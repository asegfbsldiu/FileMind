"""Settings persistence for the ordered multi-model selection."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from filemind.ai.model_config import ModelConfig
from filemind.storage.settings import AISettings, SettingsStore


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, target: str) -> str | None:
        return self.values.get(target)

    def set(self, target: str, value: str) -> None:
        self.values[target] = value

    def delete(self, target: str) -> None:
        self.values.pop(target, None)


class MultiModelSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = SettingsStore(self.root / "settings.json", self.root, MemorySecretStore())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_save_and_reload_preserves_order_and_enabled_flags_without_keys(self) -> None:
        models = [
            ModelConfig("openai", "gpt-4o", api_key="must-not-persist"),
            ModelConfig("ollama", "qwen2.5:7b"),
            ModelConfig("deepseek", "deepseek-flash", enabled=False),
        ]
        self.store.save_models(models)

        raw = (self.root / "settings.json").read_text(encoding="utf-8")
        self.assertNotIn("must-not-persist", raw)

        loaded = SettingsStore(self.root / "settings.json", self.root, MemorySecretStore()).load_models()
        self.assertEqual([item.identity for item in loaded],
                         ["openai/gpt-4o", "ollama/qwen2.5:7b", "deepseek/deepseek-flash"])
        self.assertEqual([item.enabled for item in loaded], [True, True, False])
        self.assertEqual(loaded[0].api_key, "")

    def test_missing_list_falls_back_to_the_single_active_profile(self) -> None:
        self.store.save(AISettings("openai", "https://api.openai.com/v1", "gpt-4o", 30, "user-key"))

        loaded = self.store.load_models()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].identity, "openai/gpt-4o")
        self.assertEqual(loaded[0].api_key, "user-key")

    def test_api_key_env_name_is_used_to_resolve_the_secret(self) -> None:
        self.store.save_models([ModelConfig("openai", "gpt-4o", api_key_env="OPENAI_API_KEY")])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-provided"}):
            loaded = self.store.load_models()

        self.assertEqual(loaded[0].api_key, "env-provided")
        self.assertNotIn("env-provided", (self.root / "settings.json").read_text(encoding="utf-8"))

    def test_parallel_mode_defaults_off_and_can_be_toggled(self) -> None:
        self.assertFalse(self.store.is_parallel_mode_enabled())
        self.store.set_parallel_mode(True)
        self.assertTrue(self.store.is_parallel_mode_enabled())
        self.assertTrue(json.loads((self.root / "settings.json").read_text(encoding="utf-8"))["parallel_models"])


if __name__ == "__main__":
    unittest.main()
