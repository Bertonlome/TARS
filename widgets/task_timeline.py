"""
Task Timeline Widget
Displays task allocation timeline for current procedure with TARS and Pilot timelines
"""

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QPixmap
from PySide6.QtWidgets import QWidget
import csv
from pathlib import Path


class TaskTimelineWidget(QWidget):
    """
    Widget to display task allocation timeline
    Shows two horizontal timelines: TARS (top) and PILOT (bottom)
    Each task is represented as a box with the task name
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Widget properties
        self.setMinimumHeight(120)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Fixed
        )
        
        # Task data
        self._current_procedure = None
        self._current_task_key = None
        self._tasks = []  # List of task dictionaries
        
        # Visual properties
        self._tars_color = QColor("#071c35")  # Blue for TARS
        self._pilot_color = QColor("#071c35")  # Green for PILOT
        self._current_task_color = QColor("#3399ff")  # Blue for current task
        self._background_color = QColor("#21252b")
        self._text_color = QColor("#dddddd")
        self._box_spacing = 10
        self._box_height = 35
        self._timeline_spacing = 15  # Space between TARS and PILOT timelines
        
        # Caching for performance optimization
        self._cached_pixmap = None
        self._cache_valid = False
        self._last_size = None
        
    def load_tasks_from_agent(self, agent):
        """Load tasks directly from agent's state data (preferred method)
        
        Args:
            agent: TarsAgent instance with loaded states
        """
        all_tasks = []
        
        try:
            # Extract task data from agent's states dictionary
            for state_key, state in agent.states.items():
                # Skip special states (IDLE, FINISHED)
                if state.procedure in ['IDLE', 'FINISHED']:
                    continue
                
                all_tasks.append({
                    'procedure': state.procedure,
                    'task_object': state.task_object,
                    'value': state.value,
                    'autonomy_role': state.autonomy_role or '',  # Handle None values
                    'key': state_key  # Use the same key as agent
                })
            
            print(f"TaskTimeline: Loaded {len(all_tasks)} tasks from agent states")
        except Exception as e:
            print(f"Error loading tasks from agent: {e}")
        
        self._tasks = all_tasks
        self._cache_valid = False  # Invalidate cache since data changed
        self.update()
        
    def set_current_procedure(self, procedure_name):
        """Set the current procedure to display"""
        if self._current_procedure != procedure_name:
            self._current_procedure = procedure_name
            self._cache_valid = False
            self.update()
    
    def set_current_task(self, task_key):
        """Set the current task (highlighted)
        
        Args:
            task_key: Tuple of (procedure, task_object, value)
        """
        if self._current_task_key != task_key:
            self._current_task_key = task_key
            self._cache_valid = False
            self.update()
    
    def get_procedure_tasks(self):
        """Get all tasks for current procedure in chronological order"""
        if not self._current_procedure:
            return []
        
        procedure_tasks = []
        
        for task in self._tasks:
            if task['procedure'] == self._current_procedure:
                procedure_tasks.append(task)
        
        return procedure_tasks
    
    def paintEvent(self, event):
        """Custom paint event to draw the timeline"""
        painter = QPainter(self)
        
        # Check if we need to redraw or can use cached version
        current_size = self.size()
        if (self._cache_valid and 
            self._cached_pixmap and 
            self._last_size == current_size):
            # Use cached pixmap
            painter.drawPixmap(0, 0, self._cached_pixmap)
            return
        
        # Create new pixmap for caching
        self._cached_pixmap = QtGui.QPixmap(current_size)
        self._cached_pixmap.fill(Qt.transparent)
        
        # Draw on the cached pixmap
        cache_painter = QPainter(self._cached_pixmap)
        cache_painter.setRenderHint(QPainter.Antialiasing)
        
        # Fill background
        cache_painter.fillRect(self._cached_pixmap.rect(), self._background_color)
        
        if not self._current_procedure:
            # Draw placeholder text
            cache_painter.setPen(self._text_color)
            cache_painter.drawText(self._cached_pixmap.rect(), Qt.AlignCenter, "No procedure selected")
        else:
            # Get tasks for current procedure
            procedure_tasks = self.get_procedure_tasks()
            
            if not procedure_tasks:
                cache_painter.setPen(self._text_color)
                cache_painter.drawText(self._cached_pixmap.rect(), Qt.AlignCenter, f"No tasks in {self._current_procedure}")
            else:
                # Calculate layout
                width = self._cached_pixmap.width()
                height = self._cached_pixmap.height()
                
                # Timeline positions
                tars_y = 10
                pilot_y = tars_y + self._box_height + self._timeline_spacing
                
                # Draw labels
                font = QFont("JetBrains Mono", 10, QFont.Bold)
                cache_painter.setFont(font)
                cache_painter.setPen(self._text_color)
                cache_painter.drawText(5, tars_y + 20, "TARS:")
                cache_painter.setPen(self._text_color)
                cache_painter.drawText(5, pilot_y + 20, "PILOT:")
                
                # Starting x position for boxes (after label)
                start_x = 70
                available_width = width - start_x - 10
                
                # Draw chronological timeline
                self._draw_chronological_timeline(cache_painter, procedure_tasks, start_x, tars_y, pilot_y, available_width)
        
        cache_painter.end()
        
        # Draw the cached pixmap
        painter.drawPixmap(0, 0, self._cached_pixmap)
        
        # Mark cache as valid
        self._cache_valid = True
        self._last_size = current_size
    
    def resizeEvent(self, event):
        """Handle resize events by invalidating cache"""
        super().resizeEvent(event)
        self._cache_valid = False
    
    def _draw_chronological_timeline(self, painter, tasks, start_x, tars_y, pilot_y, available_width):
        """Draw timeline with tasks in chronological order on appropriate performer lines"""
        if not tasks:
            return
        
        # Calculate box width based on total number of tasks
        num_tasks = len(tasks)
        total_spacing = self._box_spacing * (num_tasks - 1)
        box_width = (available_width - total_spacing) / num_tasks
        
        # Limit box width for readability
        box_width = min(box_width, 150)
        
        # Draw each task in its chronological position
        for i, task in enumerate(tasks):
            # Calculate x position for this task (chronological order)
            x = start_x + i * (box_width + self._box_spacing)
            
            # Determine which timeline (TARS or PILOT)
            is_tars = task['autonomy_role'].lower() == 'performer'
            y = tars_y if is_tars else pilot_y
            color = self._tars_color if is_tars else self._pilot_color
            
            # Check if this is the current task
            is_current = (task['key'] == self._current_task_key)
            
            # Choose color and border width
            if is_current:
                box_color = self._current_task_color
                border_width = 3
            else:
                box_color = color
                border_width = 2
            
            # Draw the task box
            self._draw_task_box(painter, task, x, y, box_width, box_color, border_width)
    
    def _draw_task_box(self, painter, task, x, y, box_width, color, border_width):
        """Draw a single task box"""
        # Draw box
        rect = QRect(int(x), int(y), int(box_width), self._box_height)
        
        # Fill box with semi-transparent background
        painter.setPen(Qt.NoPen)
        fill_color = QColor(color)
        fill_color.setAlpha(50)
        painter.setBrush(fill_color)
        painter.drawRoundedRect(rect, 5, 5)
        
        # Draw border
        pen = QPen(color, border_width)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 5, 5)
        
        # Draw text
        painter.setPen(self._text_color)
        font = QFont("JetBrains Mono", 8)
        is_current = (task['key'] == self._current_task_key)
        if is_current:
            font.setBold(True)
        painter.setFont(font)
        
        # Truncate text if too long
        text = task['task_object']
        fm = painter.fontMetrics()
        elided_text = fm.elidedText(text, Qt.ElideRight, int(box_width - 10))
        
        painter.drawText(rect, Qt.AlignCenter, elided_text)