from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError

from backend.ai.bundle import build_analysis_bundle
from backend.ai.prompt import PROMPT_VERSION, prompt_hash
from backend.ai.providers.openai import OpenAIReasoningProvider
from backend.ai.schemas import (
    ANALYSIS_SCHEMA_VERSION,
    AIAnalysisResponse,
    analysis_schema_hash,
)
from backend.casegraph.validate import GraphValidationError, validate_ai_output
from backend.config import settings
from backend.db.models import AIAnalysis
from backend.db.session import session_scope
from backend.evidence.domain import canonical_json_bytes
from backend.repositories import analyses as analysis_repo
from backend.services.graphs import GraphStaleInputError, graph_service
from backend.safety.service import safety_service


class AIRequestConflict(RuntimeError):
    pass


def default_reasoning_provider():
    """Select the configured reasoning provider.

    `CASEGRAPH_AI_PROVIDER` accepts `openai`, `deepseek`, `rules`, or `auto` (default).
    `auto` prefers OpenAI/DeepSeek whenever a key is configured. Without a key it falls
    back to the deterministic reference reasoner — but only outside production,
    where a missing model credential must remain a hard failure rather than a
    silent downgrade in reasoning quality.
    """
    mode = settings.ai_provider
    if mode == "rules":
        from backend.ai.providers.rules import rules_provider

        return rules_provider
    if mode in {"openai", "deepseek"}:
        return OpenAIReasoningProvider()
    if settings.openai_api_key:
        return OpenAIReasoningProvider()
    from backend.security.config import security_config

    if security_config.production:
        return OpenAIReasoningProvider()
    from backend.ai.providers.rules import rules_provider

    return rules_provider


