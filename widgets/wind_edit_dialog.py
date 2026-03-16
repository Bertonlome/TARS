"""
Wind Edit Dialog
A popup dialog for editing wind orientation and magnitude with a virtual numeric keyboard.
"""

import math
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QSizePolicy, QWidget
)
from PySide6.QtGui import QFont


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
                 initial_dir: int = 0, initial_mag: int = 0):
        super().__init__(parent)
        self.setWindowTitle("WIND EDITOR")
        self.setModal(True)
        self.setFixedSize(520, 620)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {_BG_MID};
                color: {_WHITE};
            }}
        """)

        self._runway_heading = runway_heading

        # 6 digit boxes: [dir_h, dir_t, dir_u, mag_h, mag_t, mag_u]
        self._boxes: list[_DigitBox] = [_DigitBox(self) for _ in range(6)]
        self._active_idx: int = 0

        for i, box in enumerate(self._boxes):
            box.clicked_signal.connect(lambda b, idx=i: self._set_active(idx))

        self._build_ui()
        self._load_initial(initial_dir, initial_mag)
        self._set_active(0)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(16)

        # ---- Title ----
        title = QLabel("WIND EDITOR")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("JetBrains Mono", 14, QFont.Bold))
        title.setStyleSheet(f"color: {_BLUE}; letter-spacing: 3px;")
        root.addWidget(title)

        # ---- Direction row ----
        root.addWidget(self._make_separator())
        root.addWidget(self._build_field_row("Wind direction  (°)", 0, 3, "HDG"))

        # ---- Magnitude row ----
        root.addWidget(self._make_separator())
        root.addWidget(self._build_field_row("Wind magnitude  (kt)", 3, 6, "KT"))

        # ---- Numpad ----
        root.addWidget(self._make_separator())
        root.addLayout(self._build_numpad())

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
    # Numpad handler
    # ------------------------------------------------------------------
    def _numpad_press(self, key: str):
        if key == "⌫":
            # Clear current box and go back
            box = self._boxes[self._active_idx]
            if not box.is_empty():
                box.set_digit("_")
            elif self._active_idx > 0:
                self._set_active(self._active_idx - 1)
                self._boxes[self._active_idx].set_digit("_")
        elif key == "→":
            # Move to next box (skip groups: dir→mag)
            next_idx = self._active_idx + 1
            if next_idx >= len(self._boxes):
                next_idx = 0
            self._set_active(next_idx)
        else:
            # Digit key: fill current box, advance
            self._boxes[self._active_idx].set_digit(key)
            next_idx = self._active_idx + 1
            if next_idx < len(self._boxes):
                self._set_active(next_idx)

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

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------
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
