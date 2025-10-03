"""
Home Page
Main landing page for the TARS GUI application
"""

from pages.base_page import BasePage
from PySide6 import QtCore
from PySide6.QtWidgets import QGraphicsOpacityEffect

class HomePage(BasePage):
    """
    Home page implementation
    Contains the main dashboard and status information
    """
    
    # Signals for communicating with MainWindow
    task_done_signal = QtCore.Signal()
    task_cancel_signal = QtCore.Signal()
    
    def __init__(self, widgets, main_window):
        """
        Initialize the home page
        
        Args:
            widgets: UI widgets object
            main_window: Main window instance
        """
        super().__init__(widgets, main_window)
        self.page_widget = widgets.home
        
        # Initialize countdown timers
        self.current_countdown_timer = QtCore.QTimer(self.main_window)
        self.current_countdown_timer.setInterval(1000)
        self.current_countdown_timer.timeout.connect(self.update_current_countdown)
        self.current_countdown_value = 0
        
        self.next_countdown_timer = QtCore.QTimer(self.main_window)
        self.next_countdown_timer.setInterval(1000)
        self.next_countdown_timer.timeout.connect(self.update_next_countdown)
        self.next_countdown_value = 0
        
        # Initialize glow effect timer
        self._glow_timer = None
        self._glow_steps = []
        self._glow_index = 0
        
        self.setup_page()
    
    def setup_page(self):
        """
        Setup home page specific functionality
        """
        # Connect task buttons to home page handlers
        self.widgets.task_done_button.clicked.connect(self.task_done_clicked)
        self.widgets.int_panel_right_button.clicked.connect(self.task_done_clicked)
        self.widgets.cancel_task_button_2.clicked.connect(self.task_cancel_clicked)
        self.widgets.int_panel_left_button.clicked.connect(self.task_cancel_clicked)
        
        # Set object name for current task container
        self.widgets.current_task_container_3.setObjectName("currentTaskContainer")
        
        print("Home page setup complete")
    
    def show_page(self):
        """
        Show the home page
        """
        self.widgets.stackedWidget.setCurrentWidget(self.page_widget)
        print("Showing home page")
    
    def hide_page(self):
        """
        Hide the home page
        """
        # Home page doesn't need specific hiding logic
        # as it's handled by the stacked widget
        print("Hiding home page")
    
    def refresh_data(self):
        """
        Refresh home page data
        """
        # Add any data refresh logic for home page here
        print("Refreshing home page data")
    
    # COUNTDOWN TIMER METHODS
    # ///////////////////////////////////////////////////////////////
    def update_current_countdown(self):
        """Update current task countdown display"""
        if self.current_countdown_value > 0:
            self.widgets.c_t_s_value_2.setText(str(self.current_countdown_value))
            self.current_countdown_value -= 1
        else:
            self.widgets.c_t_s_value_2.setText("0")
            self.current_countdown_timer.stop()

    def update_next_countdown(self):
        """Update next task countdown display"""
        if self.next_countdown_value > 0:
            self.widgets.n_t_s_value_2.setText(str(self.next_countdown_value))
            self.next_countdown_value -= 1
        else:
            self.widgets.n_t_s_value_2.setText("0")
            self.next_countdown_timer.stop()
    
    def start_current_countdown(self, seconds):
        """Start countdown for current task"""
        self.current_countdown_value = seconds
        self.current_countdown_timer.start()
    
    def start_next_countdown(self, seconds):
        """Start countdown for next task"""
        self.next_countdown_value = seconds
        self.next_countdown_timer.start()
    
    # LABEL UTILITY METHODS
    # ///////////////////////////////////////////////////////////////
    def hide_label(self, label):
        """Hide a label with opacity effect"""
        opacity_effect = label.graphicsEffect()
        if not isinstance(opacity_effect, QGraphicsOpacityEffect):
            opacity_effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(opacity_effect)
        opacity_effect.setOpacity(0.0)
    
    def show_label(self, label):
        """Show a label with opacity effect"""
        opacity_effect = label.graphicsEffect()
        if not isinstance(opacity_effect, QGraphicsOpacityEffect):
            opacity_effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(opacity_effect)
        opacity_effect.setOpacity(0.99)
        label.show()
    
    # TASK BUTTON HANDLERS
    # ///////////////////////////////////////////////////////////////
    def task_done_clicked(self):
        """Handle task done button click"""
        btn = self.sender()
        if btn:  # Safety check
            btn.setStyleSheet(f"""
                        border: 2px solid #3399ff;
                        border-radius: 5px;
                        background-color: rgba(0, 48, 20, 255);
                        font: 600 16pt "JetBrains Mono";
                    """)
        self.start_glow_effect(self.widgets.current_task_container_3, "green")
        
        # Emit signal to notify MainWindow
        self.task_done_signal.emit()
        
    def task_cancel_clicked(self):
        """Handle task cancel button click"""
        btn = self.sender()
        if btn:  # Safety check
            btn.setStyleSheet(f"""
                        border: 2px solid #3399ff;
                        border-radius: 5px;
                        background-color: rgba(108, 04, 04, 255);
                        font: 600 16pt "JetBrains Mono";
                    """)
        self.start_glow_effect(self.widgets.current_task_container_3, "red")
        
        # Emit signal to notify MainWindow
        self.task_cancel_signal.emit()
    
    # VISUAL EFFECTS
    # ///////////////////////////////////////////////////////////////
    def start_glow_effect(self, widget, color):
        """Start glow effect on widget"""
        # Flicker parameters: border width and color alpha
        if color == "red":
            self._glow_steps = [
                (2, "#ff3333"), (4, "#ff3333"), (6, "#ff3333"), (8, "#ff3333"),
                (6, "#ff3333"), (4, "#ff3333"), (2, "#ff3333"), (2, "#ff3333"), 
                (4, "#ff3333"), (6, "#ff3333"), (8, "#ff3333"),
                (6, "#ff3333"), (4, "#ff3333"), (2, "#ff3333")
            ]       
        elif color == "blue":
            self._glow_steps = [
                (2, "#3399ff"), (4, "#3399ff"), (6, "#3399ff"), (8, "#3399ff"),
                (6, "#3399ff"), (4, "#3399ff"), (2, "#3399ff"), (2, "#3399ff"), 
                (4, "#3399ff"), (6, "#3399ff"), (8, "#3399ff"),
                (6, "#3399ff"), (4, "#3399ff"), (2, "#3399ff")
            ]
        elif color == "green":
            self._glow_steps = [
                (2, "#00ff00"), (4, "#00ff00"), (6, "#00ff00"), (8, "#00ff00"),
                (6, "#00ff00"), (4, "#00ff00"), (2, "#00ff00"), (2, "#00ff00"), 
                (4, "#00ff00"), (6, "#00ff00"), (8, "#00ff00"),
                (6, "#00ff00"), (4, "#00ff00"), (2, "#00ff00")
            ]
        
        self._glow_index = 0
        if self._glow_timer is None:
            self._glow_timer = QtCore.QTimer(self.main_window)
            self._glow_timer.timeout.connect(lambda: self._glow_tick(widget))
            self._glow_timer.setSingleShot(False)
        self._glow_timer.start(30)  # Flicker speed

    def _glow_tick(self, widget):
        """Handle glow effect tick"""
        width, color = self._glow_steps[self._glow_index]
        widget.setStyleSheet(f"""
            #currentTaskContainer {{
            border: {width}px solid {color};
            border-radius: 8px;
            background-color: rgba(19, 20, 23, 255);
            }}
        """)
        self._glow_index += 1
        if self._glow_index >= len(self._glow_steps):
            # Stabilize to a steady glow after flicker
            self._glow_timer.stop()
            widget.setStyleSheet(f"""
                #currentTaskContainer {{
                border: 4px solid {color};
                border-radius: 8px;
                background-color: rgba(19, 20, 23, 255);
                }}
            """)
    
    def show_button(self, button, color):
        """Show button with specified color styling"""
        if color == "green":
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid #3399ff;
                    border-radius: 5px;
                    background-color: rgba(0, 168, 120, 255);
                    font: 600 16pt "JetBrains Mono";
                }
            """)
        elif color == "red":
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid #3399ff;
                    border-radius: 5px;
                    background-color: rgba(168, 0, 0, 255);
                    font: 600 16pt "JetBrains Mono";
                }
            """)
        # Actually show the button
        button.show()