"""
Task Page Base
Common functionality for pages that display task timelines and countdowns
(HomePage, FlightPage, etc.)
"""

from pages.base_page import BasePage
from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import QGraphicsOpacityEffect
from widgets.circular_countdown import CircularCountdown
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.ui_main import Ui_MainWindow
    from main import MainWindow

class TaskPageBase(BasePage):
    """
    Base class for pages that show task execution with countdowns
    Contains shared countdown logic, glow effects, and interaction panel handling
    """
    
    # Signals for communicating with MainWindow
    task_done_signal = QtCore.Signal()
    task_cancel_signal = QtCore.Signal()
    task_override_signal = QtCore.Signal()  # New: signal for override (force next state)
    task_allowed_signal = QtCore.Signal()
    task_not_allowed_signal = QtCore.Signal()
    countdown_zero_signal = QtCore.Signal()
    next_step_signal = QtCore.Signal()  # Signal to jump to next state
    previous_step_signal = QtCore.Signal()  # Signal to jump to previous state
    
    def __init__(self, widgets: 'Ui_MainWindow', main_window: 'MainWindow'):
        super().__init__(widgets, main_window)
        
        # Initialize countdown timers
        self.current_countdown_timer = QtCore.QTimer(self.main_window)
        self.current_countdown_timer.setInterval(1000)
        self.current_countdown_timer.timeout.connect(self.update_current_countdown)
        self.current_countdown_value = 0
        self.current_countdown_max = 0
        
        self.next_countdown_timer = QtCore.QTimer(self.main_window)
        self.next_countdown_timer.setInterval(1000)
        self.next_countdown_timer.timeout.connect(self.update_next_countdown)
        self.next_countdown_value = 0
        self.next_countdown_max = 0
        
        # Circular countdown widgets (to be set by subclass)
        self.current_circular_countdown = None
        self.next_circular_countdown = None
        
        # Task state tracking
        self._task_cancelled = False  # Track if current task was cancelled
        self._button_in_override_mode = False  # Track if cancel button is in override mode
        
        # Glow effect tracking
        self._glow_timer = None
        self._glow_steps = []
        self._glow_index = 0
        self._glow_active_widget = None
        
        # Widget references (subclass must set these)
        self.current_task_container = None
        self.interaction_panel_text = None
        self.interaction_panel_tars_input = None
        self.int_panel_right_button = None
        self.int_panel_left_button = None
        self.check_radio_button = None
        self.cancel_task_button = None
        
    def setup_countdown_widgets(self, current_container, next_container, 
                                current_value_label, current_unit_label,
                                next_value_label, next_unit_label):
        """Setup circular countdown widgets - call from subclass
        
        Args:
            current_container: QLayout to add current countdown widget
            next_container: QLayout to add next countdown widget  
            current_value_label: QLabel to hide (replaced by circular widget)
            current_unit_label: QLabel to hide
            next_value_label: QLabel to hide
            next_unit_label: QLabel to hide
        """
        # Hide original labels
        current_value_label.hide()
        current_unit_label.hide()
        next_value_label.hide()
        next_unit_label.hide()
        
        # Create current countdown
        self.current_circular_countdown = CircularCountdown()
        self.current_circular_countdown.set_colors(
            progress_color="#55aaff",
            background_color="#343b48",
            text_color="#d2d2d2"
        )
        current_container.addWidget(self.current_circular_countdown)
        
        # Create next countdown
        self.next_circular_countdown = CircularCountdown()
        self.next_circular_countdown.set_colors(
            progress_color="#55aaff",
            background_color="#343b48",
            text_color="#d2d2d2"
        )
        next_container.addWidget(self.next_circular_countdown)
    
    def connect_task_buttons(self):
        """Connect task control buttons to handlers - call from subclass setup"""
        if self.int_panel_right_button:
            self.int_panel_right_button.clicked.connect(self.task_done_clicked)
        if self.check_radio_button:
            self.check_radio_button.clicked.connect(self.task_done_clicked)
        if self.cancel_task_button:
            self.cancel_task_button.clicked.connect(self.task_cancel_clicked)
        if self.int_panel_left_button:
            self.int_panel_left_button.clicked.connect(self.task_cancel_clicked)
    
    # COUNTDOWN METHODS
    def update_current_countdown(self):
        """Update current task countdown display"""
        # Check if task was cancelled - ignore timer events if so
        if self._task_cancelled:
            return
        
        if self.current_countdown_value > 0:
            self.current_countdown_value -= 1
            if self.current_circular_countdown:
                # Calculate progress (0.0 = empty, 1.0 = full)
                progress = (self.current_countdown_value / self.current_countdown_max) if self.current_countdown_max > 0 else 0
                # Update both the value and progress for smooth animation
                self.current_circular_countdown._value = self.current_countdown_value
                self.current_circular_countdown._display_value = float(self.current_countdown_value)
                self.current_circular_countdown.set_progress(progress * 100.0)
        else:
            self.current_countdown_timer.stop()
            if self.current_circular_countdown:
                self.current_circular_countdown.set_progress(0.0)
            # Only emit countdown_zero_signal if task was not cancelled
            if not self._task_cancelled:
                self.countdown_zero_signal.emit()
    
    def update_next_countdown(self):
        """Update next task countdown display"""
        if self.next_countdown_value > 0:
            self.next_countdown_value -= 1
            if self.next_circular_countdown:
                # Calculate progress (0.0 = empty, 1.0 = full)
                progress = (self.next_countdown_value / self.next_countdown_max) if self.next_countdown_max > 0 else 0
                # Update both the value and progress for smooth animation
                self.next_circular_countdown._value = self.next_countdown_value
                self.next_circular_countdown._display_value = float(self.next_countdown_value)
                self.next_circular_countdown.set_progress(progress * 100.0)
        else:
            self.next_countdown_timer.stop()
            if self.next_circular_countdown:
                self.next_circular_countdown.set_progress(0.0)
    
    def start_current_countdown(self, seconds):
        """Start countdown for current task"""
        # Reset cancellation flag and button mode for new countdown
        self._task_cancelled = False
        self._reset_cancel_button_to_normal()
        
        self.current_countdown_value = seconds
        self.current_countdown_max = seconds
        if self.current_circular_countdown:
            self.current_circular_countdown.set_value(seconds, seconds)
            self.current_circular_countdown.set_progress(0.0)
        self.current_countdown_timer.start()
    
    def start_next_countdown(self, seconds):
        """Start countdown for next task"""
        self.next_countdown_value = seconds
        self.next_countdown_max = seconds
        if self.next_circular_countdown:
            self.next_circular_countdown.set_value(seconds, seconds)
            self.next_circular_countdown.set_progress(0.0)
        self.next_countdown_timer.start()
    
    def handle_human_task(self):
        """Handle task when performer is human (no countdown needed)"""
        # Reset cancellation flag and button mode - human tasks don't have countdown to cancel
        self._task_cancelled = False
        self._reset_cancel_button_to_normal()
        
        self.current_countdown_timer.stop()
        self.current_countdown_value = 0
        self.current_countdown_max = 1
        self.countdown_zero_signal.emit()
    
    # BUTTON HANDLERS
    def task_done_clicked(self):
        """Handle task done button click"""
        if self.current_task_container:
            self.start_glow_effect(self.current_task_container, "green")
        self.task_done_signal.emit()
    
    def task_allowed_clicked(self):
        """Handle task allowed button click"""
        if self.current_task_container:
            self.start_glow_effect(self.current_task_container, "blue")
        self.task_allowed_signal.emit()
    
    def task_not_allowed_clicked(self):
        """Handle task not allowed button click"""
        if self.current_task_container:
            self.start_glow_effect(self.current_task_container, "red")
        self.task_not_allowed_signal.emit()
    
    def task_cancel_clicked(self):
        """Handle task cancel/override button click - behavior depends on button mode"""
        if self._button_in_override_mode:
            # Button is in OVERRIDE mode - force transition to next state
            if self.current_task_container:
                self.start_glow_effect(self.current_task_container, "green")
            self.task_override_signal.emit()
        else:
            # Button is in CANCEL mode - cancel the current task
            if self.current_task_container:
                self.start_glow_effect(self.current_task_container, "red")
            
            # Mark task as cancelled before stopping timer
            self._task_cancelled = True
            
            self.current_countdown_timer.stop()
            self.current_countdown_value = 0
            if self.current_circular_countdown:
                self.current_circular_countdown.set_value(0, self.current_countdown_max if self.current_countdown_max > 0 else 1)
                self.current_circular_countdown.set_progress(0.0)
            
            self.task_cancel_signal.emit()
            
            # Switch button to OVERRIDE mode
            self._button_in_override_mode = True
            self._update_cancel_button_text()
    
    def _update_cancel_button_text(self):
        """Update cancel button text based on current mode - to be overridden by subclass"""
        # Subclasses should override this to update their specific button widget
        pass
    
    def _reset_cancel_button_to_normal(self):
        """Reset cancel button back to CANCEL mode - called on task transitions"""
        self._button_in_override_mode = False
        self._update_cancel_button_text()
    
    # GLOW EFFECTS
    def start_glow_effect(self, widget, color):
        """Start glow effect on widget"""
        if self._glow_active_widget is widget:
            return
        
        self._glow_active_widget = widget
        
        if color == "red":
            self._glow_steps = [
                (2, "rgba(255, 0, 0, 0)"), (4, "rgba(255, 0, 0, 100)"),
                (6, "rgba(255, 0, 0, 200)"), (8, "rgba(255, 0, 0, 255)"),
                (6, "rgba(255, 0, 0, 200)"), (4, "rgba(255, 0, 0, 100)"),
                (2, "rgba(255, 0, 0, 0)")
            ]
        elif color == "blue":
            self._glow_steps = [
                (2, "rgba(85, 170, 255, 0)"), (4, "rgba(85, 170, 255, 100)"),
                (6, "rgba(85, 170, 255, 200)"), (8, "rgba(85, 170, 255, 255)"),
                (6, "rgba(85, 170, 255, 200)"), (4, "rgba(85, 170, 255, 100)"),
                (2, "rgba(85, 170, 255, 0)")
            ]
        elif color == "green":
            self._glow_steps = [
                (2, "rgba(85, 222, 113, 0)"), (4, "rgba(85, 222, 113, 100)"),
                (6, "rgba(85, 222, 113, 200)"), (8, "rgba(85, 222, 113, 255)"),
                (6, "rgba(85, 222, 113, 200)"), (4, "rgba(85, 222, 113, 100)"),
                (2, "rgba(85, 222, 113, 0)")
            ]
        
        self._glow_index = 0
        if self._glow_timer is None:
            self._glow_timer = QtCore.QTimer(self.main_window)
            self._glow_timer.timeout.connect(lambda: self._glow_tick(widget))
        self._glow_timer.start(30)
    
    def _glow_tick(self, widget):
        """Handle glow effect tick"""
        width, color = self._glow_steps[self._glow_index]
        widget.setStyleSheet(f"""
            #{widget.objectName()} {{
                border: {width}px solid {color};
                border-radius: 8px;
                background-color: rgba(19, 20, 23, 255);
            }}
        """)
        self._glow_index += 1
        if self._glow_index >= len(self._glow_steps):
            self._glow_timer.stop()
            self._glow_active_widget = None
    
    def reset_radio_button(self, button):
        """Reset radio button state"""
        button.setChecked(False)
    
    def display_interaction_panel_message(self, message: str, tars_input: str = ""):
        """Display message in interaction panel"""
        if self.interaction_panel_text:
            self.interaction_panel_text.setText(message)
        if self.interaction_panel_tars_input:
            if tars_input:
                self.interaction_panel_tars_input.show()
                self.interaction_panel_tars_input.setText(tars_input)
            else:
                self.interaction_panel_tars_input.hide()
