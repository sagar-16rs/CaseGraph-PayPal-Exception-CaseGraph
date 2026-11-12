import { useEffect, useMemo, useState } from 'react';
import type { ActionPayload, StoredFile } from '../api/types';
import { actionLabel } from '../lib/format';

interface Props {
  actionType: string;
  currency?: string | null;
  maxAmount?: string | null;
  files: StoredFile[];
  disabled: boolean;
  busy: boolean;
  onApprove: (payload: ActionPayload) => void;
}

const OFFER_TYPES = [
  ['REFUND', 'Refund the buyer'],
  ['REFUND_WITH_RETURN', 'Refund once the item is returned'],
  ['REFUND_WITH_REPLACEMENT', 'Refund and send a replacement'],
  ['REPLACEMENT_WITHOUT_REFUND', 'Send a replacement, no refund'],
] as const;

const ACCEPT_TYPES = [
  ['REFUND', 'Full refund'],
  ['PARTIAL_REFUND', 'Partial refund'],
] as const;

const ACK_TYPES = [
  ['ITEM_RECEIVED', 'Item received'],
  ['ITEM_NOT_RECEIVED', 'Item not received'],
  ['DAMAGED', 'Item arrived damaged'],
  ['EMPTY_PACKAGE_OR_DIFFERENT', 'Empty package or different item'],
  ['MISSING_ITEMS', 'Items missing from the parcel'],
] as const;

const EVIDENCE_TYPES = [
  ['PROOF_OF_FULFILLMENT', 'Proof of fulfilment'],
  ['PROOF_OF_REFUND', 'Proof of refund'],
  ['RECEIPT', 'Receipt'],
  ['OTHER', 'Other supporting document'],
] as const;

/**
 * A typed composer for the exact PayPal payload.
 *
 * The operator approves an exact, validated payload, so the payload deserves a real
 * form. The raw JSON stays available behind a disclosure for auditability.
 */
