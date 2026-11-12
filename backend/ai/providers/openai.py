from __future__ import annotations

import json
import re
from typing import Any

from backend.ai.prompt import DEVELOPER_INSTRUCTIONS
from backend.ai.schemas import AIOutput, analysis_output_schema
from backend.config import settings

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    match = _FENCE_RE.match(text)
    return match.group(1) if match else text


def _prefers_chat_completions(base_url: str, api_mode: str, provider_mode: str) -> bool:
    mode = (api_mode or "auto").strip().lower()
    if mode in {"chat", "chat_completions", "chat-completions"}:
        return True
    if mode == "responses":
        return False
    if (provider_mode or "").strip().lower() == "deepseek":
        return True
    host = (base_url or "").strip().lower()
    return "deepseek" in host


def _is_unsupported_responses_endpoint(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in {400, 404, 405, 501}:
        return True
    msg = str(exc).lower()
    return any(token in msg for token in ("404", "not found", "/responses", "unsupported"))


class OpenAIReasoningProvider:
    provider_name = "openai"

    @property
    def model_name(self) -> str:
        return settings.openai_model

    async def _run_responses(self, client: Any, serialized_bundle: str) -> tuple[str, str | None]:
        response = await client.responses.create(
            model=settings.openai_model,
            store=False,
            instructions=DEVELOPER_INSTRUCTIONS,
            input=serialized_bundle,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "casegraph_analysis",
                    "strict": True,
                    "schema": analysis_output_schema(),
                }
            },
            max_output_tokens=settings.ai_max_output_tokens,
        )
        raw = getattr(response, "output_text", None)
        if not raw:
            raise ValueError("OpenAI returned no structured analysis output")
        return raw, getattr(response, "id", None)

    async def _run_chat_completions(self, client: Any, serialized_bundle: str) -> tuple[str, str | None]:
        schema_json = json.dumps(analysis_output_schema(), sort_keys=True, separators=(",", ":"))
        system_prompt = (
            f"{DEVELOPER_INSTRUCTIONS}\n\n"
            "Return ONLY a single valid JSON object matching this exact JSON Schema "
            f"(no markdown fences, no commentary):\n{schema_json}"
        )
        completion = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": serialized_bundle},
            ],
            response_format={"type": "json_object"},
            max_tokens=settings.ai_max_output_tokens,
            temperature=0,
        )
        choices = getattr(completion, "choices", None) or []
        first = choices[0] if choices else None
        message = getattr(first, "message", None) if first is not None else None
        raw = getattr(message, "content", None)
        if not raw:
            raise ValueError("OpenAI-compatible chat completion returned no structured analysis output")
        return _strip_code_fence(raw), getattr(completion, "id", None)

    async def run(self, bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.ai_timeout_seconds,
        )
        serialized_bundle = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
        api_mode = getattr(settings, "ai_api_mode", "auto")
        use_chat = _prefers_chat_completions(
            settings.openai_base_url,
            api_mode,
            settings.ai_provider,
        )

        if use_chat:
            raw, response_id = await self._run_chat_completions(client, serialized_bundle)
        else:
            try:
                raw, response_id = await self._run_responses(client, serialized_bundle)
            except Exception as exc:
                # If `CASEGRAPH_AI_API_MODE=auto` is pointed at a custom base URL
                # that only serves `/v1/chat/completions` (such as DeepSeek or an
                # OpenAI-compatible proxy), fall back cleanly to chat completions.
                if (
                    api_mode == "auto"
                    and settings.openai_base_url
                    and _is_unsupported_responses_endpoint(exc)
                ):
                    raw, response_id = await self._run_chat_completions(client, serialized_bundle)
                else:
                    raise

        # Refusals or truncated responses must never be interpreted as valid graph
        # data. Parsing + Pydantic validation remains mandatory even when the
        # provider was asked for strict Structured Outputs or JSON mode.
        parsed = json.loads(raw)
        validated = AIOutput.model_validate(parsed)
        return validated.model_dump(mode="json"), {
            "provider": self.provider_name,
            "model": settings.openai_model,
            "response_id": response_id,
        }
