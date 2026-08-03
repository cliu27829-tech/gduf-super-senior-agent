from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError, AuthenticationError

from app.core.config import Settings
from app.core.llm_client import (
    LLMAuthenticationError,
    LLMClient,
    LLMNotConfiguredError,
    LLMTimeoutError,
)


class FakeCompletions:
    def __init__(self, *, content: str = "模型回答", error: Exception | None = None):
        self.content = content
        self.error = error
        self.request: dict | None = None

    async def create(self, **kwargs):
        self.request = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def _settings(api_key: str = "test-only-key") -> Settings:
    return Settings(
        deepseek_api_key=api_key,
        deepseek_base_url="https://mock.invalid",
        deepseek_model="deepseek-v4-flash",
    )


def test_llm_client_sends_v4_request_without_exposing_reasoning():
    completions = FakeCompletions()
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client = LLMClient(_settings(), sdk)
    answer = asyncio.run(client.chat_completion([{"role": "user", "content": "你好"}]))
    assert answer == "模型回答"
    assert completions.request["model"] == "deepseek-v4-flash"
    assert completions.request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "api_key" not in completions.request


def test_llm_client_rejects_missing_configuration_before_network():
    client = LLMClient(_settings(api_key=""), SimpleNamespace())
    with pytest.raises(LLMNotConfiguredError):
        asyncio.run(client.chat_completion([{"role": "user", "content": "你好"}]))


def test_llm_client_maps_provider_authentication_and_timeout_errors():
    request = httpx.Request("POST", "https://mock.invalid/chat/completions")
    response = httpx.Response(401, request=request)
    auth_sdk = SimpleNamespace(
        chat=SimpleNamespace(
            completions=FakeCompletions(
                error=AuthenticationError("invalid credentials", response=response, body=None)
            )
        )
    )
    with pytest.raises(LLMAuthenticationError):
        asyncio.run(LLMClient(_settings(), auth_sdk).chat_completion([{"role": "user", "content": "你好"}]))

    timeout_sdk = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions(error=APITimeoutError(request=request)))
    )
    with pytest.raises(LLMTimeoutError):
        asyncio.run(LLMClient(_settings(), timeout_sdk).chat_completion([{"role": "user", "content": "你好"}]))
