"""OpenAI SDK adapter for compatible Chat Completions providers."""

from __future__ import annotations

import logging
from threading import Event
from typing import Iterator
from urllib.parse import urlsplit

from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, BadRequestError
from openai import NotFoundError, OpenAI, RateLimitError

from filemind.ai.prompts import SYSTEM_PROMPT, build_organize_prompt, build_organize_content
from filemind.ai.response import parse_partial_file_suggestions
from filemind.ai.schemas import AIBatchFailure, AIFileMetadata, AIOrganizationResult, file_metadata
from filemind.ai.base import ProgressCallback
from filemind.ai.providers import is_local_connection
from filemind.models import FileInfo, FileSuggestion
from filemind.storage.settings import AISettings


MAX_BATCH_FILES = 16
MAX_BATCH_CHARS = 12_000
MAX_RULE_LENGTH = 2_000
LOGGER = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    """Safe-to-display provider error without request or credential contents."""


class OpenAICompatibleClient:
    """Use one synchronous OpenAI SDK client from a non-UI worker thread."""

    def __init__(self, settings: AISettings) -> None:
        validate_connection_settings(settings)
        self.settings = settings
        self.client = OpenAI(api_key=settings.api_key or "ollama", base_url=settings.base_url,
                             timeout=settings.timeout_seconds, max_retries=0)

    def test_connection(self) -> str:
        """Send a real minimal chat request and return the provider model name."""
        try:
            response = self.client.chat.completions.create(
                model=self.settings.model,
                messages=[{"role": "user", "content": "Reply with the single word OK."}],
                max_tokens=16,
            )
        except Exception as error:
            _log_provider_failure(self.settings, error)
            raise _friendly_error(error) from None
        return str(getattr(response, "model", "") or self.settings.model)

    def complete_chat(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        cancel_event: Event | None = None,
    ) -> str:
        """Send one independent chat request and discard results after cancellation."""
        request_messages = [{"role": "system", "content": system_prompt}, *messages]
        return self.complete(request_messages, cancel_event)

    def complete(self, messages: list[dict[str, object]], cancel_event: Event | None = None) -> str:
        """Send an adapter request while preserving the existing chat API."""
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("生成已停止")
        try:
            response = self.client.chat.completions.create(
                model=self.settings.model,
                messages=messages,
            )
        except Exception as error:
            _log_provider_failure(self.settings, error)
            raise _friendly_error(error) from None
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("生成已停止")
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise AIServiceError("服务返回了空回答，请重试。")
        return content

    def stream(self, messages: list[dict[str, object]],
               cancel_event: Event | None = None) -> Iterator[str]:
        """Yield only answer text and close the SDK stream on cancellation."""
        response_stream = None
        try:
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("生成已停止")
            response_stream = self.client.chat.completions.create(
                model=self.settings.model, messages=messages, stream=True)
            for chunk in response_stream:
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("生成已停止")
                choices = getattr(chunk, "choices", ()) or ()
                text = getattr(choices[0].delta, "content", None) if choices else None
                if text:
                    yield text
        except InterruptedError:
            raise
        except Exception as error:
            _log_provider_failure(self.settings, error)
            raise _friendly_error(error) from None
        finally:
            if response_stream is not None:
                response_stream.close()

    def organize_files(
        self,
        files: list[AIFileMetadata],
        user_rule: str,
        rename_enabled: bool,
        on_progress: ProgressCallback | None = None,
        cancel_event: Event | None = None,
    ) -> AIOrganizationResult:
        """Request suggestions in bounded batches and preserve explicit failures."""
        if not user_rule.strip():
            user_rule = "根据文件名和扩展名进行清晰、保守的分类；不确定时放入其他并保留原名。"
        if len(user_rule) > MAX_RULE_LENGTH:
            raise ValueError(f"整理规则不能超过 {MAX_RULE_LENGTH} 个字符")
        batches = _make_batches(files, user_rule, rename_enabled)
        suggestions: dict[str, FileSuggestion] = {}
        failures: list[AIBatchFailure] = []
        completed = 0
        for batch_index, batch in enumerate(batches):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("AI 整理已取消")
            batch_map = {item.file_id: _as_file_info(item) for item in batch}
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_organize_content(batch, user_rule, rename_enabled)},
                    ],
                )
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("AI 整理已取消")
                response_text = response.choices[0].message.content or ""
                parsed, item_failures = parse_partial_file_suggestions(response_text, batch_map, rename_enabled)
                suggestions.update(parsed)
                failures.extend(AIBatchFailure((identifier,), message)
                                for identifier, message in item_failures.items())
            except InterruptedError:
                raise
            except Exception as error:
                failures.append(AIBatchFailure(tuple(item.file_id for item in batch), _safe_batch_error(error)))
                if _is_fatal_provider_error(error):
                    remaining = [item for later in batches[batch_index + 1:] for item in later]
                    if remaining:
                        failures.append(AIBatchFailure(tuple(item.file_id for item in remaining), _safe_batch_error(error)))
                    break
            completed += len(batch)
            if on_progress:
                on_progress(completed, len(files))
        return AIOrganizationResult(suggestions, tuple(failures))


