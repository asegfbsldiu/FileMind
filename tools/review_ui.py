"""Launch FileMind normally, or opt into isolated UI captures and fixture data."""

from __future__ import annotations

import argparse
import secrets
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from filemind.chat_models import ChatConversation, ChatMessage
from filemind.ai.model_config import ModelConfig
from filemind.core.planner import build_plan
from filemind.core.scanner import scan_files
from filemind.models import ClassificationResult
from filemind.storage.chat_history import ChatHistoryStore
from filemind.storage.local_lock import LocalLockStore
from filemind.storage.settings import AISettings, SettingsStore
from filemind.ui.dialogs.local_lock import LocalLockDialog
from filemind.ui.dialogs.plan_preview import PlanPreviewDialog
from filemind.ui.main_window import MainWindow
from filemind.ui.styles.theme import apply_theme


class ReviewSettings(SettingsStore):
    """Allow isolated edits without ever reading real env or OS credentials."""

    credential_storage_label = "当前隔离验收会话（关闭后清除）"

    def _with_resolved_key(self, config: ModelConfig) -> ModelConfig:
        """Resolve fixture credentials without inspecting process environment keys."""
        from dataclasses import replace
        profile = self.load(config.provider)
        endpoint = config.base_url.strip() or profile.base_url
        key = profile.api_key if endpoint.rstrip("/") == profile.base_url.rstrip("/") else ""
        return replace(config, base_url=endpoint, api_key=key)

    def _load_secret(self, settings: AISettings) -> tuple[str, str]:
        if settings.local:
            return "", "本机模型无需密钥"
        if settings.store_key_locally:
            value = self._read_local_secret(settings.provider_id)
        else:
            value = self.secret_store.get(f"FileMind/{settings.provider_id}/api-key")
        return value or "", "隔离验收会话" if value else "未配置"


class ReviewCredentials:
    """Keep only explicitly entered fixture keys in this isolated process."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, target: str) -> str | None:
        return self.values.get(target)

    def set(self, target: str, value: str) -> None:
        self.values[target] = value

    def delete(self, target: str) -> None:
        self.values.pop(target, None)


def sample_plan(root: Path):
    """Build a real validated plan from exclusively generated fixture files."""
    selected = root / "课程资料"
    selected.mkdir()
    for name in ("数据结构讲义.pdf", "链表练习.py", "数据库实验.docx", "课程表.xlsx", "项目截图.png"):
        (selected / name).write_bytes(b"generated UI fixture")
    categories = {".pdf": "学习资料", ".py": "编程练习", ".docx": "学习资料", ".xlsx": "表格", ".png": "图片"}
    return build_plan(selected, scan_files(selected), lambda item: ClassificationResult(
        categories[item.suffix], "生成的界面验收数据，尚未执行文件操作",
        target_subdirectory="数据结构/第一章" if item.suffix == ".pdf" else ""))


def build_review(root: Path, page: str) -> tuple[QWidget, MainWindow | None]:
    """Select a real UI state without loading the user's settings or history."""
    lock = LocalLockStore(root / "local-lock" / "auth.json")
    if page in {"setup", "unlock", "reset", "change"}:
        if page != "setup":
            lock.initialize(secrets.token_hex(12))
        return LocalLockDialog(lock, page), None
    store = ReviewSettings(root / "settings.json", root, secret_store=ReviewCredentials())
    window = MainWindow(store, ChatHistoryStore(root / "chats.json"), lock)
    window.setWindowTitle("FileMind UI 验收 · 仅临时生成数据")
    if page == "preview":
        plan = sample_plan(root)
        window.organize_page.set_plan(plan)
        return PlanPreviewDialog(plan, window.organize_page.table_model, window), window
    if page in {"organize", "content"}:
        plan = sample_plan(root)
        window.organize_page.set_directory(str(plan.root))
        if page == "organize":
            window.organize_page.set_plan(plan)
        else:
            window.organize_page.set_files(scan_files(plan.root))
            window.organize_page.preset_combo.setCurrentIndex(window.organize_page.preset_combo.findData("content"))
    if page in {"orbit", "chat"}:
        window._show_page("assistant")
        if page == "chat":
            messages = (ChatMessage("user", "帮我规划数据结构学习。"), ChatMessage("assistant",
                "## 学习计划\n\n从线性表、树和图开始。\n\n" + "- 理解概念后用 Python 实现，再分析复杂度。\n" * 25))
            window.assistant_page.set_conversation(ChatConversation(title="学习计划 · 测试数据", messages=messages))
    if page in {"settings", "conversion", "appsettings"}:
        window._show_page(page)
    return window, window


def main(arguments: list[str] | None = None) -> int:
    """Use normal application persistence unless isolation is explicitly selected."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", choices=["setup", "unlock", "reset", "change", "preview", "organize", "content", "orbit", "chat", "settings", "appsettings", "conversion"], default="setup")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=850)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--isolated", action="store_true", help="仅使用临时验收数据，不加载真实配置")
    args = parser.parse_args(arguments)
    if not args.isolated and not args.snapshot:
        from filemind.ui.startup import run_application
        return run_application()
    application = QApplication(sys.argv[:1])
    apply_theme(application)
    with tempfile.TemporaryDirectory(prefix="filemind-ui-") as directory:
        widget, window = build_review(Path(directory), args.page)
        widget.resize(args.width, args.height)
        if window is not None and window is not widget and not args.snapshot:
            window.show()
        widget.show()
        if args.snapshot:
            def capture() -> None:
                args.snapshot.parent.mkdir(parents=True, exist_ok=True)
                if not widget.grab().save(str(args.snapshot)):
                    raise OSError("无法保存 UI 截图")
                widget.close()
                finish_capture()
            def finish_capture() -> None:
                if window is not None and window.conversion_page.has_pending_work:
                    QTimer.singleShot(50, finish_capture)
                    return
                application.quit()
            QTimer.singleShot(500, capture)
        result = application.exec()
        widget.deleteLater()
        if window is not None and window is not widget:
            window.deleteLater()
        application.sendPostedEvents()
        return result


if __name__ == "__main__":
    raise SystemExit(main())
