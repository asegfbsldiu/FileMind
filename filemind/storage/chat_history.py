"""Atomic local persistence for Orbit conversations, separate from file history."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from filemind.chat_models import ChatConversation, ChatMessage
from filemind.storage.paths import config_dir


MAX_CONVERSATIONS = 200
MAX_MESSAGE_LENGTH = 20_000


class ChatHistoryError(RuntimeError):
    """A chat history read or write failed without exposing model credentials."""


class ChatHistoryStore:
    """Store only Orbit message content and timestamps in the user's app data."""

    def __init__(self, history_path: Path | None = None) -> None:
        self.history_path = history_path or _default_history_path()
        self._lock = RLock()

    def list_conversations(self) -> list[ChatConversation]:
        """Return conversations ordered by most recently updated."""
        with self._lock:
            return sorted(self._read().values(), key=lambda item: item.updated_at, reverse=True)

    def get_conversation(self, conversation_id: str) -> ChatConversation | None:
        """Return a conversation by ID, if it still exists."""
        with self._lock:
            return self._read().get(conversation_id)

    def create_conversation(self) -> ChatConversation:
        """Create an empty local conversation and enforce the history cap."""
        with self._lock:
            records = self._read()
            conversation = ChatConversation()
            records[conversation.conversation_id] = conversation
            self._write(_trim_conversations(records))
            return conversation

    def add_message(self, conversation_id: str, role: str, content: str,
                    attachments: tuple[str, ...] = ()) -> ChatConversation:
        """Append a user or assistant message and update the visible title."""
        text = content.strip()
        if role not in {"user", "assistant"} or not text:
            raise ValueError("消息角色或内容无效。")
        if len(text) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"单条消息不能超过 {MAX_MESSAGE_LENGTH} 个字符。")
        with self._lock:
            records = self._read()
            conversation = records.get(conversation_id)
            if conversation is None:
                raise ChatHistoryError("这段对话已不存在。")
            message = ChatMessage(role=role, content=text,
                                  attachments=tuple(_safe_attachment_name(name) for name in attachments))
            messages = conversation.messages + (message,)
            title = _conversation_title(conversation.title, role, text)
            updated = ChatConversation(conversation_id, title, conversation.created_at,
                                       message.created_at, messages)
            records[conversation_id] = updated
            self._write(records)
            return updated

    def delete_conversation(self, conversation_id: str) -> None:
        """Delete one local conversation without touching file-operation history."""
        with self._lock:
            records = self._read()
            records.pop(conversation_id, None)
            self._write(records)

    def _read(self) -> dict[str, ChatConversation]:
        try:
            payload = json.loads(self.history_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as error:
            raise ChatHistoryError("本地对话记录无法读取。") from error
        if not isinstance(payload, list):
            raise ChatHistoryError("本地对话记录格式无效。")
        return {item.conversation_id: item for raw in payload if (item := _decode_conversation(raw))}

    def _write(self, records: dict[str, ChatConversation]) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [_encode_conversation(item) for item in records.values()]
        handle, temporary = tempfile.mkstemp(prefix=".orbit-chat-", suffix=".tmp",
                                             dir=self.history_path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.history_path)
        except OSError as error:
            raise ChatHistoryError("本地对话记录无法保存。") from error
        finally:
            Path(temporary).unlink(missing_ok=True)


def _default_history_path() -> Path:
    return config_dir() / "chat_history.json"


def _conversation_title(current: str, role: str, content: str) -> str:
    if current != "新对话" or role != "user":
        return current
    return content.replace("\n", " ").strip()[:32] or "新对话"


def _decode_conversation(raw: object) -> ChatConversation | None:
    if not isinstance(raw, dict):
        return None
    try:
        messages = tuple(
            ChatMessage(str(item["role"]), str(item["content"]), str(item["created_at"]),
                        str(item["message_id"]),
                        tuple(str(name) for name in item.get("attachments", []) if isinstance(name, str)))
            for item in raw["messages"]
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str) and len(item["content"]) <= MAX_MESSAGE_LENGTH
        )
        return ChatConversation(str(raw["conversation_id"]), str(raw["title"]),
                                str(raw["created_at"]), str(raw["updated_at"]), messages)
    except (KeyError, TypeError):
        return None


def _encode_conversation(conversation: ChatConversation) -> dict[str, object]:
    return {
        "conversation_id": conversation.conversation_id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "messages": [
            {"message_id": item.message_id, "role": item.role,
             "content": item.content, "created_at": item.created_at,
             "attachments": list(item.attachments)}
            for item in conversation.messages
        ],
    }


def _trim_conversations(records: dict[str, ChatConversation]) -> dict[str, ChatConversation]:
    recent = sorted(records.values(), key=lambda item: item.updated_at, reverse=True)[:MAX_CONVERSATIONS]
    return {item.conversation_id: item for item in recent}


def _safe_attachment_name(name: str) -> str:
    """Persist only a basename so local chat history never stores source paths."""
    cleaned = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not cleaned or len(cleaned) > 255:
        raise ValueError("附件名称无效。")
    return cleaned
