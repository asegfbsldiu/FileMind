"""Parallel multi-model runner: order, isolation, and the documented JSON shape."""

import threading
import time
import unittest

from filemind.ai.chat_result import ChatResult
from filemind.ai.model_config import ModelConfig
from filemind.ai.multi_model import run_models


class _FakeProvider:
    def __init__(self, config: ModelConfig, behavior) -> None:
        self.config = config
        self._behavior = behavior

    def chat(self, messages, options=None, cancel_event=None) -> ChatResult:
        return self._behavior(self.config, messages, options)


def _factory(behaviors):
    def factory(config: ModelConfig):
        return _FakeProvider(config, behaviors[config.model])
    return factory


def _ok(config: ModelConfig, text: str = "答案") -> ChatResult:
    return ChatResult(config.provider, config.model, text, 12, None, config.display_name)


class MultiModelRunnerTests(unittest.TestCase):
    def test_results_keep_selection_order_and_isolate_failures(self) -> None:
        configs = [ModelConfig("openai", "gpt-4o", api_key="k"),
                   ModelConfig("deepseek", "deepseek-flash", api_key="k"),
                   ModelConfig("ollama", "qwen2.5:7b")]

        def boom(_config, _messages, _options):
            raise RuntimeError("provider exploded with a private detail")

        factory = _factory({
            "gpt-4o": lambda c, m, o: _ok(c, "first"),
            "deepseek-flash": boom,
            "qwen2.5:7b": lambda c, m, o: _ok(c, "third"),
        })
        result = run_models(configs, [{"role": "user", "content": "hi"}], provider_factory=factory)

        self.assertEqual([item.model for item in result.results],
                         ["gpt-4o", "deepseek-flash", "qwen2.5:7b"])
        self.assertEqual(result.results[0].content, "first")
        self.assertEqual(result.results[2].content, "third")
        self.assertFalse(result.results[1].ok)
        self.assertIn("模型调用失败", result.results[1].error)
        self.assertNotIn("private detail", result.results[1].error)

    def test_disabled_models_are_skipped_and_empty_selection_is_safe(self) -> None:
        configs = [ModelConfig("openai", "on", api_key="k", enabled=True),
                   ModelConfig("openai", "off", api_key="k", enabled=False)]
        factory = _factory({"on": lambda c, m, o: _ok(c)})
        result = run_models(configs, [{"role": "user", "content": "x"}], provider_factory=factory)

        self.assertEqual([item.model for item in result.results], ["on"])
        self.assertEqual(run_models([], [{"role": "user", "content": "x"}],
                                    provider_factory=factory).results, ())

    def test_models_run_in_parallel(self) -> None:
        barrier = threading.Barrier(2, timeout=5)
        configs = [ModelConfig("openai", "a", api_key="k"), ModelConfig("openai", "b", api_key="k")]

        def rendezvous(config, _messages, _options):
            barrier.wait()
            return _ok(config)

        factory = _factory({"a": rendezvous, "b": rendezvous})
        started = time.perf_counter()
        result = run_models(configs, [{"role": "user", "content": "x"}], provider_factory=factory)
        elapsed = time.perf_counter() - started

        self.assertTrue(all(item.ok for item in result.results))
        self.assertLess(elapsed, 3, "模型应当并行而不是依次执行")

    def test_to_dict_matches_the_documented_shape(self) -> None:
        configs = [ModelConfig("openai", "gpt-4o", api_key="k"),
                   ModelConfig("ollama", "qwen2.5:7b")]
        factory = _factory({"gpt-4o": lambda c, m, o: _ok(c, "hi"),
                            "qwen2.5:7b": lambda c, m, o: _ok(c, "你好")})
        payload = run_models(configs, [{"role": "user", "content": "x"}],
                             provider_factory=factory).to_dict()

        self.assertEqual(set(payload), {"results"})
        for row in payload["results"]:
            self.assertEqual(set(row), {"provider", "model", "content", "latency", "error"})
        self.assertEqual(payload["results"][1]["content"], "你好")

    def test_cancelled_selection_returns_cancelled_rows(self) -> None:
        cancel_event = threading.Event()
        cancel_event.set()
        result = run_models([ModelConfig("openai", "a", api_key="k")],
                            [{"role": "user", "content": "x"}], cancel_event=cancel_event,
                            provider_factory=_factory({}))
        self.assertIn("已取消", result.results[0].error)

    def test_configuration_error_is_reported_per_row_without_raising(self) -> None:
        # 空 Base URL 无法构造客户端；错误只落在这一行，不会中断整批调用。
        result = run_models(
            [ModelConfig("custom", "m", api_key="k")],
            [{"role": "user", "content": "x"}],
        )
        self.assertEqual(len(result.results), 1)
        self.assertFalse(result.results[0].ok)
        self.assertIn("API Base URL", result.results[0].error or "")


if __name__ == "__main__":
    unittest.main()
