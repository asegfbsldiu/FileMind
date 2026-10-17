"""Orbit chat avatar with visibility-aware native Qt animation."""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import QLabel, QWidget

from filemind.ui.styles.orbit_artwork import AVATAR_STATES, AvatarState, orbit_pixmap


STATE_LABELS = {"ready": "待命", "thinking": "正在思考", "replying": "回复完成"}
REPLY_DURATION_SECONDS = 0.48


class OrbitAvatar(QLabel):
    """Animate one active assistant identity while historical messages stay still."""

    def __init__(self, size: int = 36, parent: QWidget | None = None, *,
                 animate_idle: bool = False) -> None:
        super().__init__(parent)
        self._size = size
        self._state: AvatarState = "ready"
        self._motion_enabled = True
        self._animate_idle = animate_idle
        self._elapsed_seconds = 0.0
        self._clock = QElapsedTimer()
        self._observed_window: QWidget | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._advance_frame)
        self.setObjectName("OrbitAssistantAvatar")
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_description()
        self._render_frame()

    @property
    def state(self) -> AvatarState:
        """Return the actual request feedback represented by this avatar."""
        return self._state

    @property
    def is_animating(self) -> bool:
        """Report whether this visible avatar currently schedules animation frames."""
        return self._timer.isActive()

    @property
    def motion_enabled(self) -> bool:
        """Return the user's motion preference for this avatar."""
        return self._motion_enabled

    def set_state(self, state: AvatarState) -> None:
        """Change expression without restarting an already active request cycle."""
        if state not in AVATAR_STATES:
            raise ValueError(f"Unknown Orbit avatar state: {state}")
        if self._state != state:
            self._pause_animation()
            self._state = state
            self._elapsed_seconds = 0.0
            self._update_description()
        self._sync_animation()
        self._render_frame()

    def set_motion_enabled(self, enabled: bool) -> None:
        """Immediately replace motion with a static state when motion is reduced."""
        self._pause_animation()
        self._motion_enabled = enabled
        self._elapsed_seconds = 0.0
        self._sync_animation()
        self._render_frame()

    def _update_description(self) -> None:
        label = f"Orbit AI：{STATE_LABELS[self._state]}"
        self.setAccessibleName(label)
        self.setToolTip(label)

    def _seconds(self) -> float:
        return self._elapsed_seconds + (self._clock.elapsed() / 1000 if self._clock.isValid() else 0)

    def _pause_animation(self) -> None:
        self._elapsed_seconds = self._seconds()
        self._clock.invalidate()
        self._timer.stop()

    def _sync_animation(self) -> None:
        active = (self._motion_enabled and self.isVisible() and not self.window().isMinimized()
                  and (self._animate_idle or self._state != "ready"))
        if active and not self._timer.isActive():
            self._clock.start()
            self._timer.start()
        elif not active:
            self._pause_animation()

    def _advance_frame(self) -> None:
        if self._state == "replying" and self._seconds() >= REPLY_DURATION_SECONDS:
            self.set_state("ready")
            return
        self._render_frame()

    def _render_frame(self) -> None:
        self.setPixmap(orbit_pixmap(self._size, self.devicePixelRatioF(), state=self._state,
                                   seconds=self._seconds(), animated=self._motion_enabled))

    def showEvent(self, event: QShowEvent) -> None:
        """Resume only when this avatar's page is actually visible."""
        super().showEvent(event)
        window = self.window()
        if self._observed_window is not window:
            if self._observed_window is not None:
                self._observed_window.removeEventFilter(self)
            self._observed_window = window
            window.installEventFilter(self)
        self._sync_animation()
        self._render_frame()

    def hideEvent(self, event: QHideEvent) -> None:
        """Stop frame scheduling for hidden pages and closed windows."""
        self._pause_animation()
        super().hideEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Pause minimized windows and redraw when the display scale changes."""
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_animation()
        elif event.type() == QEvent.Type.DevicePixelRatioChange:
            self._render_frame()
        return super().eventFilter(watched, event)
