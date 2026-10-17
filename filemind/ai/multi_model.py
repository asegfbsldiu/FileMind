"""Run one chat request across several models in parallel, isolating failures.

Parallel is the default. Results keep the caller's selection order, one model's
exception or timeout is reported on its own row, and the rest are unaffected.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from typing import Callable, Iterable, Mapping

from filemind.ai.adapters import ChatProvider, build_provider, resolve_config, safe_error_message
from filemind.ai.chat_result import ChatResult, MultiModelResult
from filemind.ai.model_config import ModelConfig


DEFAULT_MAX_WORKERS = 4
ProviderFactory = Callable[[ModelConfig], ChatProvider]


def run_models(
    configs: Iterable[ModelConfig],
    messages: list[dict[str, object]],
    options: Mapping[str, object] | None = None,
    cancel_event: Event | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    provider_factory: ProviderFactory = build_provider,
) -> MultiModelResult:
    """Call every enabled model concurrently and return one result per model.

    Ordering follows the input selection; a single provider raising never cancels
    the others, and each failure is reported on its own result row.
    """
    selected = [config for config in configs if config.enabled and config.model.strip()]
    if not selected:
        return MultiModelResult(())
    workers = max(1, min(max_workers, len(selected)))
    results: list[ChatResult | None] = [None] * len(selected)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="filemind-model") as pool:
        submitted = {
            pool.submit(_run_one, config, messages, dict(options or {}), cancel_event,
                        provider_factory): index
            for index, config in enumerate(selected)
        }
        for future, index in submitted.items():
            results[index] = future.result()
    return MultiModelResult(tuple(item for item in results if item is not None))


def _run_one(
    config: ModelConfig,
    messages: list[dict[str, object]],
    options: Mapping[str, object],
    cancel_event: Event | None,
    provider_factory: ProviderFactory,
) -> ChatResult:
    resolved = resolve_config(config)
    if cancel_event is not None and cancel_event.is_set():
        return _failure(resolved, "已取消")
    try:
        provider = provider_factory(config)
    except Exception as error:  # noqa: BLE001 - one model's setup failure is that row's error
        return _failure(resolved, safe_error_message(error))
    try:
        result = provider.chat([dict(message) for message in messages], options, cancel_event)
        if cancel_event is not None and cancel_event.is_set():
            return _failure(resolved, "已取消")
        return replace(result, content=_redact(result.content, resolved.api_key),
                       error=_redact(result.error, resolved.api_key) if result.error else None)
    except InterruptedError:
        return _failure(resolved, "已取消")
    except Exception as error:  # noqa: BLE001 - never let one model break the batch
        return _failure(resolved, safe_error_message(error))


def _failure(config: ModelConfig, message: str) -> ChatResult:
    return ChatResult(config.provider, config.model, "", 0, _redact(message, config.api_key), config.display_name)


def _redact(text: str, key: str) -> str:
    return text.replace(key, "[已隐藏密钥]") if key else text
