from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TranscriptTurnInput(StrictModel):
    speaker: Literal["customer", "merchant_agent", "system"]
    message: str = Field(..., min_length=1, max_length=100000)


class SupportIntakeRequest(StrictModel):
    intake_request_id: str | None = Field(default=None, min_length=8, max_length=128)
    created_by: str = Field(default="operator", min_length=1, max_length=256)
    transcript: list[TranscriptTurnInput] = Field(default_factory=list, max_length=200)
    merchant_notes: str | None = Field(default=None, max_length=50000)
    attachment_metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def non_empty(self):
        if not self.transcript and not (self.merchant_notes or "").strip() and not self.attachment_metadata:
            raise ValueError("support intake must contain transcript, merchant notes, or attachment metadata")
        return self


class GraphCreateRequest(StrictModel):
    nodes: list[dict[str, Any]] = Field(..., max_length=300)
    edges: list[dict[str, Any]] = Field(..., max_length=1000)
    created_by: str = Field(default="operator", min_length=1, max_length=256)
    creation_mode: Literal["MANUAL"] = "MANUAL"
