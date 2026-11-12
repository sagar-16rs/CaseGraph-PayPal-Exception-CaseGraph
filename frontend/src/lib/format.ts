import type { CaseDetail, VerifiedFact } from '../api/types';

/** Human labels for PayPal fact types. Internal names never reach the screen. */
export const FACT_LABELS: Record<string, string> = {
  PAYPAL_DISPUTE_ID: 'Dispute',
  PAYPAL_DISPUTE_STATUS: 'Status',
  PAYPAL_DISPUTE_REASON: 'Reason',
  PAYPAL_DISPUTE_LIFECYCLE_STAGE: 'Stage',
  PAYPAL_DISPUTE_AMOUNT: 'Disputed amount',
  PAYPAL_SELLER_RESPONSE_DUE_DATE: 'Respond by',
  PAYPAL_TRANSACTION_ID: 'Transaction',
  PAYPAL_AVAILABLE_ACTIONS: 'PayPal actions',
  PAYPAL_ALLOWED_REFUND_AMOUNT: 'Refund ceiling',
};

export const REASON_LABELS: Record<string, string> = {
  MERCHANDISE_OR_SERVICE_NOT_RECEIVED: 'Item not received',
  MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED: 'Not as described',
  UNAUTHORIZED: 'Unauthorised payment',
  CREDIT_NOT_PROCESSED: 'Credit not processed',
  DUPLICATE_TRANSACTION: 'Duplicate charge',
  INCORRECT_AMOUNT: 'Incorrect amount',
  PAYMENT_BY_OTHER_MEANS: 'Paid by other means',
  CANCELED_RECURRING_BILLING: 'Cancelled subscription',
};

export const ACTION_LABELS: Record<string, string> = {
  SEND_MESSAGE: 'Send message',
  MAKE_OFFER: 'Make offer',
  ACCEPT_CLAIM: 'Accept claim',
  PROVIDE_EVIDENCE: 'Provide evidence',
  APPEAL: 'Appeal',
  ESCALATE: 'Escalate',
  PROVIDE_SUPPORTING_INFO: 'Provide information',
  ACKNOWLEDGE_RETURN_ITEM: 'Acknowledge return',
  NONE: 'No action',
};

export const NODE_KIND: Record<string, string> = {
  VERIFIED_FACT: 'Verified fact',
  CUSTOMER_CLAIM: 'Customer claim',
  MERCHANT_CLAIM: 'Merchant claim',
  EVENT: 'Event',
  MISSING_EVIDENCE: 'Missing evidence',
  AI_INFERENCE: 'Inference',
  ACTION: 'Action',
};

export const SUB_STATUS: Record<string, string> = {
  WAITING_FOR_SELLER_RESPONSE: 'Awaiting seller',
  UNDER_REVIEW: 'Under review',
  REQUIRED_ACTION: 'Action required',
  RESOLVED_SELLER_FAVOUR: 'Resolved — seller',
  RESOLVED_BUYER_FAVOUR: 'Resolved — buyer',
  RESOLVED_WITH_PAYOUT: 'Resolved — payout',
  CANCELED_BY_BUYER: 'Cancelled by buyer',
};

export function titleCaseWords(value: string): string {
  return value
    .toLowerCase()
    .split(/[\s_]+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ');
}

export function reasonLabel(reason: string | null | undefined): string {
  if (!reason) return '—';
  return REASON_LABELS[reason] ?? titleCaseWords(reason);
}

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? titleCaseWords(action);
}

export function statusLabel(status: string): string {
  return SUB_STATUS[status] ?? titleCaseWords(status);
}

/** Semantic tone. UNDER_REVIEW is not a warning — it is normal PayPal state. */
export function tone(value: string | null | undefined): 'good' | 'warn' | 'bad' | 'neutral' {
  const upper = String(value ?? '').toUpperCase();
  if (!upper) return 'neutral';
  if (['PASS', 'EXECUTED', 'CLEAN', 'COMPLETED', 'RESOLVED_SELLER_FAVOUR', 'CANCELED_BY_BUYER', 'READY'].includes(upper)) return 'good';
  if (['BLOCKED', 'UNKNOWN_OUTCOME', 'FAILED', 'RESOLVED_BUYER_FAVOUR', 'DEAD_LETTER'].some((token) => upper.includes(token))) return 'bad';
  if (['REVIEW', 'PENDING', 'NOT_STARTED', 'RETRY'].some((token) => upper.includes(token))) return 'warn';
  return 'neutral';
}

