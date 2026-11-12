import type { ReactNode } from 'react';
import type { Explanation } from '../api/types';
import { actionLabel } from '../lib/format';

interface Props {
  explanation: Explanation | null;
  busy: boolean;
  onLoad: () => void;
  onFocusNode?: (nodeId: string) => void;
}

/** Keep internal action enums out of the prose, matching the control labels. */
function humanNextStep(explanation: Explanation): string {
  const action = explanation.verdict.effective_action;
  if (!action || action === 'NONE') return explanation.next_step;
  return explanation.next_step.split(action).join(actionLabel(action));
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ marginTop: 22 }}>
      <div className="section-head">
        <h3>{title}</h3>
      </div>
      {children}
    </section>
  );
}

/**
 * The exportable audit document.
 *
 * This is the backend's deterministic explanation rendered verbatim: which sources
 * ground the recommendation, what conflicts, what is missing, which policy findings
 * fired, and what has to happen next. No model call — the same analysis always
 * produces the same document.
 */
export default function ExplanationPanel({ explanation, busy, onLoad, onFocusNode }: Props) {
  if (!explanation) {
    return (
      <div className="sheet">
        <p className="small" style={{ color: 'var(--ink-2)' }}>
          The audit explanation is assembled by the backend from the persisted analysis, graph revision and safety
          assessment. It contains no model call, so the same analysis always produces the same document.
        </p>
        <button type="button" className="btn ghost" disabled={busy} onClick={onLoad}>
          Load audit explanation
        </button>
      </div>
    );
  }

  const { verdict, confidence, revisions } = explanation;
  const confidenceOk = confidence.recommendation >= confidence.required_minimum;

  return (
    <div>
      <div className="row wrap" style={{ gap: 10 }}>
        <span className={`status-word ${verdict.status === 'PASS' ? 'good' : verdict.status === 'BLOCKED' ? 'bad' : 'warn'}`}>
          {verdict.status}
        </span>
        <span className="rec" style={{ fontSize: 11 }}>
          {explanation.reasoning.provider}/{explanation.reasoning.model}
        </span>
        <span className="chip">case r{revisions.current_case_revision}</span>
        <span className="chip">graph input r{revisions.graph_input_case_revision}</span>
        <span className="chip">evidence r{revisions.current_evidence_set_revision}</span>
        <span className="chip">{explanation.policy_version}</span>
      </div>

      <p style={{ fontFamily: 'var(--font-doc)', fontSize: 15, lineHeight: 1.6, marginTop: 16 }}>
        {explanation.reasoning.summary}
      </p>

      <p className="small" style={{ borderLeft: '2px solid var(--rule-strong)', paddingLeft: 12, color: 'var(--ink-2)' }}>
        {humanNextStep(explanation)}
      </p>

      <Section title="Confidence against policy">
        <p className="small">
          Recommendation confidence <b className="num">{confidence.recommendation.toFixed(2)}</b> against a required
          minimum of <b className="num">{confidence.required_minimum.toFixed(2)}</b> for {verdict.risk.toLowerCase()} risk
          {' — '}
          <span className={`status-word ${confidenceOk ? 'good' : 'warn'}`}>{confidenceOk ? 'meets policy' : 'below policy'}</span>
        </p>
      </Section>

      <Section title="Grounding">
        {explanation.grounding.length === 0 && <p className="small muted">No supporting nodes were cited.</p>}
        {explanation.grounding.map((item) => (
          <div key={item.node_id} className="finding">
            <div className="row" style={{ gap: 8 }}>
              <span className={`sev ${item.grounded ? 'review' : 'block'}`}>{item.grounded ? 'grounded' : 'ungrounded'}</span>
              <span className="code">{item.node_id}</span>
              <span className="muted small">{item.node_type}</span>
            </div>
            <p className="why">{item.title ?? item.node_id}</p>
            {(item.grounded_in ?? []).slice(0, 2).map((path, index) => (
              <div key={index} className="refs">
                {path.map((step) => (
                  <button
                    type="button"
                    key={step.node_id}
                    className="linky"
                    onClick={() => onFocusNode?.(step.node_id)}
                    title={step.kind}
                  >
                    {step.ref ? `${step.ref}@${step.revision}` : step.node_id}
                  </button>
                ))}
              </div>
            ))}
          </div>
        ))}
      </Section>

      {explanation.contradictions.length > 0 && (
        <Section title="Contradictions">
          {explanation.contradictions.map((item) => (
            <div key={`${item.left}-${item.right}`} className="finding">
              <div className="row" style={{ gap: 8 }}>
                <span className={`sev ${item.affects_recommendation ? 'block' : 'review'}`}>
                  {item.affects_recommendation ? 'affects decision' : 'background'}
                </span>
              </div>
              <p className="why">
                {item.left_title ?? item.left} ⟷ {item.right_title ?? item.right}
                {item.rationale ? ` — ${item.rationale}` : ''}
              </p>
            </div>
          ))}
        </Section>
      )}

      {explanation.evidence_gaps.length > 0 && (
        <Section title="Evidence gaps">
          {explanation.evidence_gaps.map((item) => (
            <div key={item.node_id} className="finding">
              <span className="sev review">missing</span> <span className="code">{item.node_id}</span>
              <p className="why">{item.statement}</p>
            </div>
          ))}
        </Section>
      )}

      {explanation.readiness?.requirements?.length > 0 && (
        <Section title="Readiness requirements">
          {explanation.readiness.requirements.map((item) => (
            <div key={item.code} className={`req is-${item.status}`}>
              <div className="req-top">
                <span className="mark">{item.status === 'present' ? '✓' : item.status === 'missing' ? '✗' : '·'}</span>
                <span className="label">{item.label}</span>
                {item.critical && <span className="tag critical">required</span>}
              </div>
              <p className="detail">{item.detail}</p>
            </div>
          ))}
        </Section>
      )}

      {explanation.findings.length > 0 && (
        <Section title="Policy findings">
          {explanation.findings.map((item) => (
            <div key={item.code} className="finding">
              <div className="row" style={{ gap: 8 }}>
                <span className={`sev ${item.severity === 'BLOCK' ? 'block' : 'review'}`}>{item.severity}</span>
                <span className="code">{item.code}</span>
              </div>
              <p className="why">{item.explanation}</p>
            </div>
          ))}
        </Section>
      )}

      {explanation.reasoning.uncertainties.length > 0 && (
        <Section title="Stated uncertainties">
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {explanation.reasoning.uncertainties.map((item) => (
              <li key={item} className="small" style={{ marginBottom: 6 }}>{item}</li>
            ))}
          </ul>
        </Section>
      )}

      <details className="raw" style={{ marginTop: 24 }}>
        <summary>Export this explanation as JSON</summary>
        <pre>{JSON.stringify(explanation, null, 2)}</pre>
      </details>
    </div>
  );
}
