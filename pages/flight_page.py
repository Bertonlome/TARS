"""
Flight Page
Handles the flight page functionality
"""

from pages.task_page_base import TaskPageBase
from PySide6 import QtCore
from typing import TYPE_CHECKING

# Import for type hints only (prevents circular imports)
if TYPE_CHECKING:
    from modules.ui_main import Ui_MainWindow
    from main import MainWindow

class FlightPage(TaskPageBase):
    """
    Flight page - simplified task execution view during flight
    Uses the same countdown/interaction logic as HomePage but with _flight widgets
    """
    
    def __init__(self, widgets: 'Ui_MainWindow', main_window: 'MainWindow'):
        super().__init__(widgets, main_window)
        
        # Set widget references for base class to use (all have _flight suffix)
        self.current_task_container = widgets.current_task_container_flight
        self.interaction_panel_text = widgets.interaction_panel_text_flight
        self.interaction_panel_tars_input = widgets.interaction_panel_tars_input_flight
        self.int_panel_right_button = widgets.int_panel_right_button_flight
        self.int_panel_left_button = widgets.int_panel_left_button_flight
        # Flight page doesn't have these widgets
        self.check_radio_button = None
        self.cancel_task_button = None
        
        # Store references to countdown labels for setup
        self.current_value_label = widgets.c_t_s_value_flight
        self.current_unit_label = widgets.c_t_s_unit_flight
        self.next_value_label = widgets.n_t_s_value_flight
        self.next_unit_label = widgets.n_t_s_unit_flight
        
        # Initialize the page
        self.initialize_page()
    
    def initialize_page(self):
        """
        Initialize the flight page
        """
        if self.is_initialized:
            return
        
        # Set object name for styling
        if self.current_task_container:
            self.current_task_container.setObjectName("currentTaskContainer")
        
        # Setup countdown widgets - note: c_t_s_container_3 is the layout for current countdown
        self.setup_countdown_widgets(
            current_container=self.widgets.c_t_s_container_3,
            next_container=self.widgets.n_t_s_container_flight,
            current_value_label=self.current_value_label,
            current_unit_label=self.current_unit_label,
            next_value_label=self.next_value_label,
            next_unit_label=self.next_unit_label
        )
        
        # Connect task buttons (right button = done, left button = cancel)
        self.connect_task_buttons()
        
        # No radio button styling needed since flight page doesn't have one
        
        self.is_initialized = True
    
    def on_page_show(self):
        """
        Called when the flight page is shown
        """
        # Update flight page content when shown
        pass
    
    def on_page_hide(self):
        """
        Called when the flight page is hidden
        """
        # Stop timers when leaving the page
        self.current_countdown_timer.stop()
        self.next_countdown_timer.stop()
    
    def show_page(self):
        """
        Show the flight page
        """
        self.widgets.stackedWidget.setCurrentWidget(self.widgets.flight)
        self.on_page_show()
    
    def hide_page(self):
        """
        Hide the flight page
        """
        self.on_page_hide()
    
    def displayAlert(self, text: str, color: str = "red"):
        """Display alert with specified text and color
        
        Args:
            text: Alert text to display
            color: Alert border color (red, orange, yellow, etc.)
        """
        self.widgets.alert_container_flight.setStyleSheet(f"""
            QWidget#alert_container_flight {{
                border: 2px solid {color};
                border-radius: 5px;
                background-color: rgba(33, 37, 43, 255);
            }}
        """)
        self.widgets.alert_label_flight.setText(text)
        if self.widgets.alert_container_flight:
            self.start_glow_effect(self.widgets.alert_container_flight, color)
    
    def clearAlert(self):
        """Clear the alert display"""
        self.widgets.alert_container_flight.setStyleSheet("""
            QWidget#alert_container_flight {
                border: 2px solid rgba(52, 59, 72, 255);
                border-radius: 5px;
                background-color: rgba(33, 37, 43, 255);
            }
        """)
        self.widgets.alert_label_flight.setText("")
    
    def _update_cancel_button_text(self):
        """Update cancel button text based on current mode (override from TaskPageBase)"""
        if self._button_in_override_mode:
            self.widgets.int_panel_left_button_flight.setText("OVERRIDE")
        else:
            self.widgets.int_panel_left_button_flight.setText("CANCEL")
    
    def show_button(self, button, color):
        """Show button with specified color styling"""
        button.show()
    
    def hide_label(self, label):
        """Hide a label with opacity effect"""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        opacity_effect = label.graphicsEffect()
        if not isinstance(opacity_effect, QGraphicsOpacityEffect):
            opacity_effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(opacity_effect)
        opacity_effect.setOpacity(0.0)
    
    def show_label(self, label):
        """Show a label with opacity effect"""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        opacity_effect = label.graphicsEffect()
        if not isinstance(opacity_effect, QGraphicsOpacityEffect):
            opacity_effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(opacity_effect)
        opacity_effect.setOpacity(0.99)
        label.show()
