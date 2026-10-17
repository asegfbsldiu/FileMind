"""Multi-model selection widget: enable, tag, reorder, remove, and add models.

The widget is storage-agnostic. It owns an ordered ``list[ModelConfig]`` and
emits ``changed`` whenever that list changes; the settings page is responsible
for loading from and saving to ``SettingsStore``. Ollama's local model list is
requested through ``refresh_local_requested`` so the network call never runs on
the UI thread.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from filemind.ai.model_config import ModelConfig
from filemind.ai.providers import PROVIDERS, PROVIDER_BY_ID
from filemind.ui.styles.icons import provider_icon
from filemind.ui.widgets.combo_box import StyledComboBox


class ModelSelector(QWidget):
    """Let the user pick and order several models for parallel Orbit requests."""

    changed = Signal()
    refresh_local_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._configs: list[ModelConfig] = []
        self._build_ui()

    # ------------------------------------------------------------------ build
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(96)
        scroll.setMaximumHeight(240)
        # Make the scroll area (and its viewport/rows container) transparent so the
        # empty space below the model rows blends with the surrounding card instead
        # of showing a gray block.
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        scroll.viewport().setAutoFillBackground(False)
        self._rows_container.setAutoFillBackground(False)
        scroll.setWidget(self._rows_container)
        layout.addWidget(scroll)

        self.empty_label = QLabel("还没有选择模型。用下面的表单添加至少两个模型即可并行调用。")
        self.empty_label.setObjectName("Muted")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        self.tag_label = QLabel()
        self.tag_label.setObjectName("Muted")
        self.tag_label.setWordWrap(True)
        layout.addWidget(self.tag_label)

        layout.addWidget(self._build_add_form())

    def _build_add_form(self) -> QWidget:
        form = QFrame()
        form.setProperty("card", False)
        layout = QVBoxLayout(form)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("服务商"))
        self.provider_combo = StyledComboBox()
        self.provider_combo.setIconSize(QSize(24, 24))
        for provider in PROVIDERS:
            self.provider_combo.addItem(provider_icon(provider.provider_id), provider.name,
                                        provider.provider_id)
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        provider_row.addWidget(self.provider_combo, 1)
        layout.addLayout(provider_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("模型名称"))
        self.model_combo = StyledComboBox()
        self.model_combo.setObjectName("ModelConfigChoice")
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model_combo.setPlaceholderText("例如 gpt-4o、qwen2.5:7b")
        model_row.addWidget(self.model_combo, 1)
        self.refresh_button = QPushButton("获取本地模型")
        self.refresh_button.setToolTip("从本机 Ollama 读取已安装模型列表")
        self.refresh_button.clicked.connect(self._request_local_models)
        model_row.addWidget(self.refresh_button)
        layout.addLayout(model_row)

        self._add_endpoint_fields(layout)

        action_row = QHBoxLayout()
        self.add_status = QLabel()
        self.add_status.setObjectName("Muted")
        self.add_status.setWordWrap(True)
        action_row.addWidget(self.add_status, 1)
        self.add_button = QPushButton("添加模型")
        self.add_button.clicked.connect(self._add_current)
        action_row.addWidget(self.add_button)
        layout.addLayout(action_row)
        self._provider_changed(self.provider_combo.currentIndex())
        return form

    def _add_endpoint_fields(self, layout: QVBoxLayout) -> None:
        detail_row = QHBoxLayout()
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("Base URL（留空使用服务商默认值）")
        self.display_name_edit = QLineEdit()
        self.display_name_edit.setPlaceholderText("显示名称（可选）")
        detail_row.addWidget(self.base_url_edit, 1)
        detail_row.addWidget(self.display_name_edit, 1)
        layout.addLayout(detail_row)


    # ----------------------------------------------------------------- public
    def set_configs(self, configs: list[ModelConfig]) -> None:
        """Replace the whole selection, e.g. after loading from settings."""
        self._configs = [config for config in configs if config.model.strip()]
        self._rebuild()

    def configs(self) -> list[ModelConfig]:
        """Return a copy of the ordered selection for persistence."""
        return list(self._configs)

    def enabled_labels(self) -> list[str]:
        """Return the labels of enabled models for compact tag display."""
        return [config.label for config in self._configs if config.enabled]

    def set_local_models(self, models: list[str]) -> None:
        """Fill the editable model combo with Ollama's installed models."""
        current = self.model_combo.currentText()
        self.model_combo.clear()
        self.model_combo.addItems(sorted(models))
        self.model_combo.setEditText(current)
        self.add_status.setText(f"已获取 {len(models)} 个本地模型。" if models else "本机没有可用模型。")

    def set_add_status(self, message: str) -> None:
        """Show a non-fatal hint (for example an Ollama connection failure)."""
        self.add_status.setText(message)

    def reapply_theme(self) -> None:
        """Re-load provider brand icons after a light/dark theme switch."""
        for index in range(self.provider_combo.count()):
            provider_id = self.provider_combo.itemData(index)
            if isinstance(provider_id, str):
                self.provider_combo.setItemIcon(index, provider_icon(provider_id))
        for label in self._rows_container.findChildren(QLabel, "ModelProviderLogo"):
            label.setPixmap(provider_icon(str(label.property("providerId"))).pixmap(24, 24))

    def refresh_provider_icons(self) -> None:
        """Keep the existing model-manager refresh entry point compatible."""
        self.reapply_theme()

    # ---------------------------------------------------------------- internal
    def _provider_changed(self, index: int) -> None:
        provider_id = str(self.provider_combo.itemData(index))
        preset = PROVIDER_BY_ID.get(provider_id)
        is_ollama = bool(preset and preset.kind == "ollama")
        self.refresh_button.setEnabled(is_ollama)
        self.base_url_edit.clear()
        self.base_url_edit.setPlaceholderText(preset.base_url if preset else "Base URL")
        self.add_status.clear()
        self.model_combo.clear()
        self.model_combo.setEditText("")
        if preset and not preset.requires_key:
            self.add_status.setText("该服务商不需要 API Key。")

    def _request_local_models(self) -> None:
        provider_id = str(self.provider_combo.currentData())
        preset = PROVIDER_BY_ID.get(provider_id)
        base_url = self.base_url_edit.text().strip() or (preset.base_url if preset else "")
        self.refresh_local_requested.emit(base_url)

    def _add_current(self) -> None:
        provider_id = str(self.provider_combo.currentData())
        model = self.model_combo.currentText().strip()
        if not model:
            self.add_status.setText("请先填写模型名称。")
            return
        if len(self._configs) >= 20:
            self.add_status.setText("最多保存 20 个模型。")
            return
        config = ModelConfig(
            provider=provider_id,
            model=model,
            base_url=self.base_url_edit.text().strip(),
            display_name=self.display_name_edit.text().strip(),
        )
        if any(item.identity == config.identity for item in self._configs):
            self.add_status.setText("该模型已在列表中。")
            return
        self._configs.append(config)
        self.model_combo.setEditText("")
        self.display_name_edit.clear()
        self.add_status.setText(f"已添加 {config.label}。记得保存模型选择。")
        self._rebuild()
        self.changed.emit()

    def _set_enabled(self, index: int, enabled: bool) -> None:
        self._configs[index] = replace(self._configs[index], enabled=enabled)
        self._rebuild()
        self.changed.emit()

    def _move(self, index: int, direction: int) -> None:
        target = index + direction
        if not 0 <= target < len(self._configs):
            return
        self._configs[index], self._configs[target] = self._configs[target], self._configs[index]
        self._rebuild()
        self.changed.emit()

    def _remove(self, index: int) -> None:
        del self._configs[index]
        self._rebuild()
        self.changed.emit()

    def _rebuild(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, config in enumerate(self._configs):
            self._rows_layout.addWidget(self._build_row(index, config), 0)
        self._rows_layout.addStretch(1)
        self.empty_label.setVisible(not self._configs)
        labels = self.enabled_labels()
        self.tag_label.setText("已选：" + "　".join(labels) if labels else "已选：无（至少勾选两个模型才能并行调用）")

    def _build_row(self, index: int, config: ModelConfig) -> QWidget:
        row = QFrame()
        row.setObjectName("ModelSelectionRow")
        row.setProperty("card", True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)

        checkbox = QCheckBox()
        checkbox.setChecked(config.enabled)
        checkbox.setToolTip("勾选后参与并行调用")
        checkbox.toggled.connect(lambda checked, i=index: self._set_enabled(i, checked))
        layout.addWidget(checkbox)

        logo = QLabel()
        logo.setObjectName("ModelProviderLogo")
        logo.setProperty("providerId", config.provider)
        logo.setFixedSize(26, 26)
        logo.setPixmap(provider_icon(config.provider).pixmap(24, 24))
        layout.addWidget(logo)

        text = QLabel(f"{config.label}\n{config.identity}")
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setMinimumWidth(0)
        text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text.setToolTip(f"{config.label}\n{config.identity}")
        layout.addWidget(text, 1)

        up_button = QPushButton("↑")
        up_button.setFixedWidth(34)
        up_button.setEnabled(index > 0)
        up_button.setToolTip("上移")
        up_button.clicked.connect(lambda _checked=False, i=index: self._move(i, -1))
        layout.addWidget(up_button)

        down_button = QPushButton("↓")
        down_button.setFixedWidth(34)
        down_button.setEnabled(index < len(self._configs) - 1)
        down_button.setToolTip("下移")
        down_button.clicked.connect(lambda _checked=False, i=index: self._move(i, 1))
        layout.addWidget(down_button)

        remove_button = QPushButton("删除")
        remove_button.setToolTip("从列表移除")
        remove_button.clicked.connect(lambda _checked=False, i=index: self._remove(i))
        layout.addWidget(remove_button)
        return row