export function splitAmount(value: string | null | undefined): { amount: string; currency: string } {
  if (!value) return { amount: '—', currency: '' };
  const [amount, currency = ''] = value.trim().split(/\s+/);
  return { amount, currency };
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso).slice(0, 10);
  return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso).slice(0, 16).replace('T', ' ');
  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function relTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const diff = Date.now() - date.getTime();
  const mins = Math.round(diff / 60000);
  if (Math.abs(mins) < 1) return 'just now';
  if (Math.abs(mins) < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (Math.abs(hours) < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export interface DueInfo {
  days: number | null;
  label: string;
  urgency: 'overdue' | 'urgent' | 'soon' | 'normal' | 'unknown';
}

/** Turn PayPal's ISO deadline into something a human can act on. */
export function dueInfo(iso: string | null | undefined): DueInfo {
  if (!iso) return { days: null, label: 'no deadline', urgency: 'unknown' };
  const due = new Date(iso);
  if (Number.isNaN(due.getTime())) return { days: null, label: String(iso), urgency: 'unknown' };
  const days = Math.ceil((due.getTime() - Date.now()) / 86_400_000);
  if (days < 0) return { days, label: `${Math.abs(days)}d overdue`, urgency: 'overdue' };
  if (days === 0) return { days, label: 'due today', urgency: 'urgent' };
  if (days <= 3) return { days, label: `${days}d left`, urgency: 'urgent' };
  if (days <= 7) return { days, label: `${days}d left`, urgency: 'soon' };
  return { days, label: `${days}d left`, urgency: 'normal' };
}

export function caseDue(detail: CaseDetail | null | undefined): DueInfo {
  const fact = detail?.verified_facts.find((item) => item.type === 'PAYPAL_SELLER_RESPONSE_DUE_DATE');
  return dueInfo(fact?.value ?? null);
}

export interface FactRow {
  key: string;
  label: string;
  value: string;
  mono?: boolean;
  chips?: string[];
}

/** Present PayPal facts as labelled rows, never as raw internal keys or JSON. */
export function factRows(detail: CaseDetail | null | undefined): FactRow[] {
  if (!detail) return [];
  const order = [
    'PAYPAL_DISPUTE_STATUS',
    'PAYPAL_DISPUTE_REASON',
    'PAYPAL_DISPUTE_LIFECYCLE_STAGE',
    'PAYPAL_DISPUTE_AMOUNT',
    'PAYPAL_ALLOWED_REFUND_AMOUNT',
    'PAYPAL_SELLER_RESPONSE_DUE_DATE',
    'PAYPAL_TRANSACTION_ID',
  ];
  const byType = new Map<string, VerifiedFact>(detail.verified_facts.map((fact) => [fact.type, fact]));
  const rows: FactRow[] = [];

  for (const type of order) {
    const fact = byType.get(type);
    if (!fact) continue;
    let value = fact.value;
    if (type === 'PAYPAL_DISPUTE_STATUS') value = statusLabel(fact.value);
    else if (type === 'PAYPAL_DISPUTE_REASON') value = reasonLabel(fact.value);
    else if (type === 'PAYPAL_DISPUTE_LIFECYCLE_STAGE') value = titleCaseWords(fact.value);
    else if (type === 'PAYPAL_SELLER_RESPONSE_DUE_DATE') value = `${fmtDate(fact.value)} · ${dueInfo(fact.value).label}`;
    rows.push({
      key: type,
      label: FACT_LABELS[type] ?? titleCaseWords(type),
      value,
      mono: type === 'PAYPAL_TRANSACTION_ID',
    });
  }

  if (detail.allowed_response_options.length) {
    rows.push({
      key: 'actions',
      label: FACT_LABELS.PAYPAL_AVAILABLE_ACTIONS,
      value: '',
      chips: detail.allowed_response_options,
    });
  }
  return rows;
}
