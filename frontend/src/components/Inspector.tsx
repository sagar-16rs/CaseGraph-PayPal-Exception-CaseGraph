import type { Explanation, GraphRevision, SafetyAssessment } from '../api/types';
import { NODE_KIND } from '../lib/format';
import ReadinessPanel from './ReadinessPanel';

interface Props {
  graph: GraphRevision | null;
  nodeId: string | null;
  readiness: Explanation['readiness'] | null;
  safety: SafetyAssessment | null;
  onSelectNode: (nodeId: string) => void;
  onClearNode: () => void;
}

const EXPLANATIONS: Record<string, string> = {
  UNGROUNDED_AI_INFERENCE:
    'The model asserted something that does not trace back to a PayPal fact or an exact evidence revision, so the graph is blocked.',
  HIGH_CONFIDENCE_INFERENCE_WITHOUT_PAYPAL_ROOT:
    'A confident inference rests only on non-authoritative evidence; PayPal state is not in the grounding chain.',
  ACTION_WITHOUT_SUPPORT: 'The recommended action cites no supporting node, so nothing justifies contacting PayPal.',
  MISSING_EVIDENCE_CANNOT_JUSTIFY_ACTION:
    'A consequential action is being justified by evidence that is absent. Absence can motivate a request for information, never a payment decision.',
  ACTION_SUPPORT_IS_CONTRADICTED:
    'A node supporting the recommendation is contradicted by another node. High-risk actions are blocked; low-risk ones drop to review.',
  ACTION_CONFIDENCE_BELOW_POLICY_THRESHOLD: 'Model confidence is below the threshold this risk class requires.',
  CRITICAL_ACTION_REQUIRES_EXACT_HUMAN_PAYLOAD_VALIDATION:
    'This action can move money, so a human must approve the exact typed payload before PayPal is contacted.',
};

function NodeDetail({ graph, nodeId, onSelectNode, onClearNode }: Pick<Props, 'graph' | 'nodeId' | 'onSelectNode' | 'onClearNode'>) {
  const node = graph?.nodes.find((item) => item.node_id === nodeId);
  if (!node) {
    return <p className="muted small">This node is no longer present in the current graph revision.</p>;
  }
  const incoming = (graph?.edges ?? []).filter((edge) => edge.target_node_id === node.node_id);
  const outgoing = (graph?.edges ?? []).filter((edge) => edge.source_node_id === node.node_id);

  return (
    <div className="stack">
      <button type="button" className="linky" onClick={onClearNode} style={{ justifySelf: 'start' }}>
        ← case posture
      </button>

      <div>
        <div className="micro">{NODE_KIND[node.node_type] ?? node.node_type}</div>
        <h2 className="doc" style={{ fontSize: 17, lineHeight: 1.3, marginTop: 6 }}>
          {node.title}
        </h2>
      </div>

      <p style={{ fontFamily: 'var(--font-doc)', fontSize: 13, lineHeight: 1.55 }}>{node.statement}</p>

      {node.source_excerpt && <blockquote className="record" style={{ display: 'block' }}>{node.source_excerpt}</blockquote>}

      <div>
        <div className="micro" style={{ marginBottom: 6 }}>
          Provenance
        </div>
        {node.source_ref ? (
          <p className="rec" style={{ fontSize: 11 }}>
            {node.source_ref}@{node.source_revision} · {node.source_kind}
          </p>
        ) : (
          <p className="small muted">
            No direct source. This node is {node.node_type === 'AI_INFERENCE' ? 'model-generated and must be grounded by its edges' : 'structural'}.
          </p>
        )}
        {typeof node.confidence === 'number' && node.confidence >= 0 && (
          <p className="small muted">model confidence {Math.round(node.confidence * 100)}%</p>
        )}
      </div>

      {(incoming.length > 0 || outgoing.length > 0) && (
        <div>
          <div className="micro" style={{ marginBottom: 6 }}>
            Relations
          </div>
          <div className="chipset">
            {incoming.map((edge) => (
              <button type="button" key={edge.edge_id} className="chip" onClick={() => onSelectNode(edge.source_node_id)}>
                {edge.relation_type} ← {edge.source_node_id}
              </button>
            ))}
            {outgoing.map((edge) => (
              <button type="button" key={edge.edge_id} className="chip" onClick={() => onSelectNode(edge.target_node_id)}>
                {edge.relation_type} → {edge.target_node_id}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Inspector({ graph, nodeId, readiness, safety, onSelectNode, onClearNode }: Props) {
  if (nodeId) {
    return (
      <aside className="inspector" aria-label="Node inspector">
        <NodeDetail graph={graph} nodeId={nodeId} onSelectNode={onSelectNode} onClearNode={onClearNode} />
      </aside>
    );
  }

  const findings = (safety?.report?.findings ?? []) as Array<{
    code: string;
    severity: string;
    supporting_node_ids?: string[];
    node_id?: string;
  }>;

  return (
    <aside className="inspector" aria-label="Case posture">
      <div className="block">
        <ReadinessPanel readiness={readiness} />
      </div>

      <div className="block">
        <div className="row between">
          <span className="micro">Safety findings</span>
          {safety && <span className="rec" style={{ fontSize: 10.5 }}>{safety.policy_version}</span>}
        </div>

        {!safety && <p className="muted small" style={{ marginTop: 8 }}>No assessment yet.</p>}

        {safety && findings.length === 0 && (
          <p className="small" style={{ marginTop: 8, color: 'var(--ink-2)' }}>
            No policy findings. Every inference is grounded and the recommendation is supported.
          </p>
        )}

        {findings.map((finding) => {
          const refs = [...(finding.node_id ? [finding.node_id] : []), ...(finding.supporting_node_ids ?? [])];
          return (
            <div key={finding.code} className="finding">
              <div className="row" style={{ gap: 8 }}>
                <span className={`sev ${finding.severity === 'BLOCK' ? 'block' : 'review'}`}>{finding.severity}</span>
                <span className="code">{finding.code}</span>
              </div>
              <p className="why">{EXPLANATIONS[finding.code]}</p>
              {refs.length > 0 && (
                <div className="refs">
                  {refs.map((ref) => (
                    <button type="button" key={ref} className="linky" onClick={() => onSelectNode(ref)}>
                      {ref}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {safety && (
          <details className="raw">
            <summary>Raw policy report</summary>
            <pre>{JSON.stringify(safety.report, null, 2)}</pre>
          </details>
        )}
      </div>
    </aside>
  );
}
