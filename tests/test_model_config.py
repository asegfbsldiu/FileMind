"""ModelConfig persistence shape: keys never stored, malformed rows ignored."""

import unittest

from filemind.ai.model_config import ModelConfig


class ModelConfigTests(unittest.TestCase):
    def test_to_dict_omits_the_resolved_api_key(self) -> None:
        config = ModelConfig("deepseek", "deepseek-flash", base_url="https://api.deepseek.com",
                             api_key="super-secret")
        payload = config.to_dict()

        self.assertNotIn("api_key", payload)
        self.assertNotIn("super-secret", repr(payload))
        self.assertEqual(payload["provider"], "deepseek")
        self.assertEqual(payload["model"], "deepseek-flash")

    def test_round_trip_preserves_every_persisted_field(self) -> None:
        config = ModelConfig("ollama", "qwen2.5:7b", base_url="http://localhost:11434/v1",
                             api_key_env="OLLAMA_API_KEY", display_name="本机 Qwen",
                             enabled=False, timeout_seconds=20)
        restored = ModelConfig.from_dict(config.to_dict())

        self.assertEqual(restored.to_dict(), config.to_dict())
        self.assertEqual(restored, config)

    def test_from_dict_rejects_rows_without_provider_or_model(self) -> None:
        for raw in ({}, {"provider": "openai"}, {"model": "gpt-4o"}, "not-a-dict", None):
            with self.subTest(raw=raw):
                self.assertIsNone(ModelConfig.from_dict(raw))

    def test_from_dict_clamps_timeout_and_defaults_enabled(self) -> None:
        restored = ModelConfig.from_dict({"provider": "openai", "model": "gpt-4o",
                                          "timeout_seconds": 9999})
        self.assertEqual(restored.timeout_seconds, 180)
        self.assertTrue(restored.enabled)

    def test_label_and_identity(self) -> None:
        config = ModelConfig("openai", "gpt-4o")
        self.assertEqual(config.identity, "openai/gpt-4o")
        self.assertEqual(config.label, "openai · gpt-4o")
        self.assertEqual(ModelConfig("openai", "gpt-4o", display_name="主力").label, "主力")


if __name__ == "__main__":
    unittest.main()
