"""
Wind Edit Dialog
A popup dialog for editing wind orientation and magnitude with a virtual numeric keyboard.
"""

import math
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QSizePolicy, QWidget
)
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QPolygonF


# ---------------------------------------------------------------------------
# Shared dark-theme style constants
# ---------------------------------------------------------------------------
_BG_DEEP   = "rgb(27, 31, 37)"
_BG_MID    = "rgb(33, 37, 43)"
_BG_PANEL  = "rgb(44, 49, 60)"
_BORDER    = "rgb(52, 59, 72)"
_BLUE      = "#55aaff"
_GREEN     = "#55de71"
_RED       = "#ff5555"
_WHITE     = "white"


# ---------------------------------------------------------------------------
# Single digit display box
# ---------------------------------------------------------------------------
class _DigitBox(QLabel):
    """A single-character display box that acts like a digit cell."""

    clicked_signal = Signal(object)  # emits self

    def __init__(self, parent=None):
        super().__init__("_", parent)
        self._active = False
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(56, 68)
        font = QFont("JetBrains Mono", 26, QFont.Bold)
        self.setFont(font)
        self._refresh_style()

    # ------------------------------------------------------------------
    def set_digit(self, ch: str):
        """Set to a single char (digit) or '_' for empty."""
        self.setText(ch if ch else "_")

    def digit(self) -> str:
        """Return current character, or '' if blank."""
        t = self.text()
        return t if t != "_" else ""

    def is_empty(self) -> bool:
        return self.text() == "_"

    # ------------------------------------------------------------------
    def set_active(self, active: bool):
        self._active = active
        self._refresh_style()

    def _refresh_style(self):
        border_color = _BLUE if self._active else _BORDER
        bg = _BG_MID if self._active else _BG_DEEP
        self.setStyleSheet(f"""
            QLabel {{
                color: {_WHITE};
                background-color: {bg};
                border: 2px solid {border_color};
                border-radius: 6px;
            }}
        """)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked_signal.emit(self)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Compass + Windsock visualisation
