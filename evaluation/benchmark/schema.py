from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

VALID_SPLITS = {"dev", "holdout", "redteam"}
VALID_NODE_TYPES = {
    "VERIFIED_FACT",
    "CUSTOMER_CLAIM",
    "MERCHANT_CLAIM",
    "AI_INFERENCE",
    "MISSING_EVIDENCE",
    "ACTION",
    "EVENT",
}
VALID_RELATIONS = {
    "SUPPORTS",
    "CONTRADICTS",
    "DERIVED_FROM",
    "MISSING_FOR",
    "PRECEDES",
    "REFERENCES",
    "RESOLVES",
    "CLAIMS",
}
VALID_ACTIONS = {
    "NONE",
    "SEND_MESSAGE",
    "MAKE_OFFER",
    "ACCEPT_CLAIM",
    "PROVIDE_EVIDENCE",
    "ESCALATE",
    "PROVIDE_SUPPORTING_INFO",
    "ACKNOWLEDGE_RETURN_ITEM",
    "APPEAL",
}


class BenchmarkValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BenchmarkValidationError(message)


def _as_nonempty_str(value: Any, name: str) -> str:
    _require(isinstance(value, str) and value.strip() != "", f"{name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class TranscriptTurn:
    speaker: str
    message: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TranscriptTurn":
        speaker = _as_nonempty_str(raw.get("speaker"), "transcript.speaker")
        _require(speaker in {"customer", "merchant_agent"}, "transcript speaker must be customer or merchant_agent")
        message = _as_nonempty_str(raw.get("message"), "transcript.message")
        return cls(speaker=speaker, message=message)


@dataclass(frozen=True)
class BenchmarkCase:
    scenario_id: str
    split: str
    category: str
    difficulty: str
    description: str
    paypal_dispute: dict[str, Any]
    transcript: tuple[TranscriptTurn, ...]
    merchant_notes: str | None
    tags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "BenchmarkCase":
        scenario_id = _as_nonempty_str(raw.get("scenario_id"), "scenario_id")
        split = _as_nonempty_str(raw.get("split"), "split")
        _require(split in VALID_SPLITS, f"unsupported split {split!r}")
        category = _as_nonempty_str(raw.get("category"), "category")
        difficulty = _as_nonempty_str(raw.get("difficulty"), "difficulty")
        _require(difficulty in {"easy", "medium", "hard"}, "difficulty must be easy, medium or hard")
        description = _as_nonempty_str(raw.get("description"), "description")
        paypal_dispute = raw.get("paypal_dispute")
        _require(isinstance(paypal_dispute, dict), "paypal_dispute must be an object")
        dispute_id = paypal_dispute.get("dispute_id")
        _require(isinstance(dispute_id, str) and dispute_id.startswith("PP-"), "paypal_dispute.dispute_id must start with PP-")
        turns = raw.get("transcript")
        _require(isinstance(turns, list) and turns, "transcript must be a non-empty list")
        transcript = tuple(TranscriptTurn.from_dict(t) for t in turns)
        merchant_notes = raw.get("merchant_notes")
        _require(merchant_notes is None or isinstance(merchant_notes, str), "merchant_notes must be string or null")
        tags = raw.get("tags", [])
        _require(isinstance(tags, list) and all(isinstance(x, str) and x for x in tags), "tags must be strings")
        return cls(
            scenario_id=scenario_id,
            split=split,
            category=category,
            difficulty=difficulty,
            description=description,
            paypal_dispute=paypal_dispute,
            transcript=transcript,
            merchant_notes=merchant_notes,
            tags=tuple(tags),
        )


@dataclass(frozen=True)
class ExpectedClaim:
    node_type: str
    excerpt: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExpectedClaim":
        node_type = _as_nonempty_str(raw.get("node_type"), "expected_claim.node_type")
        _require(node_type in {"CUSTOMER_CLAIM", "MERCHANT_CLAIM"}, "expected claim node_type must be a human claim type")
        return cls(node_type=node_type, excerpt=_as_nonempty_str(raw.get("excerpt"), "expected_claim.excerpt"))


@dataclass(frozen=True)
class MissingEvidenceExpectation:
    label: str
    keyword_groups: tuple[tuple[str, ...], ...]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "MissingEvidenceExpectation":
        label = _as_nonempty_str(raw.get("label"), "missing_evidence.label")
        groups = raw.get("keyword_groups")
        _require(isinstance(groups, list) and groups, "missing_evidence.keyword_groups must be non-empty")
        parsed: list[tuple[str, ...]] = []
        for group in groups:
            _require(isinstance(group, list) and group and all(isinstance(k, str) and k.strip() for k in group), "keyword group must contain strings")
            parsed.append(tuple(k.casefold() for k in group))
        return cls(label=label, keyword_groups=tuple(parsed))


@dataclass(frozen=True)
class ContradictionExpectation:
    left_excerpt: str
    right_excerpt: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ContradictionExpectation":
        return cls(
            left_excerpt=_as_nonempty_str(raw.get("left_excerpt"), "contradiction.left_excerpt"),
            right_excerpt=_as_nonempty_str(raw.get("right_excerpt"), "contradiction.right_excerpt"),
        )


@dataclass(frozen=True)
class GoldCase:
    scenario_id: str
    required_claims: tuple[ExpectedClaim, ...]
    missing_evidence: tuple[MissingEvidenceExpectation, ...]
    contradictions: tuple[ContradictionExpectation, ...]
    preferred_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    must_abstain: bool
    notes: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GoldCase":
        scenario_id = _as_nonempty_str(raw.get("scenario_id"), "gold.scenario_id")
        required_claims = tuple(ExpectedClaim.from_dict(x) for x in raw.get("required_claims", []))
        missing_evidence = tuple(MissingEvidenceExpectation.from_dict(x) for x in raw.get("missing_evidence", []))
        contradictions = tuple(ContradictionExpectation.from_dict(x) for x in raw.get("contradictions", []))
        preferred_actions_raw = raw.get("preferred_actions", [])
        forbidden_actions_raw = raw.get("forbidden_actions", [])
        _require(isinstance(preferred_actions_raw, list), "preferred_actions must be a list")
        _require(isinstance(forbidden_actions_raw, list), "forbidden_actions must be a list")
        preferred_actions = tuple(_as_nonempty_str(x, "preferred_action") for x in preferred_actions_raw)
        forbidden_actions = tuple(_as_nonempty_str(x, "forbidden_action") for x in forbidden_actions_raw)
        _require(all(x in VALID_ACTIONS for x in preferred_actions), "preferred_actions contains unsupported action")
        _require(all(x in VALID_ACTIONS for x in forbidden_actions), "forbidden_actions contains unsupported action")
        _require(not (set(preferred_actions) & set(forbidden_actions)), "preferred and forbidden actions overlap")
        must_abstain = raw.get("must_abstain")
        _require(isinstance(must_abstain, bool), "must_abstain must be boolean")
        if must_abstain:
            _require(not preferred_actions or set(preferred_actions) == {"NONE"}, "must_abstain cases may only prefer NONE")
        notes = raw.get("notes", "")
        _require(isinstance(notes, str), "notes must be a string")
        return cls(
            scenario_id=scenario_id,
            required_claims=required_claims,
            missing_evidence=missing_evidence,
            contradictions=contradictions,
            preferred_actions=preferred_actions,
            forbidden_actions=forbidden_actions,
            must_abstain=must_abstain,
            notes=notes,
        )


@dataclass(frozen=True)
class Prediction:
    scenario_id: str
    run_id: str
    mode: str
    analysis_status: str
    analysis_output: dict[str, Any]
    safety: dict[str, Any]
    provenance: dict[str, Any]
    error: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Prediction":
        scenario_id = _as_nonempty_str(raw.get("scenario_id"), "prediction.scenario_id")
        run_id = _as_nonempty_str(raw.get("run_id"), "prediction.run_id")
        mode = _as_nonempty_str(raw.get("mode"), "prediction.mode")
        analysis_status = _as_nonempty_str(raw.get("analysis_status"), "prediction.analysis_status")
        analysis_output = raw.get("analysis_output", {})
        safety = raw.get("safety", {})
        provenance = raw.get("provenance", {})
        _require(isinstance(analysis_output, dict), "analysis_output must be an object")
        _require(isinstance(safety, dict), "safety must be an object")
        _require(isinstance(provenance, dict), "provenance must be an object")
        error = raw.get("error")
        _require(error is None or isinstance(error, str), "error must be string or null")
        return cls(
            scenario_id=scenario_id,
            run_id=run_id,
            mode=mode,
            analysis_status=analysis_status,
            analysis_output=analysis_output,
            safety=safety,
            provenance=provenance,
            error=error,
        )


def unique_ids(items: Iterable[Any], attr: str) -> None:
    seen: set[str] = set()
    for item in items:
        value = getattr(item, attr)
        _require(value not in seen, f"duplicate {attr}: {value}")
        seen.add(value)
