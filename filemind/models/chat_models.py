"""Typed models for local Orbit conversation history."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4


ChatRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    """One user or assistant turn stored in a local conversation."""

    role: ChatRole
    content: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message_id: str = field(default_factory=lambda: uuid4().hex)
    attachments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChatConversation:
    """A locally persisted Orbit conversation and its display metadata."""

    conversation_id: str = field(default_factory=lambda: uuid4().hex)
    title: str = "新对话"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    messages: tuple[ChatMessage, ...] = ()
