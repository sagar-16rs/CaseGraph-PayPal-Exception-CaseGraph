import type { SafetyAssessment } from '../api/types';
import type { CaseDetail } from '../api/types';
import { actionLabel, caseDue, reasonLabel, splitAmount, tone } from '../lib/format';

interface Props {
  detail: CaseDetail;
  safety: SafetyAssessment | null;
  analysisCount: number;
}

const TONE_CLASS = { good: 'is-clear', warn: 'is-caution', bad: 'is-risk', neutral: 'is-caution' } as const;

/**
 * Case identity plus the always-visible verdict bar. The decision state must never
 * be hidden behind a tab: an operator glancing at the dossier needs to know whether
 * anything can be sent and what the deadline is.
 */
export default function CaseHeader({ detail, safety, analysisCount }: Props) {
  const { amount, currency } = splitAmount(detail.dispute_amount);
  const due = caseDue(detail);

  const verdictTone = safety ? tone(safety.safety_status) : 'neutral';
  const status = safety
    ? safety.is_stale
      ? 'STALE'
      : safety.safety_status
    : analysisCount
      ? 'UNVALIDATED'
      : 'NOT ANALYSED';

  const decision = safety
    ? safety.effective_action === 'NONE'
      ? 'no action may be approved'
      : `approvable: ${actionLabel(safety.effective_action)}`
    : 'run the reasoning pass to establish a decision';

  return (
    <header className="case-bar">
      <div className="case-id">
        <h1>{detail.paypal_dispute_id}</h1>
        <span className="amount">
          {amount} {currency}
        </span>
      </div>

      <div className="case-sub">
        <span>{reasonLabel(detail.dispute_reason)}</span>
        <span>
          case revision <b>{detail.sync_revision}</b>
        </span>
        <span>
          evidence revision <b>{detail.evidence_set_revision}</b>
        </span>
        <span>
          deadline <b>{due.label}</b>
        </span>
        {detail.simulated && <span>payload source: simulated sandbox</span>}
      </div>

      <div className={`verdict-bar ${TONE_CLASS[verdictTone]}`}>
        <span className="state">{status}</span>
        <span className="decision">{decision}</span>
        {safety && safety.action_risk !== 'NONE' && <span className="muted small">risk {safety.action_risk}</span>}
        {safety?.is_stale && <span className="muted small">· {safety.stale_reason}</span>}
        {!safety && <span className="muted small">· PayPal remains the source of truth</span>}
      </div>
    </header>
  );
}