def validate_connection_settings(settings: AISettings) -> None:
    """Reject malformed or unsafe connection settings before SDK construction."""
    if settings.provider_id == "ollama" and not is_local_connection(settings.provider_id, settings.base_url):
        raise ValueError("本地 Ollama 仅允许本机回环地址；远程服务请使用自定义兼容接口。")
    if not settings.api_key.strip() and not is_local_connection(settings.provider_id, settings.base_url):
        raise ValueError("请先填写 API Key。")
    parsed = urlsplit(settings.base_url.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("API Base URL 必须是完整的 HTTP 或 HTTPS 地址。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API Base URL 不能包含账号、密码、查询参数或片段。")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("远程 API 必须使用 HTTPS；HTTP 仅允许本机模型地址。")
    if not settings.model.strip():
        raise ValueError("请填写模型名称。")
    if not 5 <= settings.timeout_seconds <= 180:
        raise ValueError("请求超时时间必须在 5 到 180 秒之间。")


def _make_batches(
    files: list[AIFileMetadata], user_rule: str, rename_enabled: bool
) -> list[list[AIFileMetadata]]:
    batches: list[list[AIFileMetadata]] = []
    current: list[AIFileMetadata] = []
    for item in files:
        if len(build_organize_prompt([item], user_rule, rename_enabled)) > MAX_BATCH_CHARS or len(item.image_data_url) > 512 * 1024 + 64:
            raise ValueError("单个文件的请求数据超出上限，请缩短规则或减少内容。")
        candidate = current + [item]
        encoded = build_organize_prompt(candidate, user_rule, rename_enabled)
        if len(candidate) > MAX_BATCH_FILES or len(encoded) > MAX_BATCH_CHARS or sum(bool(value.image_data_url) for value in candidate) > 4:
            if not current:
                raise ValueError(f"文件名过长，无法安全发送给模型：{item.file_name[:80]}")
            batches.append(current)
            current = [item]
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


def _as_file_info(item: AIFileMetadata) -> FileInfo:
    """Create the path-free adapter expected by the strict response validator."""
    from pathlib import Path

    return FileInfo(Path(item.file_name), item.size_bytes, item.modified_ns)


def _friendly_error(error: Exception) -> AIServiceError:
    if isinstance(error, AuthenticationError):
        message = "API Key 无效或无权访问此服务。"
    elif isinstance(error, APIStatusError) and error.status_code == 403:
        message = "服务拒绝访问（403），请检查账号权限、模型授权或服务区域。"
    elif isinstance(error, RateLimitError):
        message = "请求受限（429），请检查调用频率、额度不足或账户余额。"
    elif isinstance(error, APITimeoutError):
        message = "请求超时，请检查网络或适当提高超时时间。"
    elif isinstance(error, NotFoundError):
        message = "接口地址或模型不存在，请检查 Base URL 与模型名称。"
    elif isinstance(error, BadRequestError):
        message = "服务商拒绝了请求，请检查模型是否支持 Chat Completions 及请求格式。"
    elif isinstance(error, APIConnectionError):
        message = _connection_error_message(error)
    elif isinstance(error, APIStatusError):
        message = _status_error_message(error.status_code)
    else:
        message = "模型请求失败，请检查配置后重试。"
    return AIServiceError(message)


def _connection_error_message(error: APIConnectionError) -> str:
    causes = list(_exception_chain(error))
    names = {type(cause).__name__.lower() for cause in causes}
    modules = {type(cause).__module__.lower() for cause in causes}
    if any("proxy" in name for name in names):
        return "代理连接失败，请检查代理地址和代理服务状态。"
    if any("ssl" in name or "tls" in name for name in names) or any(
        module == "ssl" for module in modules
    ):
        return "TLS 安全连接失败，请检查系统时间、证书和 HTTPS 代理设置。"
    if any(name == "gaierror" for name in names):
        return "DNS 解析失败，请检查网络连接和域名解析。"
    return "无法连接服务商，网络连接失败；请检查网络、DNS、Base URL 和代理设置。"


def _exception_chain(error: BaseException) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return tuple(chain)


def _status_error_message(status_code: int) -> str:
    if status_code >= 500:
        return f"服务商服务器异常（HTTP {status_code}），请稍后重试。"
    if status_code == 402:
        return "服务商账户余额或付款状态异常（HTTP 402），请检查账户。"
    return f"服务商返回 HTTP {status_code}，请检查配置和账户权限。"


def _log_provider_failure(settings: AISettings, error: Exception) -> None:
    status = error.status_code if isinstance(error, APIStatusError) else "-"
    LOGGER.warning("AI request failed provider=%s error_type=%s http_status=%s",
                   settings.provider_id, type(error).__name__, status)


def _safe_batch_error(error: Exception) -> str:
    if isinstance(error, ValueError):
        return str(error)
    return str(_friendly_error(error))


def _is_fatal_provider_error(error: Exception) -> bool:
    return isinstance(error, (AuthenticationError, NotFoundError, BadRequestError, APIConnectionError,
                              APITimeoutError, APIStatusError))
