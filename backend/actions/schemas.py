from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Money(StrictModel):
    currency_code: str = Field(..., pattern=r"^[A-Z]{3}$")
    value: str = Field(..., min_length=1, max_length=32, pattern=r"^[0-9]+(?:\.[0-9]+)?$")

    @field_validator("value")
    @classmethod
    def positive_amount(cls, value: str) -> str:
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("amount must be a decimal number") from exc
        if not amount.is_finite() or amount <= 0:
            raise ValueError("amount must be greater than zero")
        return value


class ReturnAddress(StrictModel):
    address_line_1: str = Field(..., min_length=1, max_length=300)
    address_line_2: str | None = Field(default=None, max_length=300)
    address_line_3: str | None = Field(default=None, max_length=100)
    admin_area_4: str | None = Field(default=None, max_length=100)
    admin_area_3: str | None = Field(default=None, max_length=100)
    admin_area_2: str | None = Field(default=None, max_length=120)
    admin_area_1: str | None = Field(default=None, max_length=300)
    postal_code: str | None = Field(default=None, max_length=60)
    country_code: str = Field(..., pattern=r"^(?:[A-Z]{2}|C2)$")


class SendMessagePayload(StrictModel):
    action_type: Literal["SEND_MESSAGE"] = "SEND_MESSAGE"
    message: str = Field(..., min_length=1, max_length=2000)


class MakeOfferPayload(StrictModel):
    action_type: Literal["MAKE_OFFER"] = "MAKE_OFFER"
    offer_type: Literal[
        "REFUND",
        "REFUND_WITH_RETURN",
        "REFUND_WITH_REPLACEMENT",
        "REPLACEMENT_WITHOUT_REFUND",
    ]
    offer_amount: Money | None = None
    note: str | None = Field(default=None, min_length=1, max_length=2000)
    return_shipping_address: ReturnAddress | None = None

    @model_validator(mode="after")
    def validate_shape(self):
        if self.offer_type == "REPLACEMENT_WITHOUT_REFUND":
            if self.offer_amount is not None:
                raise ValueError("REPLACEMENT_WITHOUT_REFUND must not include offer_amount")
        elif self.offer_amount is None:
            raise ValueError(f"{self.offer_type} requires offer_amount")
        if self.offer_type == "REFUND_WITH_RETURN":
            if self.return_shipping_address is None:
                raise ValueError("REFUND_WITH_RETURN requires return_shipping_address")
        elif self.return_shipping_address is not None:
            raise ValueError("return_shipping_address is only valid for REFUND_WITH_RETURN")
        return self


class AcceptClaimPayload(StrictModel):
    action_type: Literal["ACCEPT_CLAIM"] = "ACCEPT_CLAIM"
    accept_claim_type: Literal["REFUND", "PARTIAL_REFUND"]
    refund_amount: Money | None = None
    note: str | None = Field(default=None, min_length=1, max_length=2000)
    accept_claim_reason: str | None = Field(default=None, min_length=1, max_length=255, pattern=r"^[A-Z0-9_]+$")
    invoice_id: str | None = Field(default=None, min_length=1, max_length=127)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.accept_claim_type == "PARTIAL_REFUND" and self.refund_amount is None:
            raise ValueError("PARTIAL_REFUND requires refund_amount")
        if self.accept_claim_type == "REFUND" and self.refund_amount is not None:
            raise ValueError("REFUND must not include refund_amount; PayPal determines the full refund")
        return self


class TrackingInfo(StrictModel):
    carrier_name: str = Field(..., min_length=1, max_length=255, pattern=r"^[0-9A-Z_]+$")
    carrier_name_other: str | None = Field(default=None, min_length=1, max_length=2000)
    tracking_number: str = Field(..., min_length=1, max_length=255)
    tracking_url: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def validate_other_carrier(self):
        if self.carrier_name == "OTHER" and not self.carrier_name_other:
            raise ValueError("carrier_name_other is required when carrier_name is OTHER")
        if self.carrier_name != "OTHER" and self.carrier_name_other:
            raise ValueError("carrier_name_other is only valid when carrier_name is OTHER")
        return self


class EvidenceInfo(StrictModel):
    tracking_info: list[TrackingInfo] = Field(default_factory=list, max_length=10)
    refund_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("refund_ids")
    @classmethod
    def validate_refund_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value or len(value) > 255 or value.strip() != value or any(ord(ch) < 32 for ch in value):
                raise ValueError("refund IDs must be non-empty, trimmed, printable strings up to 255 characters")
        if len(set(values)) != len(values):
            raise ValueError("refund IDs must be unique")
        return values


