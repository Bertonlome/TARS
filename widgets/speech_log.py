"""
Speech Log Widget
Chat-style sliding message log for TARS (right) and ATC (left) speech.
Resets on TARS agent reset.
"""

from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QScroller


class SpeechLogWidget(QWidget):
    """
    Scrolling chat log showing TARS messages on the right and ATC on the left.
    New messages are appended at the bottom and the view auto-scrolls.
    Call clear_log() to wipe all messages (e.g. on TARS reset).
    """

    # Visual style constants
    TARS_TEXT_COLOR  = "#55aaff"              # Blue label for TARS sender tag
    TARS_BG_COLOR    = "rgba(85, 170, 255, 20)"
    TARS_BORDER      = "rgba(85, 170, 255, 70)"

    ATC_TEXT_COLOR   = "#ffaa55"              # Orange label for ATC sender tag
    ATC_BG_COLOR     = "rgba(255, 170, 85, 20)"
    ATC_BORDER       = "rgba(255, 170, 85, 70)"

    PILOT_TEXT_COLOR = "#55cc77"              # Green label for pilot sender tag
    PILOT_BG_COLOR   = "rgba(85, 204, 119, 20)"
    PILOT_BORDER     = "rgba(85, 204, 119, 70)"

    # Typewriter speed for ATC animated reveal (words per second).
    # Tune to match audio elocution pace: 2.0 ≈ slow/clear ATC, 3.0 ≈ normal speech.
    ATC_TYPEWRITER_SPEED: float = 0.5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.NoFrame)

        # Enable touch / click-and-drag kinetic scrolling on the whole viewport
        QScroller.grabGesture(
            self.scroll_area.viewport(),
            QScroller.ScrollerGestureType.TouchGesture
        )
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(33, 37, 43, 180);
                width: 5px;
                border-radius: 2px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(85, 170, 255, 100);
                border-radius: 2px;
                min-height: 16px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0px; }
        """)

        # Inner container for message bubbles
        self.messages_widget = QWidget()
        self.messages_widget.setStyleSheet("background-color: transparent;")
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(6, 6, 6, 6)
        self.messages_layout.setSpacing(5)
        # Trailing stretch keeps messages pinned to the top while there are
        # few of them, and naturally floats as the list grows.
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_widget)
        outer.addWidget(self.scroll_area)

        # Auto-scroll whenever the scrollable range grows (new content or
        # animated bubble expansion) so new messages are always visible.
        self.scroll_area.verticalScrollBar().rangeChanged.connect(
            lambda _min, _max: self.scroll_area.verticalScrollBar().setValue(_max)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append_tars_message(self, text: str):
        """Add a TARS message bubble (right-aligned, blue)."""
        text = text.strip()
        if not text:
            return
        bubble, _ = self._make_bubble(text, "TARS")
        self._insert_bubble(bubble)

    def append_atc_message(self, text: str):
        """Add an ATC message bubble — delegates to the animated variant."""
        self.append_atc_message_animated(text)

    def append_atc_message_animated(self, text: str, speed_rate: float | None = None):
        """
        Add an ATC message bubble that reveals its text word-by-word.

        Args:
            text:       The full message string.
            speed_rate: Words per second. Defaults to ATC_TYPEWRITER_SPEED.
                        Tune to match the audio elocution pace.
        """
        text = text.strip()
        if not text:
            return
        if speed_rate is None:
            speed_rate = self.ATC_TYPEWRITER_SPEED

        # Build bubble with an empty placeholder — the animation fills it in.
        bubble, msg_lbl = self._make_bubble("", "ATC")
        self._insert_bubble(bubble)

        words = text.split()
        interval_ms = max(40, int(1000 / speed_rate))
        self._reveal_next_word(msg_lbl, words, interval_ms, 0)

    def append_pilot_message(self, text: str):
        """Add a pilot STT bubble (left-aligned, green)."""
        text = text.strip()
        if not text:
            return
        bubble, _ = self._make_bubble(text, "You (pilot)")
        self._insert_bubble(bubble)

    def append_state_divider(self, label: str):
        """Add a faint centred divider row showing the new FSM state."""
        label = label.strip()
        if not label:
            return
        divider = self._make_divider(label)
        self._insert_bubble(divider)

    def clear_log(self):
        """Remove all message bubbles (call on TARS reset)."""
        # Remove everything except the trailing stretch (last item)
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_divider(self, label: str) -> QWidget:
        """Build a full-width divider row with a centred state label."""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 6, 4, 6)
        row_layout.setSpacing(6)

        def _line():
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            line.setStyleSheet("border: none; border-top: 1px solid rgba(255,255,255,30);")
            return line

        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        lbl.setStyleSheet(
            "font: 500 7pt 'JetBrains Mono'; "
            "color: rgba(255,255,255,55); "
            "background: transparent; border: none; "
            "padding: 0 6px;"
        )

        row_layout.addWidget(_line())
        row_layout.addWidget(lbl)
        row_layout.addWidget(_line())
        return row

    def _make_bubble(self, text: str, sender: str) -> tuple["QWidget", "QLabel"]:
        """Build a single row widget containing a styled bubble.

        Returns:
            (row_widget, msg_label) — callers that animate need the label ref.
        """
        is_tars  = (sender == "TARS")
        is_pilot = (sender == "You (pilot)")

        # Colour scheme
        if is_tars:
            label_color  = self.TARS_TEXT_COLOR
            bg_color     = self.TARS_BG_COLOR
            border_color = self.TARS_BORDER
        elif is_pilot:
            label_color  = self.PILOT_TEXT_COLOR
            bg_color     = self.PILOT_BG_COLOR
            border_color = self.PILOT_BORDER
        else:
            label_color  = self.ATC_TEXT_COLOR
            bg_color     = self.ATC_BG_COLOR
            border_color = self.ATC_BORDER

        # Row spans full width; bubble is constrained and floated L or R
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        # Bubble frame
        bubble = QFrame()
        bubble.setMaximumWidth(360)
        bubble.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)
        bubble.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 7px;
            }}
        """)

        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(8, 4, 8, 4)
        bubble_layout.setSpacing(2)

        # Sender tag
        sender_lbl = QLabel(sender)
        sender_lbl.setStyleSheet(
            f"font: 700 8pt 'JetBrains Mono'; color: {label_color}; "
            "background: transparent; border: none;"
        )

        # Message text
        msg_lbl = QLabel(f"\u201c{text}\u201d")   # typographic quotes
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            "font: 500 10pt 'JetBrains Mono'; color: rgba(255,255,255,220); "
            "background: transparent; border: none;"
        )
        msg_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        bubble_layout.addWidget(sender_lbl)
        bubble_layout.addWidget(msg_lbl)

        # Float: TARS → right; ATC / pilot → left
        if is_tars:
            row_layout.addStretch()
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch()

        return row, msg_lbl

    def _reveal_next_word(self, label: "QLabel", words: list, interval_ms: int, index: int):
        """Recursively reveal one more word every interval_ms milliseconds."""
        if index > len(words):
            return
        visible = words[:index]
        if index == 0:
            label.setText("")                               # blank on first tick
        elif index < len(words):
            label.setText("“" + " ".join(visible) + "…”")   # trailing ellipsis while typing
        else:
            label.setText("“" + " ".join(visible) + "”")    # closing quote when done
        if index <= len(words):
            QTimer.singleShot(
                interval_ms,
                lambda: self._reveal_next_word(label, words, interval_ms, index + 1)
            )

    def _insert_bubble(self, bubble: QWidget):
        """Insert bubble before the trailing stretch and scroll to bottom."""
        count = self.messages_layout.count()
        # The last item is the stretch spacer; insert just before it
        self.messages_layout.insertWidget(count - 1, bubble)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        """Defer scroll so the layout has time to update first."""
        QTimer.singleShot(60, self._do_scroll)

    def _do_scroll(self):
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())
