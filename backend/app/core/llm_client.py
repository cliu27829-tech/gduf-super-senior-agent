from __future__ import annotations

from functools import lru_cache
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)

from app.core.config import Settings, get_settings


logger = logging.getLogger("gduf-api.llm")


class LLMClientError(RuntimeError):
    def __init__(self, public_message: str, status_code: int, *, error_id: str | None = None):
        super().__init__(public_message)
        self.public_message = public_message
        self.status_code = status_code
        self.error_id = error_id or uuid4().hex[:12]


class LLMNotConfiguredError(LLMClientError):
    def __init__(self):
        super().__init__("后端已连接，但尚未配置大模型密钥。", 503)


class LLMAuthenticationError(LLMClientError):
    def __init__(self):
        super().__init__("大模型认证失败，请检查后端密钥是否有效。", 502)


class LLMRateLimitError(LLMClientError):
    def __init__(self):
        super().__init__("大模型请求过于频繁，请稍后重试。", 429)


class LLMTimeoutError(LLMClientError):
    def __init__(self):
        super().__init__("大模型响应超时，请稍后重试。", 504)


class LLMProviderError(LLMClientError):
    def __init__(self):
        super().__init__("大模型服务暂时不可用，请稍后重试。", 502)


class LLMClient:
    def __init__(self, settings: Settings | None = None, openai_client: Any | None = None):
        self.settings = settings or get_settings()
        self._client = openai_client

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.deepseek_api_key.strip()
            and self.settings.deepseek_base_url.strip()
            and self.settings.deepseek_model.strip()
        )

    @property
    def model(self) -> str:
        return self.settings.deepseek_model

    def _get_client(self) -> Any:
        if self._client is None:
            timeout = httpx.Timeout(
                self.settings.llm_read_timeout_seconds,
                connect=self.settings.llm_connect_timeout_seconds,
            )
            self._client = AsyncOpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                timeout=timeout,
                max_retries=self.settings.llm_max_retries,
            )
        return self._client

    def _request(self, messages: list[dict[str, Any]], response_format: dict[str, str] | None = None) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 1800,
            "extra_body": {
                "thinking": {"type": "enabled" if self.settings.deepseek_thinking_enabled else "disabled"}
            },
        }
        if self.settings.deepseek_thinking_enabled:
            request["reasoning_effort"] = self.settings.deepseek_reasoning_effort
        else:
            request["temperature"] = 0.6
        if response_format:
            request["response_format"] = response_format
        return request

    @staticmethod
    def _log_failure(event: str, error: LLMClientError, exc: Exception) -> None:
        logger.warning(
            "%s error_id=%s error_type=%s",
            event,
            error.error_id,
            type(exc).__name__,
        )

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.6,
        *,
        response_format: dict[str, str] | None = None,
    ) -> str:
        if not self.configured:
            raise LLMNotConfiguredError()

        request = self._request(messages, response_format)
        if not self.settings.deepseek_thinking_enabled:
            request["temperature"] = temperature

        try:
            response = await self._get_client().chat.completions.create(**request)
        except AuthenticationError as exc:
            error = LLMAuthenticationError()
            self._log_failure("llm_authentication_failed", error, exc)
            raise error from exc
        except RateLimitError as exc:
            error = LLMRateLimitError()
            self._log_failure("llm_rate_limited", error, exc)
            raise error from exc
        except APITimeoutError as exc:
            error = LLMTimeoutError()
            self._log_failure("llm_timeout", error, exc)
            raise error from exc
        except (APIConnectionError, APIStatusError) as exc:
            error = LLMProviderError()
            self._log_failure("llm_provider_failed", error, exc)
            raise error from exc

        content = response.choices[0].message.content if response.choices else None
        if not content or not content.strip():
            error = LLMProviderError()
            logger.warning("llm_empty_response error_id=%s", error.error_id)
            raise error
        return content.strip()

    async def stream_completion(self, messages: list[dict[str, Any]]) -> AsyncIterator[str]:
        """Yield only user-visible content; reasoning_content is deliberately discarded."""
        if not self.configured:
            raise LLMNotConfiguredError()
        request = self._request(messages)
        request["stream"] = True
        try:
            stream = await self._get_client().chat.completions.create(**request)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                content = getattr(chunk.choices[0].delta, "content", None)
                if content:
                    yield content
        except AuthenticationError as exc:
            error = LLMAuthenticationError()
            self._log_failure("llm_authentication_failed", error, exc)
            raise error from exc
        except RateLimitError as exc:
            error = LLMRateLimitError()
            self._log_failure("llm_rate_limited", error, exc)
            raise error from exc
        except APITimeoutError as exc:
            error = LLMTimeoutError()
            self._log_failure("llm_timeout", error, exc)
            raise error from exc
        except (APIConnectionError, APIStatusError) as exc:
            error = LLMProviderError()
            self._log_failure("llm_provider_failed", error, exc)
            raise error from exc


@lru_cache
def get_llm_client() -> LLMClient:
    return LLMClient()
