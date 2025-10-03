"""
Page Manager
Manages all page modules and navigation
"""

from pages.briefing_page import BriefingPage
from pages.home_page import HomePage
# Import other pages as you create them
# from pages.widgets_page import WidgetsPage

class PageManager:
    """
    Manages all page modules and handles navigation
    """
    
    def __init__(self, widgets, main_window):
        self.widgets = widgets
        self.main_window = main_window
        self.pages = {}
        self.current_page = None
        
        # Initialize all pages
        self.initialize_pages()
    
    def initialize_pages(self):
        """
        Initialize all page modules
        """
        # Initialize home page (main landing page)
        self.pages['home'] = HomePage(self.widgets, self.main_window)
        
        # Initialize briefing page
        self.pages['briefing'] = BriefingPage(self.widgets, self.main_window)
        
        # Add other pages as you create them
        # self.pages['widgets'] = WidgetsPage(self.widgets, self.main_window)
        
        print(f"Initialized {len(self.pages)} pages")
        
        # Set home as the default page
        self.navigate_to_page('home')
    
    def navigate_to_page(self, page_name):
        """
        Navigate to a specific page
        
        Args:
            page_name (str): Name of the page to navigate to
        """
        # Hide current page if exists
        if self.current_page and self.current_page in self.pages:
            self.pages[self.current_page].hide_page()
        
        # Show new page if it exists
        if page_name in self.pages:
            self.pages[page_name].show_page()
            self.current_page = page_name
            print(f"Navigated to {page_name} page")
        else:
            print(f"Warning: Page '{page_name}' not found")
    
    def get_page(self, page_name):
        """
        Get a specific page instance
        
        Args:
            page_name (str): Name of the page
            
        Returns:
            BasePage: The page instance or None if not found
        """
        return self.pages.get(page_name, None)
    
    def register_page(self, page_name, page_instance):
        """
        Register a new page
        
        Args:
            page_name (str): Name of the page
            page_instance (BasePage): Instance of the page
        """
        self.pages[page_name] = page_instance
        print(f"Registered page: {page_name}")
    
    def get_all_pages(self):
        """
        Get all registered pages
        
        Returns:
            dict: Dictionary of all pages
        """
        return self.pages.copy()