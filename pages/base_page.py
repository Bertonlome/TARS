"""
Base Page Class
Provides common functionality for all page modules
"""

from PySide6 import QtWidgets, QtCore, QtGui
from abc import abstractmethod
from typing import TYPE_CHECKING

# Import for type hints only (prevents circular imports)
if TYPE_CHECKING:
    from modules.ui_main import Ui_MainWindow
    from main import MainWindow

class BasePage(QtCore.QObject):
    """
    Base class for all page modules.
    Provides common interface and functionality.
    """
    
    def __init__(self, widgets: 'Ui_MainWindow', main_window: 'MainWindow'):
        super().__init__()
        self.widgets: 'Ui_MainWindow' = widgets
        self.main_window: 'MainWindow' = main_window
        self.is_initialized = False
        
    @abstractmethod
    def initialize_page(self):
        """
        Initialize the page - set up UI elements, connect signals, etc.
        This method should be implemented by each page class.
        """
        pass
    
    @abstractmethod
    def on_page_show(self):
        """
        Called when the page is shown.
        Use this for actions that should happen every time the page becomes visible.
        """
        pass
    
    @abstractmethod
    def on_page_hide(self):
        """
        Called when the page is hidden.
        Use this for cleanup actions when leaving the page.
        """
        pass
    
    def setup_page(self):
        """
        Public method to set up the page.
        Only initializes once, then calls on_page_show.
        """
        if not self.is_initialized:
            self.initialize_page()
            self.is_initialized = True
        self.on_page_show()
    
    def show_page(self):
        """
        Show this page in the stacked widget
        """
        # Get the page widget name from class name
        page_name = self.__class__.__name__.lower().replace('page', '')
        
        # Get the widget
        page_widget = getattr(self.widgets, page_name, None)
        if page_widget:
            self.widgets.stackedWidget.setCurrentWidget(page_widget)
            self.setup_page()
        else:
            print(f"Warning: Could not find widget '{page_name}' for page {self.__class__.__name__}")
    
    def hide_page(self):
        """
        Called when hiding this page
        """
        self.on_page_hide()