"""
Flight Page
Handles the flight page functionality
"""

from pages.base_page import BasePage
from PySide6 import QtCore
from typing import TYPE_CHECKING

# Import for type hints only (prevents circular imports)
if TYPE_CHECKING:
    from modules.ui_main import Ui_MainWindow
    from main import MainWindow

class FlightPage(BasePage):
    """
    Flight page - displays flight-related information and controls
    """
    
    def __init__(self, widgets: 'Ui_MainWindow', main_window: 'MainWindow'):
        super().__init__(widgets, main_window)
        self.initialize_page()
    
    def initialize_page(self):
        """
        Initialize the flight page
        """
        if self.is_initialized:
            return
        
        # Initialize flight page elements here
        # Example: Connect signals, set up UI elements, etc.
        
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
        # Cleanup or save state when leaving the page
        pass
    
    def show_page(self):
        """
        Show the flight page
        """
        self.on_page_show()
    
    def hide_page(self):
        """
        Hide the flight page
        """
        self.on_page_hide()
