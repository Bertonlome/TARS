"""
TrimIndicatorWidget
Compact horizontal bar showing rudder trim position in the range [-5, +5].

The bar fills from the center (0) toward the current trim value.
Colour:
  • Orange  — TRIMMING state (actively adjusting)
  • Green   — STABLE  state (slip centred, holding)
"""

from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget

_TRIM_MIN = -5.0
_TRIM_MAX = 5.0
_TRACK_MARGIN_X = 26   # pixels reserved for "-5" / "+5" labels
_TRACK_H = 14          # track bar height
_TRACK_RADIUS = 3      # bar corner radius

_COLOR_TRIMMING = QColor(255, 140, 30)   # orange
_COLOR_STABLE   = QColor(0,  200, 100)   # green
_COLOR_TRACK_BG = QColor(50,  55,  65)   # dark gray track
_COLOR_CENTER   = QColor(200, 205, 215)  # center tick
_COLOR_TICK     = QColor(100, 105, 115)  # ±2.5 ticks
_COLOR_LABEL    = QColor(130, 135, 145)  # scale labels


class TrimIndicatorWidget(QWidget):
    """Horizontal rudder-trim indicator widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._trim: float = 0.0
        self._stable: bool = False
        self.setFixedSize(230, 44)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    # ── Public setters ────────────────────────────────────────────────────

    def set_trim(self, value: float) -> None:
        clamped = max(_TRIM_MIN, min(_TRIM_MAX, float(value)))
        if clamped != self._trim:
            self._trim = clamped
            self.update()

    def set_stable(self, stable: bool) -> None:
        if stable != self._stable:
            self._stable = stable
            self.update()

    # ── Paint ─────────────────────────────────────────────────────────────

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        track_x = _TRACK_MARGIN_X
        track_w = w - 2 * _TRACK_MARGIN_X
        track_y = 6
        label_y = track_y + _TRACK_H + 4
        label_h = self.height() - label_y

        pixel_per_unit = track_w / (_TRIM_MAX - _TRIM_MIN)  # px per trim unit
        center_x = track_x + track_w // 2
        pixel_offset = int(self._trim * pixel_per_unit)

        color = _COLOR_STABLE if self._stable else _COLOR_TRIMMING

        # ── Background track ──────────────────────────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_COLOR_TRACK_BG)
        p.drawRoundedRect(track_x, track_y, track_w, _TRACK_H,
                          _TRACK_RADIUS, _TRACK_RADIUS)

        # ── Filled bar (center → trim value) ─────────────────────────────
        if pixel_offset != 0:
            p.setBrush(color)
            if pixel_offset > 0:
                fill = QRectF(center_x, track_y + 2, pixel_offset, _TRACK_H - 4)
            else:
                fill = QRectF(center_x + pixel_offset, track_y + 2,
                              -pixel_offset, _TRACK_H - 4)
            p.drawRoundedRect(fill, 2, 2)

        # ── Center tick ───────────────────────────────────────────────────
        p.setPen(QPen(_COLOR_CENTER, 1))
        p.drawLine(center_x, track_y - 2, center_x, track_y + _TRACK_H + 2)

        # ── ±2.5 minor ticks ─────────────────────────────────────────────
        p.setPen(QPen(_COLOR_TICK, 1))
        for tick_val in (-2.5, 2.5):
            tx = int(center_x + tick_val * pixel_per_unit)
            p.drawLine(tx, track_y + _TRACK_H - 5, tx, track_y + _TRACK_H + 1)

        # ── Scale labels ──────────────────────────────────────────────────
        label_font = QFont("JetBrains Mono", 8)
        p.setFont(label_font)
        p.setPen(_COLOR_LABEL)

        # -5 (left)
        p.drawText(QRect(0, label_y, _TRACK_MARGIN_X - 2, label_h),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, "-5")
        # +5 (right)
        p.drawText(QRect(track_x + track_w + 2, label_y, _TRACK_MARGIN_X - 2, label_h),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "+5")
        # 0 (center)
        p.drawText(QRect(center_x - 12, label_y, 24, label_h),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, "0")

        # ── Current value text ────────────────────────────────────────────
        if abs(self._trim) >= 0.05:
            p.setPen(color)
            val_text = f"{self._trim:+.1f}"
            end_x = center_x + pixel_offset
            if pixel_offset >= 0:
                vr = QRect(min(end_x + 3, w - 30), label_y, 28, label_h)
                align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            else:
                vr = QRect(max(2, end_x - 30), label_y, 28, label_h)
                align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
            p.drawText(vr, align, val_text)

        p.end()
