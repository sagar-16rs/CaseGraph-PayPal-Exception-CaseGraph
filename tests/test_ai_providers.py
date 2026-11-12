"""Tests for OpenAI and OpenAI-compatible Chat Completions (e.g. DeepSeek) reasoning providers."""

from __future__ import annotations

from dataclasses import replace
import json
import sys
import types

import pytest

from backend.ai.providers.openai import (
    OpenAIReasoningProvider,
    _prefers_chat_completions,
    _strip_code_fence,
)
from backend.config import settings


def _valid_ai_output() -> dict:
    return {
        "summary": "Customer reports non-delivery; request clarification before moving funds.",
        "nodes": [
            {
                "node_id": "F_STATUS",
                "node_type": "VERIFIED_FACT",
                "title": "PayPal dispute status",
                "statement": "WAITING_FOR_SELLER_RESPONSE",
                "source_kind": "PAYPAL_FACT",
                "source_ref": "PF-STATUS",
                "source_revision": 1,
                "source_excerpt": "",
                "confidence": -1.0,
            }
        ],
        "edges": [],
        "recommended_action": {
            "action_type": "SEND_MESSAGE",
            "rationale": "Clarify delivery status first.",
            "requires_human_approval": True,
            "confidence": 0.9,
            "supporting_node_ids": ["F_STATUS"],
        },
        "uncertainties": [],
    }


def test_prefers_chat_completions_detects_deepseek_and_explicit_modes():
    assert _prefers_chat_completions("https://api.deepseek.com", "auto", "auto") is True
    assert _prefers_chat_completions("", "auto", "deepseek") is True
    assert _prefers_chat_completions("", "chat_completions", "openai") is True
    assert _prefers_chat_completions("https://api.deepseek.com", "responses", "openai") is False
    assert _prefers_chat_completions("", "auto", "openai") is False


def test_strip_code_fence_handles_fenced_and_plain_json():
    raw = '{"summary": "ok"}'
    fenced = f"```json\n{raw}\n```"
    assert _strip_code_fence(fenced) == raw
    assert _strip_code_fence(raw) == raw


@pytest.mark.asyncio
async def test_openai_provider_uses_responses_api_by_default(monkeypatch):
    payload_str = json.dumps(_valid_ai_output())
    called = {"responses": 0, "chat": 0}

    class FakeResponses:
        async def create(self, **kwargs):
            called["responses"] += 1
            return types.SimpleNamespace(output_text=payload_str, id="resp-123")

    class FakeChatCompletions:
        async def create(self, **kwargs):
            called["chat"] += 1
            raise AssertionError("chat.completions should not be called")

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()
            self.chat = types.SimpleNamespace(completions=FakeChatCompletions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))
    monkeypatch.setattr(
        "backend.ai.providers.openai.settings",
        replace(settings, openai_api_key="test-key", openai_base_url="", openai_model="gpt-5.6", ai_api_mode="auto"),
    )

    output, prov = await OpenAIReasoningProvider().run({"case_id": "CASE-1"})
    assert called == {"responses": 1, "chat": 0}
    assert output["recommended_action"]["action_type"] == "SEND_MESSAGE"
    assert prov["response_id"] == "resp-123"


@pytest.mark.asyncio
async def test_openai_provider_uses_chat_completions_for_deepseek(monkeypatch):
    fenced_payload = "```json\n" + json.dumps(_valid_ai_output()) + "\n```"
    called = {"responses": 0, "chat": 0}

    class FakeResponses:
        async def create(self, **kwargs):
            called["responses"] += 1
            raise AssertionError("responses should not be called for DeepSeek")

    class FakeChatCompletions:
        async def create(self, **kwargs):
            called["chat"] += 1
            assert kwargs["response_format"] == {"type": "json_object"}
            msg = types.SimpleNamespace(content=fenced_payload)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], id="chatcmpl-456")

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()
            self.chat = types.SimpleNamespace(completions=FakeChatCompletions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))
    monkeypatch.setattr(
        "backend.ai.providers.openai.settings",
        replace(
            settings,
            openai_api_key="deepseek-key",
            openai_base_url="https://api.deepseek.com",
            openai_model="deepseek-chat",
            ai_api_mode="auto",
        ),
    )

    output, prov = await OpenAIReasoningProvider().run({"case_id": "CASE-1"})
    assert called == {"responses": 0, "chat": 1}
    assert output["recommended_action"]["action_type"] == "SEND_MESSAGE"
    assert prov["response_id"] == "chatcmpl-456"
    assert prov["model"] == "deepseek-chat"


@pytest.mark.asyncio
async def test_openai_provider_falls_back_to_chat_completions_when_custom_gateway_lacks_responses(monkeypatch):
    payload_str = json.dumps(_valid_ai_output())
    called = {"responses": 0, "chat": 0}

    class NotFound404(Exception):
        status_code = 404

    class FakeResponses:
        async def create(self, **kwargs):
            called["responses"] += 1
            raise NotFound404("404 /v1/responses not found")

    class FakeChatCompletions:
        async def create(self, **kwargs):
            called["chat"] += 1
            msg = types.SimpleNamespace(content=payload_str)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], id="chatcmpl-fallback")

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()
            self.chat = types.SimpleNamespace(completions=FakeChatCompletions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))
    monkeypatch.setattr(
        "backend.ai.providers.openai.settings",
        replace(
            settings,
            openai_api_key="gateway-key",
            openai_base_url="https://gateway.example.com/v1",
            openai_model="custom-model",
            ai_api_mode="auto",
        ),
    )

    output, prov = await OpenAIReasoningProvider().run({"case_id": "CASE-1"})
    assert called == {"responses": 1, "chat": 1}
    assert output["recommended_action"]["action_type"] == "SEND_MESSAGE"
    assert prov["response_id"] == "chatcmpl-fallback"
