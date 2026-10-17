"""Selectable model entries shared by the settings store, providers, and UI.

A single ``ModelConfig`` is the unit the user can enable, order, and remove in
the multi-model selector. Secrets are never part of the persisted shape: only
``api_key_env`` (an environment variable *name*) is stored, and the resolved
``api_key`` lives in memory for the duration of one request.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace


DEFAULT_TIMEOUT_SECONDS = 45


@dataclass(frozen=True)
class ModelConfig:
    """One selectable model, optionally scoped to a provider profile."""

    provider: str
    model: str
    base_url: str = ""
    api_key_env: str = ""
    display_name: str = ""
    enabled: bool = True
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    api_key: str = field(default="", repr=False, compare=False)

    @property
    def identity(self) -> str:
        """Return the stable ``provider/model`` key used for de-duplication."""
        return f"{self.provider}/{self.model}"

    @property
    def label(self) -> str:
        """Return the human-readable name shown in selectors and result headers."""
        return self.display_name or f"{self.provider} · {self.model}"

    def to_dict(self) -> dict[str, object]:
        """Serialize only persisted fields; the resolved API key is never written."""
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
        }

    def with_api_key(self, api_key: str) -> "ModelConfig":
        """Return a copy carrying a resolved secret without mutating the original."""
        return replace(self, api_key=api_key)

    @classmethod
    def from_dict(cls, raw: object) -> "ModelConfig | None":
        """Decode one persisted entry, ignoring unknown or malformed values."""
        if not isinstance(raw, dict):
            return None
        provider = raw.get("provider", "")
        model = raw.get("model", "")
        if not isinstance(provider, str) or not isinstance(model, str):
            return None
        provider, model = provider.strip(), model.strip()
        if not provider or not model:
            return None
        return cls(
            provider=provider,
            model=model,
            base_url=str(raw.get("base_url", "")).strip(),
            api_key_env=str(raw.get("api_key_env", "")).strip(),
            display_name=str(raw.get("display_name", "")).strip(),
            enabled=raw.get("enabled", True) is True,
            timeout_seconds=_valid_timeout(raw.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
        )


def _valid_timeout(value: object) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return min(max(timeout, 5), 180)
