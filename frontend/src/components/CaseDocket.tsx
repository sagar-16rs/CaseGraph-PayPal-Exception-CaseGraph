import type { CaseDetail } from '../api/types';
import { caseDue, splitAmount, statusLabel } from '../lib/format';

interface Props {
  cases: CaseDetail[];
  selectedId: string | null;
  onSelect: (caseId: string) => void;
}

export default function CaseDocket({ cases, selectedId, onSelect }: Props) {
  const sorted = [...cases].sort((a, b) => {
    const ta = caseDue(a).days ?? 9999;
    const tb = caseDue(b).days ?? 9999;
    return ta - tb;
  });

  return (
    <aside className="docket" aria-label="Case docket">
      <div className="docket-head">
        <span className="micro">Docket</span>
        <span className="count">{cases.length}</span>
      </div>

      {sorted.map((item) => {
        const due = caseDue(item);
        const { amount, currency } = splitAmount(item.dispute_amount);
        const className = [
          'docket-item',
          item.case_id === selectedId ? 'is-active' : '',
          due.urgency === 'urgent' || due.urgency === 'overdue' ? 'is-urgent' : '',
          due.urgency === 'soon' ? 'is-soon' : '',
        ]
          .filter(Boolean)
          .join(' ');
        return (
          <button
            type="button"
            key={item.case_id}
            className={className}
            onClick={() => onSelect(item.case_id)}
            aria-current={item.case_id === selectedId ? 'true' : undefined}
          >
            <span className="edge" aria-hidden="true" />
            <span>
              <span className="ref">{item.paypal_dispute_id}</span>
              <span className="meta">
                <span>{statusLabel(item.dispute_status)}</span>
                <span className="due">
                  {amount} {currency}
                </span>
              </span>
              <span className="meta">
                <span>{due.label}</span>
                {item.simulated && <span>simulated</span>}
              </span>
            </span>
          </button>
        );
      })}

      {!cases.length && (
        <p className="muted small" style={{ padding: '12px 8px' }}>
          No cases yet. Sync a dispute, or run <code>scripts/demo_seed.py</code>.
        </p>
      )}
    </aside>
  );
}
