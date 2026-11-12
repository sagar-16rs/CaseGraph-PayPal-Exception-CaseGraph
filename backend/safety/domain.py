from __future__ import annotations

import hashlib
import json
from enum import StrEnum


SAFETY_POLICY_VERSION = "casegraph_safety_policy_v4"


class SafetyStatus(StrEnum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"


class ActionRisk(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


POLICY = {
    "version": SAFETY_POLICY_VERSION,
    "risk": {
        "critical": ["MAKE_OFFER", "ACCEPT_CLAIM"],
        "high": ["PROVIDE_EVIDENCE", "APPEAL", "ESCALATE"],
        "medium": ["ACKNOWLEDGE_RETURN_ITEM", "PROVIDE_SUPPORTING_INFO"],
        "low": ["SEND_MESSAGE"],
    },
    "minimum_action_confidence": {
        "LOW": 0.50,
        "MEDIUM": 0.60,
        "HIGH": 0.70,
        "CRITICAL": 0.90,
    },
    "high_inference_confidence": 0.85,
    "rules": [
        "all non-NONE recommendations require explicit supporting node ids",
        "all AI inferences must terminate transitively in source-backed roots",
        "high-confidence inferences without authoritative PayPal roots require review",
        "contradicted recommendation support raises or blocks action scrutiny",
        "missing evidence cannot justify medium/high/critical actions",
        "critical financial actions always require exact typed payload validation and human review",
        "all consequential actions require immutable human approval",
    ],
}


def policy_hash() -> str:
    return hashlib.sha256(
        json.dumps(POLICY, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
