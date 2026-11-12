import type { Explanation } from '../api/types';

interface Props {
  readiness: Explanation['readiness'] | null;
}

/**
 * Dispute readiness: the actionable half of an investigation.
 *
 * A gap is only useful if it names the requirement it leaves unmet, so each row
 * states what PayPal expects for this reason code and whether the attached
 * evidence covers it. The basis line is shown deliberately — this is a coverage
 * check over attached text, not a prediction of the outcome.
 */
export default function ReadinessPanel({ readiness }: Props) {
  if (!readiness) {
    return <p className="muted small">Run the reasoning pass to evaluate evidence readiness.</p>;
  }

  const requirements = readiness.requirements ?? [];
  const critical = requirements.filter((item) => item.critical);
  const satisfied = critical.filter((item) => item.status === 'present');

  return (
    <div>
      <div className="row between">
        <span className="micro">Evidence readiness</span>
        {readiness.coverage !== null && (
          <span className="rec" style={{ fontSize: 11 }}>
            {satisfied.length}/{critical.length}
          </span>
        )}
      </div>

      {readiness.coverage !== null && (
        <div className="meter" role="img" aria-label={`${satisfied.length} of ${critical.length} critical requirements covered`}>
          {critical.map((item) => (
            <span
              key={item.code}
              className={item.status === 'present' ? 'on' : item.status === 'missing' ? 'gap' : item.status === 'contradicted' ? 'warn' : ''}
            />
          ))}
        </div>
      )}

      <p className="small" style={{ color: 'var(--ink-2)', marginTop: 8 }}>
        {readiness.summary}
      </p>

      {requirements.map((item) => (
        <div key={item.code} className={`req is-${item.status}`}>
          <div className="req-top">
            <span className="mark" aria-hidden="true">
              {item.status === 'present' ? '✓' : item.status === 'missing' ? '✗' : item.status === 'contradicted' ? '!' : '·'}
            </span>
            <span className="label">{item.label}</span>
            {item.critical && <span className="tag critical">required</span>}
            {item.status === 'contradicted' && <span className="tag contested">contested</span>}
          </div>
          <p className="detail">{item.detail}</p>
        </div>
      ))}

      {!requirements.length && (
        <p className="detail" style={{ marginTop: 8 }}>
          {readiness.summary}
        </p>
      )}

      <p className="detail" style={{ marginTop: 10, color: 'var(--ink-3)' }}>
        {readiness.next_action}
      </p>
    </div>
  );
}