export default function ActionComposer({ actionType, currency, maxAmount, files, disabled, busy, onApprove }: Props) {
  const [message, setMessage] = useState('We are reviewing the case information and will update you here.');
  const [note, setNote] = useState('Reviewed against the attached case evidence.');
  const [notes, setNotes] = useState('Supporting information reviewed by the merchant.');
  const [offerType, setOfferType] = useState<string>('REFUND');
  const [amount, setAmount] = useState(maxAmount ?? '');
  const [acceptType, setAcceptType] = useState<string>('REFUND');
  const [ackType, setAckType] = useState<string>('ITEM_RECEIVED');
  const [evidenceType, setEvidenceType] = useState<string>('OTHER');
  const [fileUid, setFileUid] = useState<string>('');
  const [refundId, setRefundId] = useState<string>('');

  useEffect(() => setAmount(maxAmount ?? ''), [maxAmount]);

  const usableFiles = files.filter((file) => file.scan_status !== 'REJECTED');

  const payload = useMemo<ActionPayload>(() => {
    const code = (currency || 'USD').toUpperCase();
    const money = { currency_code: code, value: amount.trim() || '0.00' };
    switch (actionType) {
      case 'SEND_MESSAGE':
        return { action_type: actionType, message: message.trim() };
      case 'MAKE_OFFER': {
        const body: ActionPayload = { action_type: actionType, offer_type: offerType, note: note.trim() };
        if (offerType !== 'REPLACEMENT_WITHOUT_REFUND') body.offer_amount = money;
        if (offerType === 'REFUND_WITH_RETURN') {
          body.return_shipping_address = {
            address_line_1: 'Merchant returns desk',
            admin_area_2: 'Springfield',
            postal_code: '00000',
            country_code: 'US',
          };
        }
        return body;
      }
      case 'ACCEPT_CLAIM': {
        const body: ActionPayload = { action_type: actionType, accept_claim_type: acceptType, note: note.trim() };
        if (acceptType === 'PARTIAL_REFUND') body.refund_amount = money;
        return body;
      }
      case 'ESCALATE':
        return { action_type: actionType, note: note.trim() };
      case 'PROVIDE_SUPPORTING_INFO':
        return { action_type: actionType, notes: notes.trim() };
      case 'ACKNOWLEDGE_RETURN_ITEM':
        return { action_type: actionType, acknowledgement_type: ackType, note: note.trim() };
      case 'PROVIDE_EVIDENCE':
      case 'APPEAL': {
        const evidence: Record<string, unknown> = {
          evidence_type: evidenceType,
          notes: notes.trim(),
          evidence_info: refundId.trim() ? { refund_ids: [refundId.trim()], tracking_info: [] } : {},
        };
        const chosen = usableFiles.find((file) => file.file_uid === fileUid);
        if (chosen) evidence.file_refs = [{ file_uid: chosen.file_uid, sha256: chosen.sha256 }];
        return { action_type: actionType, evidences: [evidence] };
      }
      default:
        return { action_type: actionType };
    }
  }, [actionType, acceptType, ackType, amount, currency, evidenceType, fileUid, message, note, notes, offerType, refundId, usableFiles]);

  const incomplete =
    disabled ||
    (actionType === 'SEND_MESSAGE' && message.trim().length === 0) ||
    (actionType === 'ESCALATE' && note.trim().length === 0) ||
    (actionType === 'PROVIDE_SUPPORTING_INFO' && notes.trim().length === 0) ||
    (actionType === 'MAKE_OFFER' && offerType !== 'REPLACEMENT_WITHOUT_REFUND' && amount.trim().length === 0) ||
    (actionType === 'ACCEPT_CLAIM' && acceptType === 'PARTIAL_REFUND' && amount.trim().length === 0);

  return (
    <form
      className="sheet"
      onSubmit={(event) => {
        event.preventDefault();
        if (!incomplete) onApprove(payload);
      }}
    >
      <div className="row between" style={{ marginBottom: 14 }}>
        <span className="micro">Approve exact payload</span>
        <span className="rec" style={{ fontSize: 11 }}>
          {actionLabel(actionType)}
        </span>
      </div>

      {actionType === 'SEND_MESSAGE' && (
        <label className="field">
          <span>Message to the buyer</span>
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={4} maxLength={2000} />
          <em>{message.length}/2000 · appears in the PayPal dispute thread</em>
        </label>
      )}

      {actionType === 'MAKE_OFFER' && (
        <>
          <label className="field">
            <span>Offer type</span>
            <select value={offerType} onChange={(event) => setOfferType(event.target.value)}>
              {OFFER_TYPES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          {offerType !== 'REPLACEMENT_WITHOUT_REFUND' && (
            <label className="field">
              <span>Offer amount {currency ? `(${currency})` : ''}</span>
              <input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" />
              {maxAmount && <em>PayPal currently permits up to {maxAmount} {currency}</em>}
            </label>
          )}
          <label className="field">
            <span>Note</span>
            <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} maxLength={2000} />
          </label>
        </>
      )}

      {actionType === 'ACCEPT_CLAIM' && (
        <>
          <label className="field">
            <span>Accept as</span>
            <select value={acceptType} onChange={(event) => setAcceptType(event.target.value)}>
              {ACCEPT_TYPES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          {acceptType === 'PARTIAL_REFUND' && (
            <label className="field">
              <span>Refund amount</span>
              <input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" />
            </label>
          )}
          <label className="field">
            <span>Note</span>
            <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} maxLength={2000} />
          </label>
        </>
      )}

      {actionType === 'ESCALATE' && (
        <label className="field">
          <span>Escalation note</span>
          <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={4} maxLength={2000} />
        </label>
      )}

      {actionType === 'PROVIDE_SUPPORTING_INFO' && (
        <label className="field">
          <span>Supporting information</span>
          <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={5} maxLength={2000} />
        </label>
      )}

      {actionType === 'ACKNOWLEDGE_RETURN_ITEM' && (
        <>
          <label className="field">
            <span>Return status</span>
            <select value={ackType} onChange={(event) => setAckType(event.target.value)}>
              {ACK_TYPES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Note</span>
            <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} maxLength={2000} />
          </label>
        </>
      )}

      {(actionType === 'PROVIDE_EVIDENCE' || actionType === 'APPEAL') && (
        <>
          <label className="field">
            <span>Evidence type</span>
            <select value={evidenceType} onChange={(event) => setEvidenceType(event.target.value)}>
              {EVIDENCE_TYPES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          {evidenceType === 'PROOF_OF_REFUND' && (
            <label className="field">
              <span>PayPal refund ID</span>
              <input value={refundId} onChange={(event) => setRefundId(event.target.value)} />
            </label>
          )}
          <label className="field">
            <span>Evidence notes</span>
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} maxLength={2000} />
          </label>
          <label className="field">
            <span>Attach an uploaded file (optional)</span>
            <select value={fileUid} onChange={(event) => setFileUid(event.target.value)}>
              <option value="">No file</option>
              {usableFiles.map((file) => (
                <option key={file.file_uid} value={file.file_uid}>
                  {file.original_name} · {file.scan_status}
                </option>
              ))}
            </select>
            <em>The file hash is bound into the approval; execution re-hashes the stored bytes.</em>
          </label>
        </>
      )}

      <details className="raw">
        <summary>Exact payload to be approved</summary>
        <pre>{JSON.stringify(payload, null, 2)}</pre>
      </details>

      <div style={{ marginTop: 14 }}>
        <button type="submit" className="btn" disabled={incomplete || busy}>
          Approve immutable payload
        </button>
        <p className="small muted" style={{ marginTop: 8 }}>
          Approval stores this exact payload with a hash. CaseGraph re-reads PayPal immediately before the write and
          refuses if the live state differs from what you approved.
        </p>
      </div>
    </form>
  );
}
