"""Unified chat interface over OpenAI-compatible and Ollama providers.

Business code depends only on ``ChatProvider.chat`` and ``ChatResult``; vendor
specifics (the OpenAI SDK, Ollama's native ``/api/tags`` listing) live here so
no feature module writes per-provider request logic. The ``unsupported`` preset
kind remains available for future native adapters (for example Anthropic or
Google) and fails with a clear message until such an adapter is added.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import replace
from threading import Event
from typing import Iterator, Mapping, Protocol

from filemind.ai.chat_result import ChatResult
from filemind.ai.model_config import DEFAULT_TIMEOUT_SECONDS, ModelConfig
from filemind.ai.openai_compatible import AIServiceError, OpenAICompatibleClient
from filemind.ai.providers import PROVIDER_BY_ID, ProviderPreset, is_local_connection
from filemind.storage.settings import AISettings


def resolve_config(config: ModelConfig) -> ModelConfig:
    """Fill in preset defaults and the placeholder Ollama key without persisting them."""
    preset = PROVIDER_BY_ID.get(config.provider)
    base_url = config.base_url.strip() or (preset.base_url if preset else "")
    api_key = config.api_key
    if not api_key and is_local_connection(config.provider, base_url):
        api_key = "ollama"
    timeout = config.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    return replace(config, base_url=base_url, api_key=api_key, timeout_seconds=timeout)


def safe_error_message(error: BaseException) -> str:
    """Return a provider-safe message without leaking keys or request internals."""
    if isinstance(error, (AIServiceError, ValueError)):
        return str(error)
    return "模型调用失败，请检查配置后重试。"


class ChatProvider(Protocol):
    """The single contract every vendor adapter implements."""

    config: ModelConfig

    def chat(self, messages: list[dict[str, object]],
             options: Mapping[str, object] | None = None,
             cancel_event: Event | None = None) -> ChatResult: ...

    def chat_stream(self, messages: list[dict[str, object]],
                    options: Mapping[str, object] | None = None,
                    cancel_event: Event | None = None) -> Iterator[str]: ...

    def list_models(self) -> list[str]: ...

    def test_connection(self) -> str: ...


class OpenAIProvider:
    """Adapter for any OpenAI Chat Completions compatible endpoint."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = resolve_config(config)
        self._client = OpenAICompatibleClient(AISettings(
            self.config.provider, self.config.base_url, self.config.model,
            self.config.timeout_seconds, self.config.api_key,
        ))

    def chat(self, messages: list[dict[str, object]],
             options: Mapping[str, object] | None = None,
             cancel_event: Event | None = None) -> ChatResult:
        request = _with_options(messages, options)
        started = time.perf_counter()
        try:
            content = self._client.complete(request, cancel_event)
            return _result(self.config, content, started)
        except InterruptedError:
            raise
        except Exception as error:  # noqa: BLE001 - convert any vendor error to a row
            return _error_result(self.config, started, safe_error_message(error))

    def chat_stream(self, messages: list[dict[str, object]],
                    options: Mapping[str, object] | None = None,
                    cancel_event: Event | None = None) -> Iterator[str]:
        yield from self._client.stream(_with_options(messages, options), cancel_event)

    def list_models(self) -> list[str]:
        """A generic OpenAI endpoint cannot enumerate models reliably."""
        return [self.config.model]

    def test_connection(self) -> str:
        return self._client.test_connection()


class OllamaProvider(OpenAIProvider):
    """Local Ollama over its OpenAI-compatible ``/v1`` endpoint plus native tags."""

    def list_models(self) -> list[str]:
        """Return installed local models via ``GET /api/tags`` with friendly errors."""
        url = f"{_ollama_root(self.config.base_url)}/api/tags"
        try:
            payload = _fetch_ollama_tags(url, min(self.config.timeout_seconds, 15))
        except AIServiceError:
            raise
        except Exception as error:  # noqa: BLE001 - one safe message for any failure
            raise AIServiceError("无法连接本机 Ollama，请确认已运行 ollama serve 并检查本机地址。") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise AIServiceError("Ollama 模型列表响应格式无效。")
        models = payload["models"]
        names = [str(item.get("name")).strip() for item in models
                 if isinstance(item, dict) and item.get("name")]
        # Ollama shows ":latest" for untagged models; OpenAI-compat calls accept the bare name.
        return [name[:-7] if name.endswith(":latest") else name for name in names if name]


def build_provider(config: ModelConfig, preset: ProviderPreset | None = None) -> ChatProvider:
    """Create the adapter for one config, raising a clear error for reserved slots."""
    resolved = resolve_config(config)
    preset = preset or PROVIDER_BY_ID.get(resolved.provider)
    kind = preset.kind if preset else "openai"
    if kind == "unsupported":
        name = preset.name if preset else resolved.provider
        raise AIServiceError(f"{name} 暂未接入原生调用；请改用自定义 OpenAI 兼容端点。")
    if kind == "ollama":
        return OllamaProvider(resolved)
    return OpenAIProvider(resolved)


def _fetch_ollama_tags(url: str, timeout: int) -> object:
    """Fetch and decode the native tags document; isolated so tests can patch it."""
    if not is_local_connection("ollama", url):
        raise AIServiceError("模型检测仅允许连接本机 Ollama。")
    request = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        content = response.read(1_000_001)
        if len(content) > 1_000_000:
            raise AIServiceError("Ollama 模型列表过大。")
        return json.loads(content.decode("utf-8"))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep a local discovery request from following redirects off this machine."""

    def redirect_request(self, req: urllib.request.Request, fp: object, code: int,
                         msg: str, headers: object, newurl: str) -> None:
        raise AIServiceError("本机 Ollama 返回了重定向；请检查地址配置。")


def _ollama_root(base_url: str) -> str:
    """Strip a trailing ``/v1`` so the native API root is used for tags."""
    root = base_url.strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return root or "http://localhost:11434"


def _with_options(messages: list[dict[str, object]],
                  options: Mapping[str, object] | None) -> list[dict[str, object]]:
    request = [dict(message) for message in messages]
    system = str((options or {}).get("system", "")).strip()
    if system:
        request.insert(0, {"role": "system", "content": system})
    return request


def _result(config: ModelConfig, content: str, started: float) -> ChatResult:
    return ChatResult(config.provider, config.model, content, _elapsed_ms(started),
                      None, config.display_name)


def _error_result(config: ModelConfig, started: float, message: str) -> ChatResult:
    return ChatResult(config.provider, config.model, "", _elapsed_ms(started),
                      message, config.display_name)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
