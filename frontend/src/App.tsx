import { useEffect, useMemo, useState } from 'react';
import { api, ApiError } from './api/client';
import type {
  ActionApproval,
  ActionPayload,
  AIAnalysis,
  CaseDetail,
  EvidenceSet,
  Explanation,
  GraphRevision,
  Reconciliation,
  SafetyAssessment,
  StoredFile,
} from './api/types';
import CaseDocket from './components/CaseDocket';
import CaseHeader from './components/CaseHeader';
import GraphCanvas from './components/GraphCanvas';
import Inspector from './components/Inspector';
import Timeline from './components/Timeline';
import ExplanationPanel from './components/ExplanationPanel';
import ActionComposer from './components/ActionComposer';
import {
  actionLabel,
  fmtDateTime,
  factRows,
  fmtDate,
  relTime,
  splitAmount,
  statusLabel,
  tone,
} from './lib/format';
import './styles.css';

type View = 'overview' | 'graph' | 'evidence' | 'ai' | 'actions';

const VIEWS: { id: View; label: string }[] = [
  { id: 'overview', label: 'Case' },
  { id: 'graph', label: 'Evidence graph' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'ai', label: 'Reasoning' },
  { id: 'actions', label: 'Response' },
];

const rid = (prefix: string) => `${prefix}-${crypto.randomUUID().replace(/-/g, '').toUpperCase()}`;

/** Views are deep-linkable so a case state can be shared or captured for review. */
function initialView(): View {
  const requested = new URLSearchParams(window.location.search).get('view');
  return (VIEWS.find((item) => item.id === requested)?.id ?? 'overview') as View;
}

/** Replace internal action enums with the same labels used by the controls. */
function humanNextStep(explanation: Explanation | null): string {
  const raw =
    explanation?.next_step ??
    'Run the reasoning pass to establish a decision, or add evidence first if the record is thin.';
  const action = explanation?.verdict.effective_action;
  if (!action || action === 'NONE') return raw;
  return raw.split(action).join(actionLabel(action));
}

/** The single constraint that most determines what can happen next. */
function assessmentLine(explanation: Explanation): string {
  if (explanation.verdict.is_stale) {
    return 'The assessment is stale: the case or evidence changed after the graph was built.';
  }
  const blocking = explanation.findings.find((item) => item.severity === 'BLOCK');
  if (blocking) return blocking.explanation;
  const decisive = explanation.contradictions.find((item) => item.affects_recommendation);
  if (decisive) {
    return `The recommendation rests on a statement that conflicts with ${decisive.left === decisive.right ? 'another node' : 'another statement in the file'}.`;
  }
  const unmet = explanation.readiness.missing_critical.length + explanation.readiness.unknown_critical.length;
  if (unmet > 0) {
    return `${unmet} critical evidence requirement${unmet === 1 ? '' : 's'} for this dispute reason ${unmet === 1 ? 'is' : 'are'} not yet evidenced.`;
  }
  return 'Every critical evidence requirement for this dispute reason is covered by the attached material.';
}

