from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ANALYSIS_SCHEMA_VERSION = "casegraph_ai_output_v2"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeCaseRequest(StrictModel):
    analysis_request_id: str = Field(..., min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    # In authenticated HTTP requests security replaces this with the signed JWT
    # subject. It remains in the service contract for deterministic CLI/tests.
    requested_by: str = Field(default="operator", min_length=1, max_length=256)


NodeType = Literal[
    "VERIFIED_FACT",
    "CUSTOMER_CLAIM",
    "MERCHANT_CLAIM",
    "AI_INFERENCE",
    "MISSING_EVIDENCE",
    "ACTION",
    "EVENT",
]
SourceKind = Literal["PAYPAL_FACT", "EXTERNAL_EVIDENCE", "NONE"]
RelationType = Literal[
    "SUPPORTS",
    "CONTRADICTS",
    "DERIVED_FROM",
    "MISSING_FOR",
    "PRECEDES",
    "REFERENCES",
    "RESOLVES",
    "CLAIMS",
]


class AINode(StrictModel):
    node_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    node_type: NodeType
    title: str = Field(..., min_length=1, max_length=300)
    statement: str = Field(..., min_length=1, max_length=5000)
    source_kind: SourceKind
    source_ref: str = Field(..., max_length=128)
    source_revision: int = Field(..., ge=0)
    source_excerpt: str = Field(..., max_length=5000)
    # -1 is a sentinel for non-AI nodes, retained for compatibility with the
    # historical CaseGraph graph contract. AI_INFERENCE must use [0, 1].
    confidence: float = Field(..., ge=-1.0, le=1.0)


class AIEdge(StrictModel):
    edge_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    source_node_id: str = Field(..., min_length=1, max_length=128)
    target_node_id: str = Field(..., min_length=1, max_length=128)
    relation_type: RelationType
    rationale: str = Field(..., min_length=1, max_length=2000)


class AIRecommendation(StrictModel):
    action_type: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Z0-9_]+$")
    rationale: str = Field(..., min_length=1, max_length=3000)
    requires_human_approval: Literal[True]
    confidence: float = Field(..., ge=0.0, le=1.0)
    supporting_node_ids: list[str] = Field(..., max_length=50)


class AIOutput(StrictModel):
    summary: str = Field(..., min_length=1, max_length=5000)
    nodes: list[AINode] = Field(..., max_length=300)
    edges: list[AIEdge] = Field(..., max_length=1000)
    recommended_action: AIRecommendation
    uncertainties: list[str] = Field(..., max_length=100)


def analysis_output_schema() -> dict[str, Any]:
    return AIOutput.model_json_schema()


def analysis_schema_hash() -> str:
    payload = json.dumps(analysis_output_schema(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class AIAnalysisResponse(StrictModel):
    analysis_uid: str
    request_id: str
    case_id: str
    input_case_revision: int
    input_evidence_set_revision: int
    model_provider: str
    model_name: str
    prompt_version: str
    schema_version: str
    schema_hash: str
    bundle_hash: str
    output_hash: str | None
    provider_response_id: str | None
    status: str
    validation_status: str
    graph_id: str | None
    output: dict[str, Any]
    error: str | None = None
