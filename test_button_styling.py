#!/usr/bin/env python3
"""
Test script to demonstrate button styling states
"""

import sys
import os

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget, QLabel
from PySide6.QtCore import Qt, QTimer

class ButtonStyleTest(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Button Styling Test")
        self.setFixedSize(400, 300)
        
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Button Styling Test")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font: 600 14pt 'JetBrains Mono'; margin: 20px;")
        layout.addWidget(title)
        
        # Test button
        self.test_button = QPushButton("Validate Briefing")
        self.test_button.setFixedHeight(50)
        layout.addWidget(self.test_button)
        
        # State label
        self.state_label = QLabel("State: Disabled")
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setStyleSheet("font: 12pt 'JetBrains Mono'; margin: 10px;")
        layout.addWidget(self.state_label)
        
        self.setLayout(layout)
        
        # Initialize in disabled state
        self.current_state = 0  # 0=disabled, 1=enabled, 2=reset
        self.set_disabled_state()
        
        # Setup timer to cycle through states
        self.timer = QTimer()
        self.timer.timeout.connect(self.cycle_state)
        self.timer.start(3000)  # Change state every 3 seconds
    
    def set_disabled_state(self):
        """Set button to disabled state"""
        self.test_button.setText("Cannot Validate")
        self.test_button.setEnabled(False)
        
        # Apply disabled styling with !important
        self.test_button.setStyleSheet("""
            QPushButton {
                border: 2px solid gray !important;
                border-radius: 5px !important;
                background-color: #808080 !important;
                font: 600 16pt "JetBrains Mono" !important;
                color: #404040 !important;
            }
            QPushButton:disabled {
                border: 2px solid gray !important;
                background-color: #808080 !important;
                color: #404040 !important;
            }
        """)
        self.state_label.setText("State: Disabled (Gray)")
    
    def set_enabled_state(self):
        """Set button to enabled state"""
        self.test_button.setText("Validate Briefing")
        self.test_button.setEnabled(True)
        
        # Apply enabled styling with !important
        self.test_button.setStyleSheet("""
            QPushButton {
                border: 2px solid rgba(0, 168, 120, 255) !important;
                border-radius: 5px !important;
                background-color: rgba(0, 168, 120, 255) !important;
                font: 600 16pt "JetBrains Mono" !important;
                color: white !important;
            }
            QPushButton:hover {
                background-color: rgba(0, 150, 108, 255) !important;
                border-color: rgba(0, 150, 108, 255) !important;
            }
            QPushButton:pressed {
                background-color: rgba(0, 134, 96, 255) !important;
                border-color: rgba(0, 134, 96, 255) !important;
            }
        """)
        self.state_label.setText("State: Enabled (Green)")
    
    def set_reset_state(self):
        """Set button to reset state"""
        self.test_button.setText("Reset Selection")
        self.test_button.setEnabled(True)
        
        # Apply reset styling with !important
        self.test_button.setStyleSheet("""
            QPushButton {
                border: 2px solid rgba(0, 134, 96, 255) !important;
                border-radius: 5px !important;
                background-color: rgba(0, 134, 96, 255) !important;
                font: 600 16pt "JetBrains Mono" !important;
                color: white !important;
            }
            QPushButton:hover {
                background-color: rgba(0, 120, 86, 255) !important;
                border-color: rgba(0, 120, 86, 255) !important;
            }
            QPushButton:pressed {
                background-color: rgba(0, 100, 72, 255) !important;
                border-color: rgba(0, 100, 72, 255) !important;
            }
        """)
        self.state_label.setText("State: Reset (Dark Green)")
    
    def cycle_state(self):
        """Cycle through button states for demonstration"""
        self.current_state = (self.current_state + 1) % 3
        
        if self.current_state == 0:
            self.set_disabled_state()
        elif self.current_state == 1:
            self.set_enabled_state()
        else:
            self.set_reset_state()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ButtonStyleTest()
    window.show()
    sys.exit(app.exec())