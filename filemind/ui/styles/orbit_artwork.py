"""Resolution-independent Orbit artwork shared by static and animated avatars."""

from __future__ import annotations

import math
from typing import Literal

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


AvatarState = Literal["ready", "thinking", "replying"]
AVATAR_STATES: tuple[AvatarState, ...] = ("ready", "thinking", "replying")
IDLE_ORBIT_SECONDS = 6.0
ORBIT_COLORS = {
    "lilac": "#B38AFF", "violet": "#8658EF", "indigo": "#5368EF",
    "ring": "#BBA4F4", "face": "#FFFFFF",
}


def _orbit_paths() -> tuple[QPainterPath, QPainterPath]:
    back = QPainterPath(QPointF(16, 86))
    back.cubicTo(7, 72, 40, 46, 72, 33)
    back.cubicTo(104, 20, 125, 23, 116, 42)
    front = QPainterPath(QPointF(116, 42))
    front.cubicTo(109, 59, 82, 79, 54, 89)
    front.cubicTo(31, 97, 18, 96, 16, 86)
    return back, front


def _pen(color: str, width: float, opacity: float = 1.0) -> QPen:
    value = QColor(color)
    value.setAlphaF(opacity)
    return QPen(value, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)


def _paint_planet(painter: QPainter) -> QPainterPath:
    core = QPainterPath()
    core.addEllipse(QRectF(21, 21, 86, 86))
    gradient = QLinearGradient(33, 24, 95, 111)
    for position, name in ((0.0, "lilac"), (0.48, "violet"), (1.0, "indigo")):
        gradient.setColorAt(position, QColor(ORBIT_COLORS[name]))
    painter.fillPath(core, gradient)
    highlight = QPainterPath(QPointF(34, 49))
    highlight.cubicTo(38, 36, 49, 30, 60, 30)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_pen(ORBIT_COLORS["face"], 5, 0.16))
    painter.drawPath(highlight)
    return core


def _paint_eyes(painter: QPainter, state: AvatarState, seconds: float) -> None:
    white = ORBIT_COLORS["face"]
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(white))
    if state == "thinking":
        for center in (QPointF(54, 52), QPointF(76, 47)):
            painter.drawEllipse(center, 3.6, 3.6)
    elif state == "replying":
        eyes = QPainterPath(QPointF(46, 60))
        eyes.quadTo(50, 53, 55, 58)
        eyes.moveTo(67, 55)
        eyes.quadTo(72, 48, 77, 53)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_pen(white, 5))
        painter.drawPath(eyes)
    else:
        blink = seconds % 4.6
        openness = 1.0
        if 3.8 < blink < 3.98:
            openness -= 0.94 * math.sin(math.pi * (blink - 3.8) / 0.18)
        height = max(1.2, 11 * openness)
        for left, center_y in ((47.0, 57.5), (70.0, 52.5)):
            painter.drawRoundedRect(QRectF(left, center_y - height / 2, 6.5, height),
                                    min(3.25, height / 2), min(3.25, height / 2))


def _paint_satellite(painter: QPainter, position: QPointF) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ORBIT_COLORS["violet"]))
    painter.drawEllipse(position, 5, 5)
    highlight = QColor(ORBIT_COLORS["face"])
    highlight.setAlphaF(0.55)
    painter.setBrush(highlight)
    painter.drawEllipse(position + QPointF(-1.2, -1.2), 1.4, 1.4)


def _paint_orbit(painter: QPainter, state: AvatarState, seconds: float) -> None:
    back, front = _orbit_paths()
    ring = back.toReversed()
    ring.connectPath(front.toReversed())
    period = IDLE_ORBIT_SECONDS if state == "ready" else 2.8
    start_phase = 0.105 if state == "ready" else 0.65
    phase = (start_phase + seconds / period) % 1.0
    moving = state in ("ready", "thinking") and seconds > 0
    satellite = ring.pointAtPercent(phase) if moving else QPointF(111, 28)
    behind = moving and phase < 0.5
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_pen(ORBIT_COLORS["ring"], 5.5))
    painter.drawPath(back)
    if behind:
        _paint_satellite(painter, satellite)
    core = _paint_planet(painter)
    _paint_eyes(painter, state, seconds)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_pen(ORBIT_COLORS["ring"], 5.5))
    painter.drawPath(front)
    painter.save()
    painter.setClipPath(core)
    painter.setPen(_pen(ORBIT_COLORS["face"], 5.5))
    painter.drawPath(front)
    painter.restore()
    if not behind:
        _paint_satellite(painter, satellite)


def orbit_pixmap(size: int, device_pixel_ratio: float = 1.0, *,
                 state: AvatarState = "ready", seconds: float = 0.0,
                 animated: bool = False) -> QPixmap:
    """Render the Figma identity at logical size, preserving high-DPI sharpness."""
    if state not in AVATAR_STATES:
        raise ValueError(f"Unknown Orbit avatar state: {state}")
    if size <= 0 or not math.isfinite(device_pixel_ratio) or device_pixel_ratio <= 0:
        raise ValueError("Avatar size and device pixel ratio must be positive")
    dimension = max(1, round(size * device_pixel_ratio))
    pixmap = QPixmap(dimension, dimension)
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 128, size / 128)
        elapsed = seconds if animated else 0.0
        pulse = math.sin(elapsed * math.tau / 2.8)
        scale = 1 + (0.018 if state == "thinking" else 0.008) * pulse
        if state == "replying":
            scale = 1 + 0.04 * math.sin(math.pi * min(elapsed / 0.48, 1.0))
        painter.translate(64, 64 + 1.4 * pulse)
        painter.scale(scale, scale)
        painter.translate(-64, -64)
        _paint_orbit(painter, state, elapsed)
    finally:
        painter.end()
    return pixmap
