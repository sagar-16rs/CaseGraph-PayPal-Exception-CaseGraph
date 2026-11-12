import type { ActionApproval, EvidenceSet, GraphRevision } from '../api/types';
import { fmtDateTime, actionLabel } from '../lib/format';

interface Props {
  evidence: EvidenceSet | null;
  actions: ActionApproval[];
  graph: GraphRevision | null;
}

interface Event {
  when: string;
  kind: 'case' | 'evidence' | 'action' | 'reasoning';
  what: string;
  note?: string;
}

/**
 * The event spine. A dispute is a sequence, and the workspace should show that
 * sequence rather than presenting every artefact as a parallel card.
 */
export default function Timeline({ evidence, actions, graph }: Props) {
  const events: Event[] = [];

  if (graph) {
    events.push({
      when: graph.created_at,
      kind: 'reasoning',
      what: `Reasoning graph compiled — revision ${graph.revision}`,
      note: `${graph.nodes.length} nodes · ${graph.edges.length} relations · ${graph.creation_mode}`,
    });
  }

  for (const member of evidence?.members ?? []) {
    events.push({
      when: member.evidence.created_at,
      kind: 'evidence',
      what: `Evidence recorded — ${member.evidence.source_ref}@${member.evidence.revision}`,
      note: `${member.evidence.speaker ?? 'record'} · ${member.evidence.evidence_type}`,
    });
  }

  for (const action of actions) {
    events.push({
      when: action.approved_at,
      kind: 'action',
      what: `${actionLabel(action.action_type)} approved — ${action.execution_status.toLowerCase().replace('_', ' ')}`,
      note: `by ${action.approved_by} · approval ${action.approval_hash.slice(0, 10)}…`,
    });
  }

  events.sort((a, b) => new Date(b.when).getTime() - new Date(a.when).getTime());

  if (!events.length) {
    return <p className="muted small">Nothing recorded yet. Evidence intake and analysis will appear here.</p>;
  }

  return (
    <div className="spine">
      {events.map((event, index) => (
        <div key={`${event.when}-${index}`} className={`spine-item kind-${event.kind}`}>
          <div className="when">{fmtDateTime(event.when)}</div>
          <div className="what">{event.what}</div>
          {event.note && <div className="note">{event.note}</div>}
        </div>
      ))}
    </div>
  );
}