class EvidenceFileRef(StrictModel):
    file_uid: str = Field(..., min_length=10, max_length=64, pattern=r"^FILE-[A-F0-9]+$")
    sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class EvidenceItem(StrictModel):
    evidence_type: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Z0-9_]+$")
    evidence_info: EvidenceInfo = Field(default_factory=EvidenceInfo)
    notes: str | None = Field(default=None, min_length=1, max_length=2000)
    # security binds immutable, malware-scanned local files into the exact
    # human-approved action payload. The browser never supplies bytes at execute time.
    file_refs: list[EvidenceFileRef] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_required_content(self):
        if self.evidence_type == "PROOF_OF_REFUND" and not self.evidence_info.refund_ids:
            raise ValueError("PROOF_OF_REFUND requires at least one refund_id")
        uids = [ref.file_uid for ref in self.file_refs]
        if len(set(uids)) != len(uids):
            raise ValueError("duplicate evidence file references are not allowed")
        if self.evidence_type == "PROOF_OF_FULFILLMENT":
            if not self.evidence_info.tracking_info and not self.notes and not self.file_refs:
                raise ValueError("PROOF_OF_FULFILLMENT requires tracking_info, notes, or approved files")
        elif self.evidence_type == "OTHER" and not self.notes and not self.file_refs:
            raise ValueError("OTHER evidence requires notes or approved files")
        elif (
            self.evidence_type not in {"PROOF_OF_REFUND", "PROOF_OF_FULFILLMENT", "OTHER"}
            and not self.notes
            and not self.evidence_info.tracking_info
            and not self.evidence_info.refund_ids
            and not self.file_refs
        ):
            raise ValueError("evidence must contain notes, tracking information, refund IDs, or approved files")
        return self


def _validate_unique_payload_file_refs(evidences: list[EvidenceItem]) -> None:
    seen: set[str] = set()
    for evidence in evidences:
        for ref in evidence.file_refs:
            if ref.file_uid in seen:
                raise ValueError("an evidence file may be referenced only once per PayPal action payload")
            seen.add(ref.file_uid)


class ProvideEvidencePayload(StrictModel):
    action_type: Literal["PROVIDE_EVIDENCE"] = "PROVIDE_EVIDENCE"
    evidences: list[EvidenceItem] = Field(..., min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_unique_file_refs(self):
        _validate_unique_payload_file_refs(self.evidences)
        return self


class AppealPayload(StrictModel):
    action_type: Literal["APPEAL"] = "APPEAL"
    evidences: list[EvidenceItem] = Field(..., min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_unique_file_refs(self):
        _validate_unique_payload_file_refs(self.evidences)
        return self


class EscalatePayload(StrictModel):
    action_type: Literal["ESCALATE"] = "ESCALATE"
    note: str = Field(..., min_length=1, max_length=2000)


class ProvideSupportingInfoPayload(StrictModel):
    action_type: Literal["PROVIDE_SUPPORTING_INFO"] = "PROVIDE_SUPPORTING_INFO"
    notes: str = Field(..., min_length=1, max_length=2000)


class AcknowledgeReturnItemPayload(StrictModel):
    action_type: Literal["ACKNOWLEDGE_RETURN_ITEM"] = "ACKNOWLEDGE_RETURN_ITEM"
    acknowledgement_type: Literal[
        "ITEM_RECEIVED",
        "ITEM_NOT_RECEIVED",
        "DAMAGED",
        "EMPTY_PACKAGE_OR_DIFFERENT",
        "MISSING_ITEMS",
    ]
    note: str | None = Field(default=None, min_length=1, max_length=2000)


ActionPayload = Annotated[
    Union[
        SendMessagePayload,
        MakeOfferPayload,
        AcceptClaimPayload,
        ProvideEvidencePayload,
        AppealPayload,
        EscalatePayload,
        ProvideSupportingInfoPayload,
        AcknowledgeReturnItemPayload,
    ],
    Field(discriminator="action_type"),
]


class ActionApprovalRequest(StrictModel):
    action_request_id: str = Field(..., min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    approved_by: str = Field(..., min_length=1, max_length=256)
    analysis_uid: str = Field(..., min_length=4, max_length=64)
    safety_uid: str = Field(..., min_length=4, max_length=64)
    payload: ActionPayload


class ActionApprovalResponse(StrictModel):
    action_uid: str
    action_request_id: str
    case_id: str
    analysis_uid: str
    safety_uid: str
    graph_id: str
    action_type: str
    action_risk: str
    approved_by: str
    payload: dict
    payload_hash: str
    approval_hash: str
    execution_status: str
    post_action_sync_pending: bool = False
    approved_at: str


class ActionExecuteRequest(StrictModel):
    approval_hash: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class ActionExecutionResponse(StrictModel):
    action_uid: str
    action_request_id: str
    case_id: str
    action_type: str
    execution_status: str
    result_status: str
    post_action_sync_pending: bool = False
    paypal_response: dict = Field(default_factory=dict)
    updated_dispute_status: str | None = None
    warning: str | None = None
    last_error: str | None = None
