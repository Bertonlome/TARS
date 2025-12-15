"""
Circular Countdown Widget
A visual countdown timer with a circular progress indicator
"""

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QConicalGradient
from PySide6.QtWidgets import QWidget


class CircularCountdown(QWidget):
    """
    A circular countdown widget with animated progress ring
    Similar to a movie countdown timer
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Countdown properties
        self._value = 0
        self._max_value = 100
        self._progress = 100.0  # 0-100, starts at 100 (full circle)
        self._display_value = 0.0  # Float value for smooth animation
        
        # Visual properties
        self._circle_color = QColor(52, 59, 72)  # Background circle
        self._progress_color = QColor(85, 170, 255)  # Progress arc color
        self._text_color = QColor(210, 210, 210)  # Text color
        self._ring_width = 8
        
        # Task firing properties
        self._show_tick = False
        self._tick_color = QColor(85, 170, 255)  # Blue tick mark
        self._tick_animation_timer = None
        self._delayed_tick_timer = None  # Timer for delayed tick mark display
        
        # N/A state (waiting for acknowledgment)
        self._show_na = False
        
        # Animation
        self._animation = QPropertyAnimation(self, b"progress")
        self._animation.setEasingCurve(QEasingCurve.Type.Linear)
        
        # Setup
        self.setMinimumSize(80, 80)
        
    def get_progress(self):
        return self._progress
    
    def set_progress(self, value):
        self._progress = value
        # Update the display value to match the progress
        # This makes the number animate smoothly as the progress changes
        if self._max_value > 0:
            self._display_value = (value / 100.0) * self._max_value
        else:
            self._display_value = 0.0
        self.update()  # Trigger repaint
    
    # Define as Qt Property for animation
    progress = Property(float, get_progress, set_progress)
    
    def set_value(self, current, maximum):
        """
        Set the countdown value and maximum (instant, no animation)
        
        Args:
            current: Current countdown value
            maximum: Maximum value (starting value)
        """
        # IMPORTANT: Stop any running animation first
        self._animation.stop()
        
        # Reset N/A mode when setting a value
        self._show_na = False
        
        # Only reset tick mark if we're starting a NEW countdown (from 0 or different task)
        # Don't reset if just updating the same countdown
        if current > 0 and maximum > 0:
            # Starting a new countdown - reset tick mark
            self._show_tick = False
            
            # Stop any pending tick mark timers
            if self._tick_animation_timer:
                self._tick_animation_timer.stop()
                self._tick_animation_timer.deleteLater()
                self._tick_animation_timer = None
            if self._delayed_tick_timer:
                self._delayed_tick_timer.stop()
                self._delayed_tick_timer.deleteLater()
                self._delayed_tick_timer = None
        
        self._value = current
        self._display_value = float(current)
        self._max_value = maximum if maximum > 0 else 1
        
        # Calculate progress percentage (100 = full, 0 = empty)
        if self._max_value > 0:
            self._progress = (current / self._max_value) * 100.0
        else:
            self._progress = 0.0
        
        self.update()
    
    def animate_to(self, target_value, duration_ms=1000):
        """
        Animate the progress to a target value
        
        Args:
            target_value: Target countdown value
            duration_ms: Animation duration in milliseconds
        """
        # Reset N/A mode when starting an animation
        self._show_na = False
        
        if self._max_value > 0:
            target_progress = (target_value / self._max_value) * 100.0
        else:
            target_progress = 0.0
        
        # Don't set _value immediately - let the animation update it via progress property
        # Store the target for reference
        self._target_value = target_value
        
        self._animation.stop()
        self._animation.setDuration(duration_ms)
        self._animation.setStartValue(self._progress)  # Start from current progress
        self._animation.setEndValue(target_progress)    # Animate to target progress
        self._animation.start()
    
    def set_colors(self, progress_color=None, background_color=None, text_color=None, tick_color=None):
        """
        Set custom colors for the widget
        
        Args:
            progress_color: Color for the progress arc
            background_color: Color for the background circle
            text_color: Color for the text
            tick_color: Color for the tick mark when task fires
        """
        if progress_color:
            self._progress_color = QColor(progress_color)
        if background_color:
            self._circle_color = QColor(background_color)
        if text_color:
            self._text_color = QColor(text_color)
        if tick_color:
            self._tick_color = QColor(tick_color)
        self.update()
    
    def show_task_fired(self, duration_ms=2000):
        """
        Show a tick mark indicating the task has fired
        
        Args:
            duration_ms: How long to show the tick mark (default: 2 seconds)
        """
        # Stop any existing animation
        if self._animation:
            self._animation.stop()
        
        # Show tick mark
        self._show_tick = True
        self.update()
        
        # Set up timer to hide tick mark after duration
        if self._tick_animation_timer:
            self._tick_animation_timer.stop()
            self._tick_animation_timer.deleteLater()
            self._tick_animation_timer = None
        
        # Create timer with parent to prevent garbage collection
        self._tick_animation_timer = QTimer(self)
        self._tick_animation_timer.setSingleShot(True)
        self._tick_animation_timer.timeout.connect(self._hide_tick_mark)
        self._tick_animation_timer.start(duration_ms)
    
    def schedule_task_fired(self, delay_ms=500, duration_ms=2000):
        """
        Schedule a tick mark to appear after a delay (for synchronization)
        
        Args:
            delay_ms: Delay before showing tick mark (default: 500ms = 0.5 seconds)
            duration_ms: How long to show the tick mark (default: 2 seconds)
        """
        # Stop any existing delayed tick timer
        if self._delayed_tick_timer:
            self._delayed_tick_timer.stop()
            self._delayed_tick_timer.deleteLater()
            self._delayed_tick_timer = None
        
        # Create timer for delayed tick mark with parent to prevent garbage collection
        self._delayed_tick_timer = QTimer(self)
        self._delayed_tick_timer.setSingleShot(True)
        self._delayed_tick_timer.timeout.connect(lambda: self.show_task_fired(duration_ms))
        self._delayed_tick_timer.start(delay_ms)
    
    def _hide_tick_mark(self):
        """Hide the tick mark and return to normal countdown display"""
        self._show_tick = False
        self.update()
        
        # Clean up timer
        if self._tick_animation_timer:
            self._tick_animation_timer.stop()
            self._tick_animation_timer = None
    
    def reset_to_countdown(self):
        """Reset widget to normal countdown mode (hide tick mark and N/A)"""
        self._show_tick = False
        self._show_na = False
        if self._tick_animation_timer:
            self._tick_animation_timer.stop()
            self._tick_animation_timer = None
        if self._delayed_tick_timer:
            self._delayed_tick_timer.stop()
            self._delayed_tick_timer = None
        self.update()
    
    def set_na(self):
        """
        Set widget to N/A mode (waiting for acknowledgment)
        Shows "N/A" text with a non-lit circle
        """
        # Stop any animations
        self._animation.stop()
        if self._tick_animation_timer:
            self._tick_animation_timer.stop()
            self._tick_animation_timer = None
        if self._delayed_tick_timer:
            self._delayed_tick_timer.stop()
            self._delayed_tick_timer = None
        
        # Set to N/A mode
        self._show_tick = False
        self._show_na = True
        self._progress = 0.0  # Empty circle (non-lit)
        self._value = 0
        self._display_value = 0.0
        
        self.update()
    
    def paintEvent(self, event):
        """
        Paint the circular countdown or tick mark
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Get dimensions
        width = self.width()
        height = self.height()
        size = min(width, height)
        
        if self._show_tick:
            # Draw tick mark mode (task fired)
            self._draw_tick_mark(painter, size)
        else:
            # Draw normal countdown mode
            self._draw_countdown(painter, size)
        
        painter.end()
    
    def _draw_countdown(self, painter, size):
        """Draw the normal countdown display"""
        # Calculate rectangle for arcs
        margin = self._ring_width
        rect = QtCore.QRectF(margin, margin, size - 2*margin, size - 2*margin)
        
        # Draw background circle
        pen = QPen(self._circle_color)
        pen.setWidth(self._ring_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)  # Full circle
        
        # Draw progress arc
        if self._progress > 0:
            pen = QPen(self._progress_color)
            pen.setWidth(self._ring_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            
            # Start angle at top (90 degrees) and draw clockwise
            # Qt uses 1/16th degree units, positive angles go counter-clockwise
            start_angle = 90 * 16  # Start at top
            span_angle = -(self._progress / 100.0) * 360 * 16  # Negative for clockwise
            
            painter.drawArc(rect, start_angle, int(span_angle))
        
        # Draw text (countdown value or N/A)
        painter.setPen(self._text_color)
        
        if self._show_na:
            # N/A mode - larger text, no "sec" label
            font = QFont("JetBrains Mono", 18, QFont.Weight.Medium)
            painter.setFont(font)
            
            text_rect = QtCore.QRectF(0, 0, size, size)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "N/A")
        else:
            # Normal countdown mode
            # Large font for the number
            font = QFont("JetBrains Mono", 20, QFont.Weight.Medium)
            painter.setFont(font)
            
            # Use the animated display value, rounded to nearest integer
            display_text = str(int(round(self._display_value)))
            
            text_rect = QtCore.QRectF(0, 0, size, size * 0.6)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, display_text)
            
            # Small font for "sec" label
            font_small = QFont("JetBrains Mono", 9, QFont.Weight.Light)
            painter.setFont(font_small)
            
            label_rect = QtCore.QRectF(0, size * 0.45, size, size * 0.45)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, "sec")
    
    def _draw_tick_mark(self, painter, size):
        """Draw the tick mark (task fired) display"""
        # Draw background circle in green
        margin = self._ring_width
        rect = QtCore.QRectF(margin, margin, size - 2*margin, size - 2*margin)
        
        pen = QPen(self._tick_color)
        pen.setWidth(self._ring_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)  # Full circle in green
        
        # Draw tick mark (checkmark) in center
        tick_pen = QPen(self._tick_color)
        tick_pen.setWidth(4)
        tick_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(tick_pen)
        
        # Calculate checkmark coordinates
        center_x = size / 2
        center_y = size / 2
        check_size = size * 0.25  # Size of checkmark relative to widget
        
        # Checkmark points
        from PySide6.QtCore import QPointF
        # Start point (bottom-left of check)
        p1 = QPointF(center_x - check_size * 0.5, center_y)
        # Middle point (bottom of check)  
        p2 = QPointF(center_x - check_size * 0.1, center_y + check_size * 0.3)
        # End point (top-right of check)
        p3 = QPointF(center_x + check_size * 0.5, center_y - check_size * 0.3)
        
        # Draw checkmark as two lines
        painter.drawLine(p1, p2)  # Left stroke
        painter.drawLine(p2, p3)  # Right stroke