class AIReasoningService:
    def _provider_identity(self, provider: Any) -> tuple[str, str]:
        name = getattr(provider, "provider_name", None)
        model = getattr(provider, "model_name", None)
        if callable(model):
            model = model()
        if not name:
            name = provider.__class__.__name__
        if not model:
            model = settings.openai_model if isinstance(provider, OpenAIReasoningProvider) else "unknown"
        return str(name), str(model)

    def _same_request(
        self,
        row: AIAnalysis,
        *,
        case_id: str,
        bundle_hash: str,
        provider_name: str,
        model_name: str,
    ) -> bool:
        return (
            row.case_id == case_id
            and row.bundle_hash == bundle_hash
            and row.model_provider == provider_name
            and row.model_name == model_name
            and row.prompt_version == PROMPT_VERSION
            and row.prompt_hash == prompt_hash()
            and row.schema_version == ANALYSIS_SCHEMA_VERSION
            and row.schema_hash == analysis_schema_hash()
        )

    def _claim_request(
        self,
        *,
        case_id: str,
        request_id: str,
        requested_by: str,
        bundle: dict[str, Any],
        bundle_hash: str,
        provider_name: str,
        model_name: str,
    ) -> AIAnalysisResponse | str:
        """Claim a model request before network I/O.

        Returns an existing response for an exact idempotent replay, otherwise the
        newly-created analysis UID. The unique request_id constraint closes the
        concurrent double-model-call race.
        """
        with session_scope() as session:
            old = analysis_repo.get_by_request_id(session, request_id)
            if old is not None:
                if not self._same_request(
                    old,
                    case_id=case_id,
                    bundle_hash=bundle_hash,
                    provider_name=provider_name,
                    model_name=model_name,
                ):
                    raise AIRequestConflict(
                        "analysis_request_id was already used with different case/input/model/prompt/schema state"
                    )
                return self._resp(old)

            uid = "AIR-" + uuid.uuid4().hex.upper()
            row = AIAnalysis(
                analysis_uid=uid,
                request_id=request_id,
                case_id=case_id,
                input_case_revision=bundle["case_revision"],
                input_evidence_set_revision=bundle["evidence_set_revision"],
                graph_id=None,
                model_provider=provider_name,
                model_name=model_name,
                prompt_version=PROMPT_VERSION,
                prompt_hash=prompt_hash(),
                schema_version=ANALYSIS_SCHEMA_VERSION,
                schema_hash=analysis_schema_hash(),
                bundle_hash=bundle_hash,
                output_hash=None,
                provider_response_id=None,
                status="RUNNING",
                validation_status="PENDING",
                output_json={},
                error=None,
                requested_by=requested_by,
            )
            session.add(row)
            try:
                session.flush()
            except IntegrityError:
                # The session will roll back on context exit. Resolve the winner in
                # a new transaction outside this context below.
                raise
            return uid

    def _resolve_claim_race(
        self,
        request_id: str,
        *,
        case_id: str,
        bundle_hash: str,
        provider_name: str,
        model_name: str,
    ) -> AIAnalysisResponse:
        with session_scope() as session:
            old = analysis_repo.get_by_request_id(session, request_id)
            if old is None:
                raise RuntimeError("analysis request-id race resolved without a persisted winner")
            if not self._same_request(
                old,
                case_id=case_id,
                bundle_hash=bundle_hash,
                provider_name=provider_name,
                model_name=model_name,
            ):
                raise AIRequestConflict(
                    "analysis_request_id was concurrently used with different inputs"
                )
            return self._resp(old)

    def _finish(
        self,
        analysis_uid: str,
        *,
        status: str,
        validation_status: str,
        output: dict[str, Any],
        output_hash: str | None,
        response_id: str | None,
        graph_id: str | None,
        error: str | None,
    ) -> AIAnalysisResponse:
        with session_scope() as session:
            row = session.query(AIAnalysis).filter_by(analysis_uid=analysis_uid).with_for_update().one()
            # An exact replay that saw RUNNING cannot complete this row. Only the
            # original claimant reaches _finish. Terminal rows are immutable.
            if row.status != "RUNNING":
                return self._resp(row)
            row.status = status
            row.validation_status = validation_status
            row.output_json = output
            row.output_hash = output_hash
            row.provider_response_id = response_id
            row.graph_id = graph_id
            row.error = error
            session.flush()
            return self._resp(row)

    async def analyze(self, case_id: str, req, provider=None) -> AIAnalysisResponse:
        bundle = build_analysis_bundle(case_id)
        bundle_bytes = canonical_json_bytes(bundle)
        if len(bundle_bytes) > settings.ai_max_bundle_chars:
            raise ValueError("analysis bundle exceeds configured maximum")
        bundle_hash = hashlib.sha256(bundle_bytes).hexdigest()

        provider = provider or default_reasoning_provider()
        provider_name, model_name = self._provider_identity(provider)

        try:
            claim = self._claim_request(
                case_id=case_id,
                request_id=req.analysis_request_id,
                requested_by=req.requested_by,
                bundle=bundle,
                bundle_hash=bundle_hash,
                provider_name=provider_name,
                model_name=model_name,
            )
        except IntegrityError:
            return self._resolve_claim_race(
                req.analysis_request_id,
                case_id=case_id,
                bundle_hash=bundle_hash,
                provider_name=provider_name,
                model_name=model_name,
            )

        if isinstance(claim, AIAnalysisResponse):
            return claim
        analysis_uid = claim

        try:
            raw_output, provenance = await provider.run(bundle)
        except Exception as exc:
            return self._finish(
                analysis_uid,
                status="FAILED_PROVIDER",
                validation_status="FAILED",
                output={},
                output_hash=None,
                response_id=None,
                graph_id=None,
                error=f"{type(exc).__name__}: {exc}",
            )

        raw_for_audit = raw_output if isinstance(raw_output, dict) else {"raw_type": type(raw_output).__name__}
        raw_hash = hashlib.sha256(canonical_json_bytes(raw_for_audit)).hexdigest()
        try:
            output = validate_ai_output(bundle, raw_output)
        except Exception as exc:
            status = "FAILED_OUTPUT" if isinstance(exc, (GraphValidationError, ValueError, TypeError)) else "FAILED_COMPILE"
            return self._finish(
                analysis_uid,
                status=status,
                validation_status="FAILED",
                output=raw_for_audit,
                output_hash=raw_hash,
                response_id=provenance.get("response_id"),
                graph_id=None,
                error=f"{type(exc).__name__}: {exc}",
            )

        output_hash = hashlib.sha256(canonical_json_bytes(output)).hexdigest()
        try:
            graph = graph_service.create(
                case_id,
                output["nodes"],
                output["edges"],
                req.requested_by,
                "AI",
                expected_case_revision=bundle["case_revision"],
                expected_evidence_set_revision=bundle["evidence_set_revision"],
            )
        except GraphStaleInputError as exc:
            return self._finish(
                analysis_uid,
                status="STALE_INPUT",
                validation_status="FAILED",
                output=output,
                output_hash=output_hash,
                response_id=provenance.get("response_id"),
                graph_id=None,
                error=str(exc),
            )
        except Exception as exc:
            return self._finish(
                analysis_uid,
                status="FAILED_COMPILE",
                validation_status="FAILED",
                output=output,
                output_hash=output_hash,
                response_id=provenance.get("response_id"),
                graph_id=None,
                error=f"{type(exc).__name__}: {exc}",
            )

        result = self._finish(
            analysis_uid,
            status="COMPLETED",
            validation_status="PASSED",
            output=output,
            output_hash=output_hash,
            response_id=provenance.get("response_id"),
            graph_id=graph["graph_id"],
            error=None,
        )
        safety_service.assess(case_id, analysis_uid)
        return result

    def _resp(self, row: AIAnalysis) -> AIAnalysisResponse:
        return AIAnalysisResponse(
            analysis_uid=row.analysis_uid,
            request_id=row.request_id,
            case_id=row.case_id,
            input_case_revision=row.input_case_revision,
            input_evidence_set_revision=row.input_evidence_set_revision,
            model_provider=row.model_provider,
            model_name=row.model_name,
            prompt_version=row.prompt_version,
            schema_version=row.schema_version,
            schema_hash=row.schema_hash,
            bundle_hash=row.bundle_hash,
            output_hash=row.output_hash,
            provider_response_id=row.provider_response_id,
            status=row.status,
            validation_status=row.validation_status,
            graph_id=row.graph_id,
            output=row.output_json,
            error=row.error,
        )


ai_reasoning_service = AIReasoningService()