export default function App() {
  const [cases, setCases] = useState<CaseDetail[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [graph, setGraph] = useState<GraphRevision | null>(null);
  const [evidence, setEvidence] = useState<EvidenceSet | null>(null);
  const [analyses, setAnalyses] = useState<AIAnalysis[]>([]);
  const [safety, setSafety] = useState<SafetyAssessment | null>(null);
  const [actions, setActions] = useState<ActionApproval[]>([]);
  const [files, setFiles] = useState<StoredFile[]>([]);
  const [reconciliations, setReconciliations] = useState<Reconciliation[]>([]);
  const [explanation, setExplanation] = useState<Explanation | null>(null);

  const [view, setView] = useState<View>(initialView);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [syncId, setSyncId] = useState('');
  const [customerText, setCustomerText] = useState('');
  const [merchantNote, setMerchantNote] = useState('');
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  const latestAnalysis = useMemo(
    () => analyses.find((item) => item.status === 'COMPLETED') ?? analyses[0] ?? null,
    [analyses],
  );
  const latestAction = actions[0] ?? null;

  async function loadCases(prefer?: string) {
    const list = await api.listCases();
    setCases(list);
    const id = prefer ?? selectedId ?? list[0]?.case_id ?? null;
    if (id) setSelectedId(id);
  }

  async function loadCase(id: string) {
    setBusy('Loading case');
    setError('');
    setSelectedNode(null);
    try {
      const [caseDetail, graphResult, evidenceResult, analysisResult, actionResult, fileResult] = await Promise.all([
        api.getCase(id),
        api.latestGraph(id).catch(() => null),
        api.currentEvidence(id).catch(() => null),
        api.analyses(id).catch(() => []),
        api.actions(id).catch(() => []),
        api.files(id).catch(() => []),
      ]);
      setDetail(caseDetail);
      setGraph(graphResult);
      setEvidence(evidenceResult);
      setAnalyses(analysisResult);
      setActions(actionResult);
      setFiles(fileResult);

      const completed = analysisResult.find((item) => item.status === 'COMPLETED');
      const assessment = completed ? await api.safety(id, completed.analysis_uid).catch(() => null) : null;
      setSafety(assessment);
      setExplanation(completed ? await api.explain(id, completed.analysis_uid).catch(() => null) : null);

      const newest = actionResult[0];
      setReconciliations(newest ? await api.reconciliations(id, newest.action_uid).catch(() => []) : []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy('');
    }
  }

  useEffect(() => {
    void loadCases().catch((cause) => setError(String(cause)));
  }, []);
  useEffect(() => {
    if (selectedId) void loadCase(selectedId);
  }, [selectedId]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (view === 'overview') url.searchParams.delete('view');
    else url.searchParams.set('view', view);
    window.history.replaceState(null, '', url.toString());
  }, [view]);

  async function act(label: string, run: () => Promise<unknown>) {
    setBusy(label);
    setError('');
    setNotice('');
    try {
      await run();
      setNotice(`${label} completed.`);
      if (selectedId) {
        await loadCases(selectedId);
        await loadCase(selectedId);
      }
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? `${cause.status}: ${cause.message}`
          : cause instanceof Error
            ? cause.message
            : String(cause),
      );
    } finally {
      setBusy('');
    }
  }

  async function sync() {
    if (!syncId.trim()) return;
    await act('PayPal sync', async () => {
      const result = await api.syncPayPal(syncId.trim());
      setSelectedId(result.case_id);
      setSyncId('');
    });
  }

  async function addEvidence() {
    if (!selectedId || (!customerText.trim() && !merchantNote.trim())) return;
    await act('Evidence intake', () =>
      api.intake(selectedId, {
        intake_request_id: rid('INTAKE-UI'),
        created_by: 'operator',
        transcript: customerText.trim() ? [{ speaker: 'customer', message: customerText.trim() }] : [],
        merchant_notes: merchantNote.trim() || null,
      }),
    );
    setCustomerText('');
    setMerchantNote('');
  }

  async function analyze() {
    if (!selectedId) return;
    await act('Reasoning pass', () => api.analyze(selectedId, rid('AIR-UI')));
  }

  async function approve(payload: ActionPayload) {
    if (!selectedId || !latestAnalysis || !safety) return;
    await act('Approval', () =>
      api.approveAction(selectedId, {
        actionRequestId: rid('ACTREQ-UI'),
        analysisUid: latestAnalysis.analysis_uid,
        safetyUid: safety.safety_uid,
        payload,
      }),
    );
  }

  async function execute() {
    if (!selectedId || !latestAction) return;
    await act('Execution', () => api.executeAction(selectedId, latestAction.action_uid, latestAction.approval_hash));
  }

  async function reconcile() {
    if (!selectedId || !latestAction) return;
    await act('Reconciliation', () => api.reconcile(selectedId, latestAction.action_uid));
  }

  async function upload(file: File | null) {
    if (!selectedId || !file) return;
    await act('File upload', () => api.uploadFile(selectedId, file));
  }

  const dueLabel = detail ? factRows(detail).find((row) => row.key === 'PAYPAL_SELLER_RESPONSE_DUE_DATE')?.value : '';
  const amount = splitAmount(detail?.dispute_amount);
  const rows = factRows(detail);
  const feedback = error ? { kind: 'error', text: error } : notice ? { kind: 'ok', text: notice } : null;

  return (
    <main className="shell">
      <header className="masthead">
        <span className="wordmark">
          CaseGraph<em>dispute dossier</em>
        </span>
        <span className="spacer" />
        {detail?.simulated && <span className="stamp">Simulated sandbox</span>}
        {busy && <span className="clock">{busy}…</span>}
        <span className="clock">{cases.length} cases</span>
        <span className="clock masthead-tagline">AI interprets · PayPal is authoritative · humans authorize</span>
      </header>

      <div className="cmdbar">
        <span className="micro" style={{ marginRight: 4 }}>
          Sync
        </span>
        <input
          value={syncId}
          onChange={(event) => setSyncId(event.target.value)}
          placeholder="PP-D-DEMO-1001"
          aria-label="PayPal dispute ID"
          onKeyDown={(event) => {
            if (event.key === 'Enter') void sync();
          }}
        />
        <button type="button" className="btn ghost" onClick={() => void sync()} disabled={Boolean(busy)}>
          Fetch dispute
        </button>
        <span className="spacer" style={{ flex: 1 }} />
        <span className="micro">PayPal remains the source of truth</span>
      </div>

      <div className="panes">
        <CaseDocket cases={cases} selectedId={selectedId} onSelect={setSelectedId} />

        <div className="canvas-column">
          {feedback && <div className={`notice ${feedback.kind}`}>{feedback.text}</div>}

          {!detail ? (
            <div className="canvas-body">
              <div className="empty">Select a case from the docket, or fetch a dispute from PayPal.</div>
            </div>
          ) : (
            <>
              <CaseHeader detail={detail} safety={safety} analysisCount={analyses.length} />

              <nav className="viewtabs" aria-label="Investigation views">
                {VIEWS.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    aria-current={view === item.id ? 'page' : undefined}
                    onClick={() => setView(item.id)}
                  >
                    {item.label}
                  </button>
                ))}
              </nav>

              <div className={`canvas-body ${view === 'graph' ? 'tint' : ''}`}>
                {view === 'overview' && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.25fr) minmax(0,1fr)', gap: 32 }}>
                    <div>
                      <div className="section-head">
                        <h3>PayPal record</h3>
                      </div>
                      <table className="fact-table">
                        <tbody>
                          {rows.map((row) => (
                            <tr key={row.key}>
                              <td>{row.label}</td>
                              <td>
                                {row.chips ? (
                                  <span className="chipset">
                                    {row.chips.map((chip) => (
                                      <span key={chip} className="chip tone-authority">
                                        {actionLabel(chip)}
                                      </span>
                                    ))}
                                  </span>
                                ) : (
                                  <span className={row.mono ? 'rec' : undefined}>{row.value}</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>

                      <div className="section-head" style={{ marginTop: 26 }}>
                        <h3>Next step</h3>
                      </div>
                      <p style={{ fontFamily: 'var(--font-doc)', fontSize: 14, lineHeight: 1.6 }}>
                        {humanNextStep(explanation)}
                      </p>

                      {explanation && (
                        <>
                          <div className="section-head" style={{ marginTop: 26 }}>
                            <h3>Assessment</h3>
                          </div>
                          <p style={{ fontFamily: 'var(--font-doc)', fontSize: 14, lineHeight: 1.6, color: 'var(--ink-2)' }}>
                            {assessmentLine(explanation)}
                          </p>
                          <p className="small muted">
                            {explanation.reasoning.provider}/{explanation.reasoning.model} · confidence{' '}
                            <b className="num">{explanation.confidence.recommendation.toFixed(2)}</b> against{' '}
                            <b className="num">{explanation.confidence.required_minimum.toFixed(2)}</b> required for{' '}
                            {explanation.verdict.risk.toLowerCase()} risk ·{' '}
                            {explanation.grounding.filter((item) => item.grounded).length} of{' '}
                            {explanation.grounding.length} supporting nodes grounded
                          </p>
                        </>
                      )}
                    </div>

                    <div>
                      <div className="section-head">
                        <h3>Event spine</h3>
                      </div>
                      <Timeline evidence={evidence} actions={actions} graph={graph} />
                    </div>
                  </div>
                )}

                {view === 'graph' && (
                  <>
                    {graph?.is_stale && (
                      <p className="notice error" style={{ margin: '0 0 14px' }}>
                        This graph was built from case revision {graph.input_case_revision} / evidence revision{' '}
                        {graph.input_evidence_set_revision}; the case has moved on. Re-run the reasoning pass.
                      </p>
                    )}
                    {graph ? (
                      <GraphCanvas
                        nodes={graph.nodes}
                        edges={graph.edges}
                        selected={selectedNode}
                        onSelect={setSelectedNode}
                      />
                    ) : (
                      <div className="empty">No CaseGraph yet. Add evidence and run the reasoning pass.</div>
                    )}
                  </>
                )}

                {view === 'evidence' && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 32 }}>
                    <div>
                      <div className="section-head">
                        <h3>Record evidence</h3>
                      </div>
                      <div className="sheet">
                        <label className="field">
                          <span>Customer transcript</span>
                          <textarea value={customerText} onChange={(event) => setCustomerText(event.target.value)} rows={5} />
                        </label>
                        <label className="field">
                          <span>Merchant note</span>
                          <textarea value={merchantNote} onChange={(event) => setMerchantNote(event.target.value)} rows={4} />
                        </label>
                        <button type="button" className="btn" disabled={Boolean(busy)} onClick={() => void addEvidence()}>
                          Store evidence revision
                        </button>
                        <p className="small muted" style={{ marginTop: 10 }}>
                          Intake is append-only. A new set revision keeps earlier evidence visible and invalidates any
                          analysis that did not see it.
                        </p>
                      </div>

                      <div className="section-head" style={{ marginTop: 26 }}>
                        <h3>Evidence file</h3>
                      </div>
                      <div className="sheet">
                        <p className="small muted">
                          PDF/JPG/PNG/GIF · production requires a malware scan · the stored hash is bound into the
                          approved action.
                        </p>
                        <input
                          type="file"
                          accept=".pdf,.jpg,.jpeg,.png,.gif"
                          onChange={(event) => void upload(event.target.files?.[0] ?? null)}
                        />
                        {files.map((file) => (
                          <div key={file.file_uid} className="record" style={{ gridTemplateColumns: '1fr auto' }}>
                            <span>
                              <b>{file.original_name}</b>
                              <span className="small muted">
                                {' '}
                                · {Math.round(file.size_bytes / 1024)} KB · {file.scan_status}
                              </span>
                            </span>
                            <span className="hash">{file.sha256.slice(0, 12)}…</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <div className="section-head">
                        <h3>
                          Evidence set · revision {evidence?.revision ?? 0}
                        </h3>
                      </div>
                      {(evidence?.members.length ?? 0) === 0 && <div className="empty">No evidence recorded yet.</div>}
                      {(evidence?.members ?? []).map((member) => (
                        <div key={`${member.evidence.source_ref}-${member.evidence.revision}`} className="record">
                          <span className="src">
                            {member.evidence.source_ref}@{member.evidence.revision}
                          </span>
                          <span className="body">
                            <span className="micro">{member.evidence.speaker ?? 'record'}</span>
                            <div style={{ marginTop: 4 }}>{member.evidence.content}</div>
                          </span>
                          <span className="hash" title={member.evidence.content_hash}>
                            {member.evidence.content_hash.slice(0, 10)}…
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {view === 'ai' && (
                  <div style={{ maxWidth: 760 }}>
                    <div className="row between" style={{ marginBottom: 18 }}>
                      <div>
                        <div className="micro">Structured reasoning</div>
                        <p className="small" style={{ marginTop: 4, color: 'var(--ink-2)' }}>
                          One frozen case snapshot. Output is re-validated deterministically before it can support an
                          action.
                        </p>
                      </div>
                      <button type="button" className="btn" disabled={Boolean(busy)} onClick={() => void analyze()}>
                        Run analysis
                      </button>
                    </div>

                    {latestAnalysis && (
                      <table className="fact-table" style={{ marginBottom: 26 }}>
                        <tbody>
                          <tr>
                            <td>Status</td>
                            <td>
                              <span className={`status-word ${tone(latestAnalysis.status)}`}>{latestAnalysis.status}</span>
                            </td>
                          </tr>
                          <tr>
                            <td>Provider</td>
                            <td>
                              {latestAnalysis.model_provider} / {latestAnalysis.model_name}
                            </td>
                          </tr>
                          <tr>
                            <td>Validation</td>
                            <td>{latestAnalysis.validation_status}</td>
                          </tr>
                          <tr>
                            <td>Graph</td>
                            <td className="rec">{latestAnalysis.graph_id ?? '—'}</td>
                          </tr>
                          <tr>
                            <td>Bundle hash</td>
                            <td className="rec">{latestAnalysis.bundle_hash.slice(0, 24)}…</td>
                          </tr>
                        </tbody>
                      </table>
                    )}

                    <ExplanationPanel
                      explanation={explanation}
                      busy={Boolean(busy) || !latestAnalysis}
                      onLoad={() => {
                        if (selectedId && latestAnalysis) {
                          void api
                            .explain(selectedId, latestAnalysis.analysis_uid)
                            .then(setExplanation)
                            .catch((cause) => setError(String(cause)));
                        }
                      }}
                      onFocusNode={(id) => {
                        setSelectedNode(id);
                        setView('graph');
                      }}
                    />

                    {analyses.length > 1 && (
                      <>
                        <div className="section-head" style={{ marginTop: 26 }}>
                          <h3>Analysis history</h3>
                        </div>
                        <table className="history">
                          <thead>
                            <tr>
                              <th>Status</th>
                              <th>Analysis</th>
                              <th>Model</th>
                              <th>Inputs</th>
                            </tr>
                          </thead>
                          <tbody>
                            {analyses.map((item) => (
                              <tr key={item.analysis_uid}>
                                <td>
                                  <span className={`status-word ${tone(item.status)}`}>{item.status}</span>
                                </td>
                                <td className="rec">{item.analysis_uid.slice(0, 16)}…</td>
                                <td>
                                  {item.model_provider}/{item.model_name}
                                </td>
                                <td>
                                  case r{item.input_case_revision} · evidence r{item.input_evidence_set_revision}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </>
                    )}
                  </div>
                )}

                {view === 'actions' && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.1fr) minmax(0,1fr)', gap: 32 }}>
                    <div>
                      <div className="section-head">
                        <h3>Human authorization</h3>
                      </div>
                      {!safety || safety.effective_action === 'NONE' ? (
                        <div className="sheet">
                          <span className={`status-word ${safety ? tone(safety.safety_status) : 'neutral'}`}>
                            {safety ? safety.safety_status : 'No analysis'}
                          </span>
                          <p style={{ marginTop: 10, fontFamily: 'var(--font-doc)', fontSize: 14, lineHeight: 1.6 }}>
                            No action can be approved right now.
                            {safety?.is_stale
                              ? ' The safety assessment is stale, so CaseGraph refuses to reuse it.'
                              : ' The safety policy did not clear any action for this graph.'}
                          </p>
                          <p className="small muted">
                            An inconclusive or contradicted case produces a clarifying step, never an automatic money
                            movement.
                          </p>
                        </div>
                      ) : (
                        <ActionComposer
                          actionType={safety.effective_action}
                          currency={amount.currency}
                          maxAmount={amount.amount}
                          files={files}
                          disabled={Boolean(busy) || safety.is_stale || safety.safety_status === 'BLOCKED'}
                          busy={Boolean(busy)}
                          onApprove={(payload) => void approve(payload)}
                        />
                      )}

                      {actions.length > 0 && (
                        <>
                          <div className="section-head" style={{ marginTop: 26 }}>
                            <h3>Action history</h3>
                          </div>
                          <table className="history">
                            <thead>
                              <tr>
                                <th>Execution</th>
                                <th>Action</th>
                                <th>Approved by</th>
                                <th>Approved at</th>
                              </tr>
                            </thead>
                            <tbody>
                              {actions.map((item) => (
                                <tr key={item.action_uid}>
                                  <td>
                                    <span className={`status-word ${tone(item.execution_status)}`}>
                                      {item.execution_status.replaceAll('_', ' ')}
                                    </span>
                                  </td>
                                  <td>{actionLabel(item.action_type)}</td>
                                  <td>{item.approved_by}</td>
                                  <td>{relTime(item.approved_at)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </>
                      )}
                    </div>

                    <div>
                      <div className="section-head">
                        <h3>Latest approval</h3>
                      </div>
                      {latestAction ? (
                        <div className="sheet">
                          <table className="fact-table">
                            <tbody>
                              <tr>
                                <td>Action</td>
                                <td>{actionLabel(latestAction.action_type)}</td>
                              </tr>
                              <tr>
                                <td>Risk</td>
                                <td>{latestAction.action_risk}</td>
                              </tr>
                              <tr>
                                <td>Execution</td>
                                <td>
                                  <span className={`status-word ${tone(latestAction.execution_status)}`}>
                                    {latestAction.execution_status}
                                  </span>
                                </td>
                              </tr>
                              <tr>
                                <td>Approved by</td>
                                <td>{latestAction.approved_by}</td>
                              </tr>
                              <tr>
                                <td>Approved at</td>
                                <td>{fmtDateTime(latestAction.approved_at)}</td>
                              </tr>
                              <tr>
                                <td>Payload hash</td>
                                <td className="rec">{latestAction.payload_hash.slice(0, 20)}…</td>
                              </tr>
                              <tr>
                                <td>Approval hash</td>
                                <td className="rec">{latestAction.approval_hash.slice(0, 20)}…</td>
                              </tr>
                            </tbody>
                          </table>

                          {latestAction.post_action_sync_pending && (
                            <p className="notice error" style={{ margin: '12px 0 0' }}>
                              PayPal accepted this action but the authoritative refresh did not complete. Do not resend;
                              reconcile instead.
                            </p>
                          )}

                          <div className="row wrap" style={{ marginTop: 14 }}>
                            <button
                              type="button"
                              className="btn"
                              disabled={Boolean(busy) || latestAction.execution_status !== 'NOT_STARTED'}
                              onClick={() => void execute()}
                            >
                              Execute approved action
                            </button>
                            {(latestAction.execution_status === 'UNKNOWN_OUTCOME' ||
                              latestAction.execution_status === 'PENDING' ||
                              latestAction.post_action_sync_pending) && (
                              <button type="button" className="btn ghost" disabled={Boolean(busy)} onClick={() => void reconcile()}>
                                Read-only reconcile
                              </button>
                            )}
                          </div>
                          <p className="small muted" style={{ marginTop: 10 }}>
                            An ambiguous write is never retried automatically. Reconciliation re-reads PayPal and records
                            what it can prove; only an operator who checked the dashboard can release the block.
                          </p>
                        </div>
                      ) : (
                        <div className="empty">No approval recorded.</div>
                      )}

                      {reconciliations.length > 0 && (
                        <>
                          <div className="section-head" style={{ marginTop: 26 }}>
                            <h3>Reconciliation trail</h3>
                          </div>
                          <table className="history">
                            <tbody>
                              {reconciliations.map((item) => (
                                <tr key={item.reconciliation_uid}>
                                  <td>
                                    <span className={`status-word ${tone(item.outcome)}`}>{item.outcome}</span>
                                  </td>
                                  <td>{item.method}</td>
                                  <td>→ {item.execution_status}</td>
                                  <td>{item.reconciled_by ?? 'system'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {detail ? (
          <Inspector
            graph={graph}
            nodeId={selectedNode}
            readiness={explanation?.readiness ?? null}
            safety={safety}
            onSelectNode={setSelectedNode}
            onClearNode={() => setSelectedNode(null)}
          />
        ) : (
          <aside className="inspector" aria-label="Case posture">
            <p className="small muted">No case selected.</p>
          </aside>
        )}
      </div>
    </main>
  );
}
