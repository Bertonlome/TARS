"""
Chrono Edit Dialog
A self-contained two-phase popup:
  Phase 0 – SET: numpad to type duration in seconds.
  Phase 1 – RUN: internal QTimer counts down; emits `completed` at zero.
"""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QStackedWidget, QWidget
)
from PySide6.QtGui import QFont


# ---------------------------------------------------------------------------
# Shared dark-theme style constants (match wind_edit_dialog)
# ---------------------------------------------------------------------------
_BG_DEEP   = "rgb(27, 31, 37)"
_BG_MID    = "rgb(33, 37, 43)"
_BG_PANEL  = "rgb(44, 49, 60)"
_BORDER    = "rgb(52, 59, 72)"
_BLUE      = "#55aaff"
_GREEN     = "#55de71"
_RED       = "#ff5555"
_ORANGE    = "#ffaa55"
_WHITE     = "white"


# ---------------------------------------------------------------------------
# Single digit display box
# ---------------------------------------------------------------------------
class _DigitBox(QLabel):
    clicked_signal = Signal(object)

    def __init__(self, parent=None):
        super().__init__("0", parent)
        self._active = False
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(62, 72)
        self.setFont(QFont("JetBrains Mono", 28, QFont.Bold))
        self._refresh_style()

    def set_digit(self, ch: str):
        self.setText(ch if ch else "0")

    def digit(self) -> str:
        return self.text()

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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked_signal.emit(self)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Chrono Edit Dialog
# ---------------------------------------------------------------------------
class ChronoEditDialog(QDialog):
    """
    Two-phase countdown dialog.

    Phase 0 – SET: operator types a duration (seconds) with the numpad,
               then clicks START.
    Phase 1 – RUN: countdown runs inside the dialog.  At zero the dialog
               closes automatically and emits ``completed``.

    Signals
    -------
    completed()
        Emitted when the countdown reaches zero.
    """

    completed = Signal()

    _PHASE_SET = 0
    _PHASE_RUN = 1

    def __init__(self, parent=None, initial_seconds: int = 30, auto_start: bool = False, auto_start_delay_ms: int = 0):
        super().__init__(parent)
        self.setWindowTitle("CHRONO")
        self.setModal(True)
        self.setFixedSize(390, 510)
        self.setStyleSheet(
            f"QDialog {{ background-color: {_BG_MID}; color: {_WHITE}; }}"
        )

        # Three digit boxes for 000–999 seconds
        self._boxes: list[_DigitBox] = [_DigitBox(self) for _ in range(3)]
        self._active_idx = 0
        for i, box in enumerate(self._boxes):
            box.clicked_signal.connect(lambda _, idx=i: self._set_active(idx))

        self._remaining = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        self._build_ui()
        self._load_initial(initial_seconds)

        if auto_start:
            QTimer.singleShot(max(0, auto_start_delay_ms), self._start_countdown)

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # Phase label (changes between phases)
        self._title = QLabel("SET DURATION")
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setFont(QFont("JetBrains Mono", 11, QFont.Bold))
        self._title.setStyleSheet(f"color: {_BLUE};")
        root.addWidget(self._title)

        # Stacked: phase 0 = SET, phase 1 = RUN
        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._stack.addWidget(self._build_set_phase())  # index 0
        self._stack.addWidget(self._build_run_phase())  # index 1

    # ---- Phase 0: SET -----------------------------------------------
    def _build_set_phase(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Digit display
        disp = QFrame()
        disp.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG_DEEP};
                border: 2px solid {_BORDER};
                border-radius: 10px;
            }}
        """)
        disp_l = QHBoxLayout(disp)
        disp_l.setContentsMargins(16, 12, 16, 12)
        disp_l.setSpacing(8)
        disp_l.addStretch()
        for box in self._boxes:
            disp_l.addWidget(box)
        disp_l.addStretch()
        unit = QLabel("sec")
        unit.setFont(QFont("JetBrains Mono", 18, QFont.Bold))
        unit.setStyleSheet(
            f"color: {_BLUE}; border: none; background: transparent;"
        )
        disp_l.addWidget(unit)
        layout.addWidget(disp)

        # Numpad
        pad = QFrame()
        pad.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG_PANEL};
                border: 2px solid {_BORDER};
                border-radius: 10px;
            }}
        """)
        grid = QGridLayout(pad)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(8)
        keys = [
            ("7", 0, 0), ("8", 0, 1), ("9", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("1", 2, 0), ("2", 2, 1), ("3", 2, 2),
            ("CLR", 3, 0), ("0", 3, 1), ("\u232b", 3, 2),
        ]
        for text, row, col in keys:
            grid.addWidget(self._make_key(text), row, col)
        layout.addWidget(pad)

        # CANCEL / START buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel = QPushButton("CANCEL")
        cancel.setFixedHeight(46)
        cancel.setFont(QFont("JetBrains Mono", 11, QFont.Bold))
        cancel.setStyleSheet(f"""
            QPushButton {{ color: {_RED}; background: {_BG_DEEP};
                           border: 2px solid {_RED}; border-radius: 8px; }}
            QPushButton:hover   {{ background: rgba(255,85,85,30); }}
            QPushButton:pressed {{ background: rgba(255,85,85,60); }}
        """)
        cancel.clicked.connect(self.reject)

        start = QPushButton("START")
        start.setFixedHeight(46)
        start.setFont(QFont("JetBrains Mono", 11, QFont.Bold))
        start.setStyleSheet(f"""
            QPushButton {{ color: {_GREEN}; background: {_BG_DEEP};
                           border: 2px solid {_GREEN}; border-radius: 8px; }}
            QPushButton:hover   {{ background: rgba(85,222,113,30); }}
            QPushButton:pressed {{ background: rgba(85,222,113,60); }}
        """)
        start.clicked.connect(self._start_countdown)

        btn_row.addWidget(cancel)
        btn_row.addWidget(start)
        layout.addLayout(btn_row)
        return w

    # ---- Phase 1: RUN -----------------------------------------------
    def _build_run_phase(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        layout.addStretch()

        # Big countdown display
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG_DEEP};
                border: 2px solid {_BORDER};
                border-radius: 16px;
            }}
        """)
        frame_l = QVBoxLayout(frame)
        frame_l.setContentsMargins(20, 36, 20, 36)
        self._countdown_label = QLabel("00:00")
        self._countdown_label.setAlignment(Qt.AlignCenter)
        self._countdown_label.setFont(QFont("JetBrains Mono", 54, QFont.Bold))
        self._countdown_label.setStyleSheet(
            f"color: {_BLUE}; border: none; background: transparent;"
        )
        frame_l.addWidget(self._countdown_label)
        layout.addWidget(frame)

        layout.addStretch()

        # ABORT button
        abort = QPushButton("ABORT")
        abort.setFixedHeight(46)
        abort.setFont(QFont("JetBrains Mono", 11, QFont.Bold))
        abort.setStyleSheet(f"""
            QPushButton {{ color: {_RED}; background: {_BG_DEEP};
                           border: 2px solid {_RED}; border-radius: 8px; }}
            QPushButton:hover   {{ background: rgba(255,85,85,30); }}
            QPushButton:pressed {{ background: rgba(255,85,85,60); }}
        """)
        abort.clicked.connect(self._abort)
        layout.addWidget(abort)
        return w

    # ------------------------------------------------------------------
    # Numpad key factory
    # ------------------------------------------------------------------
    def _make_key(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(84, 56)
        btn.setFont(QFont("JetBrains Mono", 15, QFont.Bold))
        color = _RED if text in ("CLR", "\u232b") else _WHITE
        btn.setStyleSheet(f"""
            QPushButton {{ color: {color}; background: {_BG_DEEP};
                           border: 2px solid {_BORDER}; border-radius: 8px; }}
            QPushButton:hover   {{ background: rgb(44,49,60); border-color: {_BLUE}; }}
            QPushButton:pressed {{ background: rgb(55,62,72); }}
        """)
        btn.clicked.connect(lambda _, t=text: self._key_pressed(t))
        return btn

    # ------------------------------------------------------------------
    # Logic
    # ------------------------------------------------------------------
    def _load_initial(self, seconds: int):
        s = max(0, min(999, seconds))
        for box, ch in zip(self._boxes, f"{s:03d}"):
            box.set_digit(ch)
        self._set_active(0)

    def _set_active(self, idx: int):
        for i, box in enumerate(self._boxes):
            box.set_active(i == idx)
        self._active_idx = idx

    def _key_pressed(self, text: str):
        if text == "CLR":
            for box in self._boxes:
                box.set_digit("0")
            self._set_active(0)
        elif text == "\u232b":
            self._boxes[self._active_idx].set_digit("0")
            if self._active_idx > 0:
                self._set_active(self._active_idx - 1)
        elif text.isdigit():
            self._boxes[self._active_idx].set_digit(text)
            if self._active_idx < len(self._boxes) - 1:
                self._set_active(self._active_idx + 1)

    def _value(self) -> int:
        try:
            return int("".join(box.digit() for box in self._boxes))
        except ValueError:
            return 0

    def _start_countdown(self):
        s = self._value()
        if s <= 0:
            return
        self._remaining = s
        self._title.setText("COUNTING DOWN")
        self._update_display()
        self._stack.setCurrentIndex(self._PHASE_RUN)
        self._timer.start()

    def _tick(self):
        self._remaining -= 1
        self._update_display()
        if self._remaining <= 0:
            self._timer.stop()
            self.completed.emit()
            self.accept()

    def _update_display(self):
        mins = self._remaining // 60
        secs = self._remaining % 60
        self._countdown_label.setText(f"{mins:02d}:{secs:02d}")
        # Colour shift: orange at ≤30 s, red at ≤10 s
        if self._remaining <= 10:
            color = _RED
        elif self._remaining <= 30:
            color = _ORANGE
        else:
            color = _BLUE
        self._countdown_label.setStyleSheet(
            f"color: {color}; border: none; background: transparent;"
        )

    def _abort(self):
        self._timer.stop()
        self.reject()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)



# ---------------------------------------------------------------------------
# Single digit display box (reuse same pattern as wind_edit_dialog)
# ---------------------------------------------------------------------------
class _DigitBox(QLabel):
    clicked_signal = Signal(object)  # emits self

    def __init__(self, parent=None):
        super().__init__("_", parent)
        self._active = False
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(62, 72)
        font = QFont("JetBrains Mono", 28, QFont.Bold)
        self.setFont(font)
        self._refresh_style()

    def set_digit(self, ch: str):
        self.setText(ch if ch else "_")

    def digit(self) -> str:
        t = self.text()
        return t if t != "_" else ""

    def is_empty(self) -> bool:
        return self.text() == "_"

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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked_signal.emit(self)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Chrono Value Editor Dialog (simple value-only editor, no countdown)
# ---------------------------------------------------------------------------
class ChronoValueEditor(QDialog):
    """
    Popup dialog for editing the countdown duration (seconds).

    Signals
    -------
    confirmed(seconds: int)
        Emitted when the user accepts the value.
    """

    confirmed = Signal(int)

    def __init__(self, parent=None, initial_seconds: int = 0):
        super().__init__(parent)
        self.setWindowTitle("EDIT CHRONO")
        self.setModal(True)
        self.setFixedSize(380, 460)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {_BG_MID};
                color: {_WHITE};
            }}
        """)

        # Up to 3 digit boxes for 0–999 seconds
        self._boxes: list[_DigitBox] = [_DigitBox(self) for _ in range(3)]
        self._active_idx: int = 0

        for i, box in enumerate(self._boxes):
            box.clicked_signal.connect(lambda b, idx=i: self._set_active(idx))

        self._build_ui()
        self._load_initial(initial_seconds)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # Title
        title = QLabel("CHRONOMETER DURATION")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("JetBrains Mono", 11, QFont.Bold))
        title.setStyleSheet(f"color: {_BLUE};")
        root.addWidget(title)

        # Digit display row
        display_frame = QFrame()
        display_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG_DEEP};
                border: 2px solid {_BORDER};
                border-radius: 10px;
            }}
        """)
        display_layout = QHBoxLayout(display_frame)
        display_layout.setContentsMargins(16, 12, 16, 12)
        display_layout.setSpacing(8)
        display_layout.addStretch()
        for box in self._boxes:
            display_layout.addWidget(box)
        display_layout.addStretch()

        # "s" unit label to the right
        unit_label = QLabel("sec")
        unit_label.setFont(QFont("JetBrains Mono", 18, QFont.Bold))
        unit_label.setStyleSheet(f"color: {_BLUE}; border: none; background: transparent;")
        display_layout.addWidget(unit_label)
        root.addWidget(display_frame)

        # Hint label
        hint = QLabel("Click a digit to select, then press a key")
        hint.setAlignment(Qt.AlignCenter)
        hint.setFont(QFont("JetBrains Mono", 8))
        hint.setStyleSheet(f"color: rgb(130,130,150); border: none; background: transparent;")
        root.addWidget(hint)

        # Numeric keypad (3×4 grid: 1-9, ., 0, ⌫)
        keypad_frame = QFrame()
        keypad_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG_PANEL};
                border: 2px solid {_BORDER};
                border-radius: 10px;
            }}
        """)
        keypad_layout = QGridLayout(keypad_frame)
        keypad_layout.setContentsMargins(12, 12, 12, 12)
        keypad_layout.setSpacing(8)

        keys = [
            ("7", 0, 0), ("8", 0, 1), ("9", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("1", 2, 0), ("2", 2, 1), ("3", 2, 2),
            ("CLR", 3, 0), ("0", 3, 1), ("⌫", 3, 2),
        ]
        for text, row, col in keys:
            btn = self._make_key(text)
            keypad_layout.addWidget(btn, row, col)
        root.addWidget(keypad_frame)

        # OK / Cancel buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setFixedHeight(46)
        cancel_btn.setFont(QFont("JetBrains Mono", 11, QFont.Bold))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                color: {_RED};
                background-color: {_BG_DEEP};
                border: 2px solid {_RED};
                border-radius: 8px;
            }}
            QPushButton:hover  {{ background-color: rgba(255,85,85,30); }}
            QPushButton:pressed {{ background-color: rgba(255,85,85,60); }}
        """)
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("CONFIRM")
        ok_btn.setFixedHeight(46)
        ok_btn.setFont(QFont("JetBrains Mono", 11, QFont.Bold))
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                color: {_GREEN};
                background-color: {_BG_DEEP};
                border: 2px solid {_GREEN};
                border-radius: 8px;
            }}
            QPushButton:hover  {{ background-color: rgba(85,222,113,30); }}
            QPushButton:pressed {{ background-color: rgba(85,222,113,60); }}
        """)
        ok_btn.clicked.connect(self._confirm)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Key button factory
    # ------------------------------------------------------------------
    def _make_key(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(80, 56)
        btn.setFont(QFont("JetBrains Mono", 15, QFont.Bold))
        if text in ("CLR", "⌫"):
            color = _RED
        else:
            color = _WHITE
        btn.setStyleSheet(f"""
            QPushButton {{
                color: {color};
                background-color: {_BG_DEEP};
                border: 2px solid {_BORDER};
                border-radius: 8px;
            }}
            QPushButton:hover  {{ background-color: rgb(44,49,60); border-color: {_BLUE}; }}
            QPushButton:pressed {{ background-color: rgb(55,62,72); }}
        """)
        btn.clicked.connect(lambda _, t=text: self._key_pressed(t))
        return btn

    # ------------------------------------------------------------------
    # Logic
    # ------------------------------------------------------------------
    def _load_initial(self, seconds: int):
        """Populate boxes from an integer number of seconds (0–999)."""
        s = max(0, min(999, seconds))
        digits = f"{s:03d}"  # pad to 3 digits
        for box, ch in zip(self._boxes, digits):
            box.set_digit(ch)
        self._set_active(0)

    def _set_active(self, idx: int):
        for i, box in enumerate(self._boxes):
            box.set_active(i == idx)
        self._active_idx = idx

    def _key_pressed(self, text: str):
        if text == "CLR":
            for box in self._boxes:
                box.set_digit("0")
            self._set_active(0)
        elif text == "⌫":
            # Move left and clear
            idx = self._active_idx
            self._boxes[idx].set_digit("0")
            if idx > 0:
                self._set_active(idx - 1)
        elif text.isdigit():
            self._boxes[self._active_idx].set_digit(text)
            # Advance to next box (if any)
            if self._active_idx < len(self._boxes) - 1:
                self._set_active(self._active_idx + 1)

    def _value(self) -> int:
        """Return current input as an integer (0–999)."""
        digits = "".join(box.digit() or "0" for box in self._boxes)
        try:
            return int(digits)
        except ValueError:
            return 0

    def _confirm(self):
        self.confirmed.emit(self._value())
        self.accept()
