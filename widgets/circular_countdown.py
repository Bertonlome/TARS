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
    
    def set_colors(self, progress_color=None, background_color=None, text_color=None):
        """
        Set custom colors for the widget
        
        Args:
            progress_color: Color for the progress arc
            background_color: Color for the background circle
            text_color: Color for the text
        """
        if progress_color:
            self._progress_color = QColor(progress_color)
        if background_color:
            self._circle_color = QColor(background_color)
        if text_color:
            self._text_color = QColor(text_color)
        self.update()
    
    def paintEvent(self, event):
        """
        Paint the circular countdown
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Get dimensions
        width = self.width()
        height = self.height()
        size = min(width, height)
        
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
        
        # Draw text (countdown value)
        painter.setPen(self._text_color)
        
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
        
        label_rect = QtCore.QRectF(0, size * 0.55, size, size * 0.45)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, "sec")
        
        painter.end()
