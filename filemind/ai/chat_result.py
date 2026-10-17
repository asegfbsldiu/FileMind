"""Uniform result envelope for single- and multi-model chat calls.

Every provider adapter returns the same ``ChatResult`` shape so the UI and any
future API surface can render grouped results without knowing which vendor was
called. Failures are carried on the row instead of raised, so one broken model
never hides the answers from the others.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatResult:
    """One model's answer, latency, and optional error, never containing a key."""

    provider: str
    model: str
    content: str = ""
    latency_ms: int = 0
    error: str | None = None
    display_name: str = ""

    @property
    def ok(self) -> bool:
        """Return whether this model produced a usable answer."""
        return self.error is None

    @property
    def label(self) -> str:
        """Return the human-readable name for grouped output."""
        return self.display_name or f"{self.provider} · {self.model}"

    def to_dict(self) -> dict[str, object]:
        """Return the documented JSON shape: provider, model, content, latency, error."""
        return {
            "provider": self.provider,
            "model": self.model,
            "content": self.content,
            "latency": self.latency_ms,
            "error": self.error,
        }


@dataclass(frozen=True)
class MultiModelResult:
    """Ordered per-model results from one parallel multi-model request."""

    results: tuple[ChatResult, ...] = ()

    @property
    def succeeded(self) -> tuple[ChatResult, ...]:
        """Return only the models that answered successfully."""
        return tuple(item for item in self.results if item.ok)

    @property
    def failed(self) -> tuple[ChatResult, ...]:
        """Return only the models that failed, keeping their error text."""
        return tuple(item for item in self.results if not item.ok)

    def to_dict(self) -> dict[str, object]:
        """Return ``{"results": [...]}`` as specified for downstream consumers."""
        return {"results": [item.to_dict() for item in self.results]}
