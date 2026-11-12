from enum import StrEnum


class WorkStatus(StrEnum):
    READY='READY'; LEASED='LEASED'; RETRY='RETRY'; COMPLETED='COMPLETED'; DEAD_LETTER='DEAD_LETTER'


class WorkType(StrEnum):
    PAYPAL_DISPUTE_WEBHOOK='PAYPAL_DISPUTE_WEBHOOK'


class ReconciliationMethod(StrEnum):
    # Automatic: CaseGraph re-read the authoritative PayPal dispute and recorded
    # what it could (and could not) prove about the ambiguous write.
    AUTO_PAYPAL_STATE='AUTO_PAYPAL_STATE'
    # Manual: a named operator confirmed the outcome directly in the PayPal
    # dashboard. This is the only path allowed to clear an ambiguous write as
    # "not executed" and thereby unblock a new approval.
    MANUAL_PAYPAL_DASHBOARD='MANUAL_PAYPAL_DASHBOARD'


class ReconciliationOutcome(StrEnum):
    CONFIRMED_EXECUTED='CONFIRMED_EXECUTED'
    CONFIRMED_NOT_EXECUTED='CONFIRMED_NOT_EXECUTED'
    # A fresh GET that does not reveal an effect is NOT proof that a
    # non-idempotent POST failed. INCONCLUSIVE preserves the block.
    INCONCLUSIVE='INCONCLUSIVE'