# ---------------------------------------------------------------------------
class _CompassWindsock(QWidget):
    """Compass rose whose top always points toward the runway heading,
    with a trapezoidal orange/white windsock that shows wind direction
    and magnitude.  Click or drag on the compass to set values directly."""

    wind_dragged = Signal(int, int)   # direction_deg, magnitude_kt

    def __init__(self, parent=None, runway_heading: int = 237):
        super().__init__(parent)
        self._runway_heading = runway_heading
        self._wind_dir = 0      # degrees – where wind comes FROM
        self._wind_mag = 0      # knots
        self._max_mag = 50      # knots for full-length sock
        self._dragging = False
        self.setFixedSize(280, 300)
        self.setCursor(Qt.CrossCursor)

    def set_wind(self, direction: int, magnitude: int):
        self._wind_dir = direction % 360
        self._wind_mag = max(0, magnitude)
        self.update()

    # -- touch / mouse interaction ----------------------------------------
    def _compass_geometry(self):
        """Return (cx, cy, radius) matching paintEvent's geometry."""
        w, h = self.width(), self.height()
        return w / 2, h / 2 + 12, min(w, h) / 2 - 30

    def _pos_to_wind(self, qpointf):
        """Convert a widget-local QPointF to (direction°, magnitude_kt)."""
        cx, cy, radius = self._compass_geometry()
        dx, dy = qpointf.x() - cx, qpointf.y() - cy
        distance = math.sqrt(dx * dx + dy * dy)
        if distance < 0.5:
            return self._wind_dir, 0      # calm – keep previous heading
        angle_deg = math.degrees(math.atan2(dx, -dy))
        wind_dir = int((self._runway_heading + angle_deg) % 360)
        magnitude = round(min(self._max_mag,
                              self._max_mag * distance / radius))
        return wind_dir, magnitude

    def mousePressEvent(self, event):               # noqa: N802
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.setCursor(Qt.ClosedHandCursor)
            d, m = self._pos_to_wind(event.position())
            self.wind_dragged.emit(d, m)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):                # noqa: N802
        if self._dragging:
            d, m = self._pos_to_wind(event.position())
            self.wind_dragged.emit(d, m)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):             # noqa: N802
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CrossCursor)
        super().mouseReleaseEvent(event)

    # -- coordinate helper ------------------------------------------------
    def _hdg_xy(self, heading_deg: float, radius: float):
        """Compass heading → (dx, dy) offset from centre.
        Runway heading maps to straight up (12-o'clock)."""
        a = math.radians(heading_deg - self._runway_heading)
        return radius * math.sin(a), -radius * math.cos(a)

    # -- paint ------------------------------------------------------------
    def paintEvent(self, event):                        # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2 + 12        # nudge down for RWY label
        radius = min(w, h) / 2 - 30

        # background
        p.fillRect(self.rect(), QColor(_BG_MID))

        # ---- RWY label above compass ----
        p.setFont(QFont("JetBrains Mono", 9, QFont.Bold))
        p.setPen(QColor(_BLUE))
        rwy_txt = f"RWY {self._runway_heading:03d}\u00b0"
        tw = p.fontMetrics().horizontalAdvance(rwy_txt)
        p.drawText(QPointF(cx - tw / 2, cy - radius - 8), rwy_txt)

        # ---- compass circle ----
        p.setPen(QPen(QColor(_BORDER), 2))
        p.setBrush(QColor(_BG_DEEP))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # ---- tick marks (every 10°, longer every 30°) ----
        for deg in range(0, 360, 10):
            long_tick = (deg % 30 == 0)
            ox, oy = self._hdg_xy(deg, radius)
            ix, iy = self._hdg_xy(deg, radius - (12 if long_tick else 6))
            p.setPen(QPen(QColor(_WHITE if long_tick else _BORDER),
                         1.5 if long_tick else 1))
            p.drawLine(QPointF(cx + ox, cy + oy),
                       QPointF(cx + ix, cy + iy))

        # ---- cardinal labels ----
        p.setFont(QFont("JetBrains Mono", 10, QFont.Bold))
        fm = p.fontMetrics()
        for hdg, lbl in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
            lx, ly = self._hdg_xy(hdg, radius - 24)
            p.setPen(QColor(_WHITE))
            p.drawText(
                QPointF(cx + lx - fm.horizontalAdvance(lbl) / 2,
                        cy + ly + fm.height() / 3),
                lbl)

        # ---- runway dashed centre-line ----
        p.setPen(QPen(QColor(_BLUE), 1.5, Qt.DashLine))
        tx, ty = self._hdg_xy(self._runway_heading, radius - 14)
        bx, by = self._hdg_xy((self._runway_heading + 180) % 360, radius - 14)
        p.drawLine(QPointF(cx + tx, cy + ty),
                   QPointF(cx + bx, cy + by))

        # ---- windsock / calm indicator ----
        if self._wind_mag > 0:
            self._paint_sock(p, cx, cy, radius)
        else:
            p.setPen(QPen(QColor("#ff8c00"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), 8, 8)

        p.end()

    # -- windsock painter -------------------------------------------------
    def _paint_sock(self, p: QPainter, cx: float, cy: float, radius: float):
        """Draw 5-stripe trapezoidal windsock from compass centre."""
        downwind = (self._wind_dir + 180) % 360
        a = math.radians(downwind - self._runway_heading)

        # direction unit-vectors
        dx, dy = math.sin(a), -math.cos(a)       # along sock
        px, py = math.cos(a),  math.sin(a)       # perpendicular

        max_len = radius * 0.78
        length = max(18, min(max_len, max_len * self._wind_mag / self._max_mag))

        base_hw = 12    # half-width at anchor (wide end)
        tip_hw  = 3     # half-width at tip   (narrow end)
        colors  = [QColor("#ff8c00"), QColor("#ffffff")]   # orange / white
        n_stripes = 5

        for i in range(n_stripes):
            t0, t1 = i / n_stripes, (i + 1) / n_stripes
            hw0 = base_hw + (tip_hw - base_hw) * t0
            hw1 = base_hw + (tip_hw - base_hw) * t1
            sx0, sy0 = cx + dx * length * t0, cy + dy * length * t0
            sx1, sy1 = cx + dx * length * t1, cy + dy * length * t1
            poly = QPolygonF([
                QPointF(sx0 + px * hw0, sy0 + py * hw0),
                QPointF(sx0 - px * hw0, sy0 - py * hw0),
                QPointF(sx1 - px * hw1, sy1 - py * hw1),
                QPointF(sx1 + px * hw1, sy1 + py * hw1),
            ])
            p.setPen(QPen(QColor(100, 100, 100), 0.5))
            p.setBrush(colors[i % 2])
            p.drawPolygon(poly)

        # small "wind-from" triangle on compass rim
        fx, fy = self._hdg_xy(self._wind_dir, radius - 2)
        arw_l, arw_hw = 10, 5
        tri = QPolygonF([
            QPointF(cx + fx, cy + fy),
            QPointF(cx + fx + dx * arw_l + px * arw_hw,
                    cy + fy + dy * arw_l + py * arw_hw),
            QPointF(cx + fx + dx * arw_l - px * arw_hw,
                    cy + fy + dy * arw_l - py * arw_hw),
        ])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ff8c00"))
        p.drawPolygon(tri)

        # anchor dot at centre
        p.drawEllipse(QPointF(cx, cy), 4, 4)


# ---------------------------------------------------------------------------
# Wind Edit Dialog
# ---------------------------------------------------------------------------
class WindEditDialog(QDialog):
    """
    Popup dialog for editing wind direction (°) and magnitude (kt).

    Signals
    -------
    confirmed(direction_deg: int, magnitude_kt: int)
        Emitted when the user accepts the form.
    """

    confirmed = Signal(int, int)   # direction °, magnitude kt

    def __init__(self, parent=None, runway_heading: int = 237,
                 initial_dir: int = 0, initial_mag: int = 0,
                 metar_text: str = "", metar_reliable: bool = True):
        super().__init__(parent)
        self.setWindowTitle("WIND EDITOR")
        self.setModal(True)
        self.setFixedSize(800, 660 if metar_text else 620)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {_BG_MID};
                color: {_WHITE};
            }}
        """)

        self._runway_heading = runway_heading
        self._metar_text     = metar_text
        self._metar_reliable = metar_reliable

        # 6 digit boxes: [dir_h, dir_t, dir_u, mag_h, mag_t, mag_u]
        self._boxes: list[_DigitBox] = [_DigitBox(self) for _ in range(6)]
        self._active_idx: int = 0

        for i, box in enumerate(self._boxes):
            box.clicked_signal.connect(lambda b, idx=i: self._set_active(idx))

        self._build_ui()
        self._compass.wind_dragged.connect(self._on_compass_drag)
        self._load_initial(initial_dir, initial_mag)
        self._set_active(0)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ---- Title ----
        title = QLabel("WIND EDITOR")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("JetBrains Mono", 14, QFont.Bold))
        title.setStyleSheet(f"color: {_BLUE}; letter-spacing: 3px;")
        root.addWidget(title)
        root.addWidget(self._make_separator())

        # ---- Content: left (fields + numpad)  |  right (compass) ----
        content = QHBoxLayout()
        content.setSpacing(20)

        # -- Left column --
        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(self._build_field_row("Wind direction  (\u00b0)", 0, 3, "HDG"))
        left.addWidget(self._make_separator())
        left.addWidget(self._build_field_row("Wind magnitude  (kt)", 3, 6, "KT"))
        left.addWidget(self._make_separator())
        left.addLayout(self._build_numpad())
        left.addStretch()
        content.addLayout(left)

        # -- Right column: compass + windsock --
        right = QVBoxLayout()
        right.setSpacing(6)
        self._compass = _CompassWindsock(self, self._runway_heading)
        right.addStretch()
        right.addWidget(self._compass, alignment=Qt.AlignCenter)
        self._wind_info_label = QLabel("CALM")
        self._wind_info_label.setAlignment(Qt.AlignCenter)
        self._wind_info_label.setFont(QFont("JetBrains Mono", 9, QFont.Bold))
        self._wind_info_label.setStyleSheet(f"color: {_WHITE};")
        right.addWidget(self._wind_info_label)

        # ---- METAR source label (shown only when data was provided) ----
        if self._metar_text:
            metar_color = _GREEN
            metar_lbl = QLabel(self._metar_text)
            metar_lbl.setAlignment(Qt.AlignCenter)
            metar_lbl.setWordWrap(True)
            metar_lbl.setFont(QFont("JetBrains Mono", 10))
            metar_lbl.setStyleSheet(
                f"color: {metar_color}; "
                f"background-color: {_BG_DEEP}; "
                f"border: 1px solid {metar_color}; "
                "border-radius: 4px; "
                "padding: 4px 6px;"
            )
            right.addWidget(metar_lbl)

        right.addStretch()
        content.addLayout(right)

        root.addLayout(content)

        # ---- Action buttons ----
        root.addWidget(self._make_separator())
        root.addLayout(self._build_action_buttons())

    def _make_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {_BORDER};")
        return sep

    def _build_field_row(self, label_text: str, start: int, end: int,
                         unit_hint: str) -> QWidget:
        """Build one row: label + 3 digit boxes + unit hint."""
        container = QFrame()
        container.setStyleSheet("background: transparent;")
        row = QVBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        lbl = QLabel(label_text)
        lbl.setFont(QFont("JetBrains Mono", 11))
        lbl.setStyleSheet(f"color: rgb(200,200,200);")
        row.addWidget(lbl)

        boxes_row = QHBoxLayout()
        boxes_row.setSpacing(8)
        boxes_row.addStretch()
        for i in range(start, end):
            boxes_row.addWidget(self._boxes[i])
        unit_lbl = QLabel(f"  {unit_hint}")
        unit_lbl.setFont(QFont("JetBrains Mono", 14, QFont.Bold))
        unit_lbl.setStyleSheet(f"color: {_BLUE};")
        boxes_row.addWidget(unit_lbl)
        boxes_row.addStretch()
        row.addLayout(boxes_row)
        return container

    def _build_numpad(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(10)
        # layout: 7 8 9 / 4 5 6 / 1 2 3 / DEL 0 NEXT
        keys = [
            ("7", 0, 0), ("8", 0, 1), ("9", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("1", 2, 0), ("2", 2, 1), ("3", 2, 2),
            ("⌫", 3, 0), ("0", 3, 1), ("→", 3, 2),
        ]
        for text, r, c in keys:
            btn = self._make_numpad_btn(text)
            btn.clicked.connect(lambda _=False, t=text: self._numpad_press(t))
            grid.addWidget(btn, r, c)
        return grid

    def _make_numpad_btn(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(118, 56)
        btn.setFont(QFont("JetBrains Mono", 18, QFont.Bold))
        is_action = text in ("⌫", "→")
        bg = _BG_PANEL
        fg = _BLUE if is_action else _WHITE
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 2px solid {_BORDER};
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: rgb(60, 68, 82);
                border: 2px solid {_BLUE};
            }}
            QPushButton:pressed {{
                background-color: rgb(52, 59, 72);
            }}
        """)
        return btn

    def _build_action_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setFixedHeight(48)
        cancel_btn.setFont(QFont("JetBrains Mono", 12, QFont.Bold))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_BG_PANEL};
                color: {_RED};
                border: 2px solid {_RED};
                border-radius: 8px;
            }}
            QPushButton:hover {{ background-color: rgba(255,85,85,30); }}
            QPushButton:pressed {{ background-color: rgba(255,85,85,60); }}
        """)
        cancel_btn.clicked.connect(self.reject)

        self._confirm_btn = QPushButton("CONFIRM")
        self._confirm_btn.setFixedHeight(48)
        self._confirm_btn.setFont(QFont("JetBrains Mono", 12, QFont.Bold))
        self._confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_BG_PANEL};
                color: {_GREEN};
                border: 2px solid {_GREEN};
                border-radius: 8px;
            }}
            QPushButton:hover {{ background-color: rgba(85,222,113,30); }}
            QPushButton:pressed {{ background-color: rgba(85,222,113,60); }}
        """)
        self._confirm_btn.clicked.connect(self._on_confirm)

        row.addWidget(cancel_btn)
        row.addWidget(self._confirm_btn)
        return row

    # ------------------------------------------------------------------
    # Active box management
    # ------------------------------------------------------------------
    def _set_active(self, idx: int):
        if 0 <= self._active_idx < len(self._boxes):
            self._boxes[self._active_idx].set_active(False)
        self._active_idx = max(0, min(idx, len(self._boxes) - 1))
        self._boxes[self._active_idx].set_active(True)

    # ------------------------------------------------------------------
    # Compass live-update helpers
    # ------------------------------------------------------------------
    def _read_values(self):
        """Read direction and magnitude from the current digit boxes."""
        dir_str = "".join(b.digit() or "0" for b in self._boxes[0:3])
        mag_str = "".join(b.digit() or "0" for b in self._boxes[3:6])
        try:
            direction = int(dir_str) % 360
        except ValueError:
            direction = 0
        try:
            magnitude = max(0, int(mag_str))
        except ValueError:
            magnitude = 0
        return direction, magnitude

    def _update_compass(self):
        """Push current digit values into the compass widget."""
        d, m = self._read_values()
        self._compass.set_wind(d, m)
        if m > 0:
            self._wind_info_label.setText(f"FROM {d:03d}\u00b0 / {m} KT")
            self._wind_info_label.setStyleSheet(f"color: {_GREEN};")
        else:
            self._wind_info_label.setText("CALM")
            self._wind_info_label.setStyleSheet(f"color: {_WHITE};")

    def _on_compass_drag(self, direction: int, magnitude: int):
        """Compass drag → fill digit boxes then refresh compass."""
        for i, ch in enumerate(f"{min(359, direction):03d}"):
            self._boxes[i].set_digit(ch)
        for i, ch in enumerate(f"{min(999, magnitude):03d}"):
            self._boxes[3 + i].set_digit(ch)
        self._update_compass()

    # ------------------------------------------------------------------
    # Numpad handler
    # ------------------------------------------------------------------
    def _numpad_press(self, key: str):
        if key == "\u232b":
            # Clear current box and go back
            box = self._boxes[self._active_idx]
            if not box.is_empty():
                box.set_digit("_")
            elif self._active_idx > 0:
                self._set_active(self._active_idx - 1)
                self._boxes[self._active_idx].set_digit("_")
        elif key == "\u2192":
            # Move to next box (skip groups: dir→mag)
            next_idx = self._active_idx + 1
            if next_idx >= len(self._boxes):
                next_idx = 0
            self._set_active(next_idx)
        else:
            # Direction hundreds (box 0): values 4–9 always exceed 359° – reject
            if self._active_idx == 0 and key in ('4', '5', '6', '7', '8', '9'):
                return
            self._boxes[self._active_idx].set_digit(key)
            # After filling the third direction digit clamp to 359
            if self._active_idx == 2:
                self._clamp_direction()
            next_idx = self._active_idx + 1
            if next_idx < len(self._boxes):
                self._set_active(next_idx)
        self._update_compass()

    def _clamp_direction(self):
        """If the 3-digit direction value exceeds 359, snap it to 359."""
        dir_str = "".join(b.digit() or "0" for b in self._boxes[0:3])
        try:
            val = int(dir_str)
        except ValueError:
            return
        if val > 359:
            for i, ch in enumerate("359"):
                self._boxes[i].set_digit(ch)

    # ------------------------------------------------------------------
    # Pre-fill
    # ------------------------------------------------------------------
    def _load_initial(self, direction: int, magnitude: int):
        # Direction: zero-pad to 3 digits
        d_str = f"{max(0, min(359, direction)):03d}"
        # Magnitude: zero-pad to 3 digits
        m_str = f"{max(0, min(999, magnitude)):03d}"
        for i, ch in enumerate(d_str):
            self._boxes[i].set_digit(ch)
        for i, ch in enumerate(m_str):
            self._boxes[3 + i].set_digit(ch)
        self._update_compass()

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------
    def confirm(self):
        """Programmatically confirm with current values (e.g. via joystick ack)."""
        self._on_confirm()

    def _on_confirm(self):
        dir_str = "".join(b.digit() or "0" for b in self._boxes[0:3])
        mag_str = "".join(b.digit() or "0" for b in self._boxes[3:6])
        try:
            direction = int(dir_str)
            magnitude = int(mag_str)
        except ValueError:
            direction, magnitude = 0, 0

        # Clamp
        direction = direction % 360
        magnitude = max(0, magnitude)

        self.confirmed.emit(direction, magnitude)
        self.accept()

    # ------------------------------------------------------------------
    # Crosswind helper (static, exported for gui_agent use)
    # ------------------------------------------------------------------
    @staticmethod
    def compute_crosswind(wind_dir: int, wind_mag: int, runway_heading: int) -> dict:
        """
        Compute crosswind and headwind components.
        Returns dict with keys: crosswind, headwind, side ('left'/'right'), angle_deg
        """
        angle_rad = math.radians(wind_dir - runway_heading)
        crosswind = wind_mag * math.sin(angle_rad)
        headwind  = wind_mag * math.cos(angle_rad)
        side = "right" if crosswind >= 0 else "left"
        return {
            "crosswind": abs(crosswind),
            "headwind": headwind,
            "side": side,
            "angle_deg": math.degrees(angle_rad) % 360,
        }
