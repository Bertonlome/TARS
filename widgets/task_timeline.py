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
    
    # Signal emitted when a task box is clicked
    # Emits the task key: (procedure, task_object, value)
    task_clicked = QtCore.Signal(tuple)
    
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
        self._current_task_color = QColor("#071c35")  # Blue for current task
        self._background_color = QColor("#21252b")
        self._text_color = QColor("#dddddd")
        self._box_spacing = 10
        self._box_height = 35
        self._timeline_spacing = 15  # Space between TARS and PILOT timelines
        
        # Animation properties
        self._line_color = QColor("#3399ff")  # Blue for progress line
        self._line_inactive_color = QColor("#44475a")  # Gray for inactive line
        self._animation_progress = 0.0  # 0.0 to 1.0, overall progress through timeline
        self._current_task_progress = 0.0  # 0.0 to 1.0, progress within current task
        self._current_task_index = 0  # Index of current task in procedure
        self._target_task_progress = 0.0  # Target progress for smooth animation
        self._target_connection_progress = 0.0  # Target progress for connection animation
        self._current_connection_progress = 0.0  # Current connection progress
        self._active_connection_index = 0  # Which connection is currently animating
        
        # Smooth animation timer (60fps)
        self._animation_timer = QtCore.QTimer()
        self._animation_timer.timeout.connect(self._update_smooth_animation)
        self._animation_timer.setInterval(16)  # ~60fps (1000ms / 60 = 16.67ms)
        
        # Caching for performance optimization
        self._cached_pixmap = None
        self._cache_valid = False
        self._last_size = None
        
        # Task item references for violation marking
        self._task_items = {}
        
        # Task rectangles for click detection
        # Maps task_key -> QRect for hit testing
        self._task_rects = {}
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        self._hovered_task_key = None
        
        # Set cursor to indicate clickability
        self.setCursor(Qt.PointingHandCursor)
        
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
                    'delay_before_action': getattr(state, 'delay_before_action', None),  # Add delay info
                    'key': state_key  # Use the same key as agent
                })
            
            #print(f"TaskTimeline: Loaded {len(all_tasks)} tasks from agent states")
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
            # Update current task index for animations
            self._update_current_task_index()
            self._cache_valid = False
            self.update()
    
    def _update_current_task_index(self):
        """Update the current task index for animation purposes"""
        if not self._current_task_key:
            self._current_task_index = 0
            return
            
        procedure_tasks = self.get_procedure_tasks()
        for i, task in enumerate(procedure_tasks):
            if task['key'] == self._current_task_key:
                self._current_task_index = i
                return
        self._current_task_index = 0
    
    def set_timeline_progress(self, task_index, task_progress=0.0):
        """DEPRECATED: Use set_task_border_progress and set_connection_progress instead
        
        Args:
            task_index: Index of current task (0-based)
            task_progress: Progress within current task (0.0 to 1.0)
        """
        # Keep for compatibility but redirect to new methods
        self._current_task_index = task_index
        self.set_task_border_progress(task_progress)
    
    def set_next_task_countdown(self, countdown_value, max_countdown):
        """Update animation based on next task countdown
        
        Args:
            countdown_value: Current countdown value (decreasing)
            max_countdown: Maximum countdown value
        """
        if max_countdown > 0:
            # Convert countdown to progress (0.0 when countdown=max, 1.0 when countdown=0)
            progress = 1.0 - (countdown_value / max_countdown)
            self.set_timeline_progress(self._current_task_index, progress)
    
    def reset_animation(self):
        """Reset all animation progress"""
        self._animation_progress = 0.0
        self._current_task_progress = 0.0
        self._target_task_progress = 0.0
        self._current_connection_progress = 0.0
        self._target_connection_progress = 0.0
        self._current_task_index = 0
        self._active_connection_index = 0
        self._animation_timer.stop()
        self._cache_valid = False
        self.update()
    
    def _update_smooth_animation(self):
        """Update smooth animation interpolation (60fps)"""
        animation_speed = 0.15  # Increased speed for smoother animation (0.15 = smoother, 1.0 = instant)
        
        # Smooth interpolation for task progress
        if abs(self._current_task_progress - self._target_task_progress) > 0.001:
            self._current_task_progress += (self._target_task_progress - self._current_task_progress) * animation_speed
            self._cache_valid = False
        else:
            # Snap to target when very close
            self._current_task_progress = self._target_task_progress
        
        # Smooth interpolation for connection progress
        if abs(self._current_connection_progress - self._target_connection_progress) > 0.001:
            self._current_connection_progress += (self._target_connection_progress - self._current_connection_progress) * animation_speed
            self._cache_valid = False
        else:
            # Snap to target when very close
            self._current_connection_progress = self._target_connection_progress
        
        # Update display if animation is active
        if not self._cache_valid:
            self.update()
        
        # Stop timer if animations are complete
        if (abs(self._current_task_progress - self._target_task_progress) <= 0.001 and
            abs(self._current_connection_progress - self._target_connection_progress) <= 0.001):
            self._animation_timer.stop()
    
    def set_task_border_progress(self, progress):
        """Set the progress for current task border animation (0.0 to 1.0)
        This should be called during delay_before_action countdown
        """
        self._target_task_progress = max(0.0, min(1.0, progress))
        if not self._animation_timer.isActive():
            self._animation_timer.start()
    
    def set_connection_progress(self, progress):
        """Set the progress for connection line animation (0.0 to 1.0)
        This should be called when transitioning between tasks
        """
        self._target_connection_progress = max(0.0, min(1.0, progress))
        if not self._animation_timer.isActive():
            self._animation_timer.start()
    
    def complete_current_task(self):
        """Mark current task as complete and prepare for next task transition"""
        self._target_task_progress = 1.0
        # Start animating the connection FROM current task TO next task
        self._active_connection_index = self._current_task_index
        self._target_connection_progress = 0.0  # Reset for new connection animation
        self._current_connection_progress = 0.0  # Reset current progress
        if not self._animation_timer.isActive():
            self._animation_timer.start()
    
    def start_next_task_transition(self):
        """Start the connection animation to the next task"""
        # This should be called when transitioning between tasks
        self._active_connection_index = self._current_task_index
        self._target_connection_progress = 0.0  # Start connection animation
        self._current_connection_progress = 0.0  # Reset current progress
        if not self._animation_timer.isActive():
            self._animation_timer.start()
    
    def advance_to_next_task(self):
        """Advance to the next task (called when task index changes)"""
        # The previous connection should already be complete from the animation
        # Don't force it to 1.0 here as it causes the flash
        
        # Reset task progress for new task
        self._current_task_progress = 0.0
        self._target_task_progress = 0.0
        
        # Update active connection to the NEXT one (from current task to next task)
        self._active_connection_index = self._current_task_index
        
        # Reset connection progress for the NEW connection (should start at 0)
        self._current_connection_progress = 0.0
        self._target_connection_progress = 0.0
        
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
                
                # Draw connection lines and animations
                self._draw_connection_lines(cache_painter, procedure_tasks, start_x, tars_y, pilot_y, available_width)
        
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
    
    def mousePressEvent(self, event):
        """Handle mouse press events to detect task clicks"""
        if event.button() == Qt.LeftButton:
            # Check if click is on any task box
            pos = event.pos()
            for task_key, rect in self._task_rects.items():
                if rect.contains(pos):
                    # Emit signal with the task key
                    self.task_clicked.emit(task_key)
                    break
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move events for hover effects"""
        pos = event.pos()
        hovered = None
        
        # Check if hovering over any task box
        for task_key, rect in self._task_rects.items():
            if rect.contains(pos):
                hovered = task_key
                break
        
        # Update hover state if changed
        if hovered != self._hovered_task_key:
            self._hovered_task_key = hovered
            self._cache_valid = False
            self.update()
        
        super().mouseMoveEvent(event)
    
    def _draw_chronological_timeline(self, painter, tasks, start_x, tars_y, pilot_y, available_width):
        """Draw timeline with tasks in chronological order on appropriate performer lines"""
        if not tasks:
            return
        
        # Clear task rectangles for this redraw
        self._task_rects.clear()
        
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
    
    def _draw_connection_lines(self, painter, tasks, start_x, tars_y, pilot_y, available_width):
        """Draw animated connection lines between task boxes"""
        if len(tasks) < 2:
            return
        
        # Calculate box width and positions (same as in chronological timeline)
        num_tasks = len(tasks)
        total_spacing = self._box_spacing * (num_tasks - 1)
        box_width = (available_width - total_spacing) / num_tasks
        box_width = min(box_width, 150)
        
        # Timeline center points
        tars_center_y = tars_y + self._box_height // 2
        pilot_center_y = pilot_y + self._box_height // 2
        
        # Draw connections between consecutive tasks
        for i in range(len(tasks) - 1):
            current_task = tasks[i]
            next_task = tasks[i + 1]
            
            # Calculate connection points
            current_x = start_x + i * (box_width + self._box_spacing)
            next_x = start_x + (i + 1) * (box_width + self._box_spacing)
            
            # Determine which timelines the tasks are on
            current_is_tars = current_task['autonomy_role'].lower() == 'performer'
            next_is_tars = next_task['autonomy_role'].lower() == 'performer'
            
            current_y = tars_center_y if current_is_tars else pilot_center_y
            next_y = tars_center_y if next_is_tars else pilot_center_y
            
            # Connection start and end points
            start_point_x = current_x + box_width
            end_point_x = next_x
            
            # Determine if this connection should be animated
            connection_progress = self._get_connection_progress(i)
            
            # Draw the connection line with animation
            self._draw_animated_connection(painter, start_point_x, current_y, end_point_x, next_y, connection_progress)
    
    def _get_connection_progress(self, connection_index):
        """Calculate the progress for a specific connection line
        
        Args:
            connection_index: Index of the connection (0 = between task 0 and 1)
            
        Returns:
            float: Progress from 0.0 to 1.0
        """
        # Connections before the current task should be fully lit (completed)
        if connection_index < self._current_task_index:
            return 1.0
        # The connection FROM current task TO next task
        elif connection_index == self._current_task_index:
            # Only animate this connection when it's the active one
            if connection_index == self._active_connection_index:
                return self._current_connection_progress
            else:
                # If it's not the active connection, it should be unlit
                return 0.0
        else:
            # Connections after current task - not lit yet
            return 0.0
    
    def _draw_animated_connection(self, painter, start_x, start_y, end_x, end_y, progress):
        """Draw a single animated connection line
        
        Args:
            painter: QPainter instance
            start_x, start_y: Start point of the line
            end_x, end_y: End point of the line
            progress: Animation progress (0.0 to 1.0)
        """
        # Set up line style
        line_width = 3
        
        # Draw inactive (background) line first
        painter.setPen(QPen(self._line_inactive_color, line_width))
        
        # For connections between different timelines, draw a curved path
        if start_y != end_y:
            self._draw_curved_line(painter, start_x, start_y, end_x, end_y)
        else:
            # Straight horizontal line
            painter.drawLine(int(start_x), int(start_y), int(end_x), int(end_y))
        
        # Draw animated (active) portion
        if progress > 0.0:
            painter.setPen(QPen(self._line_color, line_width))
            
            if start_y != end_y:
                # Curved line with progress
                self._draw_curved_line_with_progress(painter, start_x, start_y, end_x, end_y, progress)
            else:
                # Straight line with progress
                progress_x = start_x + (end_x - start_x) * progress
                painter.drawLine(int(start_x), int(start_y), int(progress_x), int(start_y))
    
    def _draw_curved_line(self, painter, start_x, start_y, end_x, end_y):
        """Draw a curved line between two points on different timelines"""
        from PySide6.QtGui import QPainterPath
        
        path = QPainterPath()
        path.moveTo(start_x, start_y)
        
        # Create a smooth curve
        control_x = (start_x + end_x) / 2
        control_y1 = start_y
        control_y2 = end_y
        
        # Use cubic bezier curve for smooth transition
        path.cubicTo(control_x, control_y1, control_x, control_y2, end_x, end_y)
        painter.drawPath(path)
    
    def _draw_curved_line_with_progress(self, painter, start_x, start_y, end_x, end_y, progress):
        """Draw a curved line with animation progress"""
        from PySide6.QtGui import QPainterPath
        
        # Create the full path
        path = QPainterPath()
        path.moveTo(start_x, start_y)
        
        control_x = (start_x + end_x) / 2
        control_y1 = start_y
        control_y2 = end_y
        
        path.cubicTo(control_x, control_y1, control_x, control_y2, end_x, end_y)
        
        # Get the point at the current progress
        progress_point = path.pointAtPercent(progress)
        
        # Create a new path from start to progress point
        progress_path = QPainterPath()
        progress_path.moveTo(start_x, start_y)
        
        if progress < 1.0:
            # Interpolate the control points
            prog_control_x = start_x + (control_x - start_x) * min(progress * 2, 1.0)
            prog_control_y1 = start_y
            prog_control_y2 = start_y + (control_y2 - start_y) * min(progress * 2, 1.0)
            
            if progress > 0.5:
                # Second half of the curve
                prog_control_x = control_x + (end_x - control_x) * (progress - 0.5) * 2
                prog_control_y2 = control_y2
            
            progress_path.cubicTo(prog_control_x, prog_control_y1, prog_control_x, prog_control_y2, progress_point.x(), progress_point.y())
        else:
            progress_path.cubicTo(control_x, control_y1, control_x, control_y2, end_x, end_y)
        
        painter.drawPath(progress_path)
    
    def _draw_task_box(self, painter, task, x, y, box_width, color, border_width):
        """Draw a single task box with optional animated border"""
        # Draw box
        rect = QRect(int(x), int(y), int(box_width), self._box_height)
        
        # Store rectangle for click detection
        task_key = task['key']
        self._task_rects[task_key] = rect
        
        # Check if this task is being hovered
        is_hovered = (task_key == self._hovered_task_key)
        
        # Fill box with semi-transparent background
        painter.setPen(Qt.NoPen)
        fill_color = QColor(color)
        # Increase alpha for hover effect
        fill_color.setAlpha(100 if is_hovered else 50)
        painter.setBrush(fill_color)
        painter.drawRoundedRect(rect, 5, 5)
        
        # Check if this is the current task
        is_current = (task['key'] == self._current_task_key)
        
        # Check if this is a 0-second delay task (should show blue border immediately)
        has_zero_delay = False
        if is_current:
            delay = task.get('delay_before_action', None)
            if delay is not None:
                try:
                    # Handle string "0", empty string "", None, 0, 0.0, etc.
                    if delay == "" or delay == 0 or delay == 0.0 or delay == "0" or delay == "0.0":
                        has_zero_delay = True
                        delay_val = 0
                    else:
                        delay_val = float(delay)
                        has_zero_delay = (delay_val == 0.0)
                except (ValueError, TypeError):
                    has_zero_delay = False
            else:
                # If delay is None, treat as 0
                has_zero_delay = True
        
        # Draw border based on task state
        if is_current and (self._current_task_progress > 0.0 or has_zero_delay):
            # Draw animated border for current task (or instant blue for 0-delay tasks)
            # For 0-delay tasks, draw full blue border instantly
            self._draw_animated_border(painter, rect, color, border_width, force_full=has_zero_delay)
        else:
            # Draw normal border (brighter if hovered)
            border_color = QColor("#55aaff") if is_hovered else color
            pen = QPen(border_color, border_width + (1 if is_hovered else 0))
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 5, 5)
        
        # Draw text
        painter.setPen(self._text_color)
        font = QFont("JetBrains Mono", 8)
        if is_current:
            font.setBold(True)
        painter.setFont(font)
        
        # Handle text truncation - don't truncate current task
        text = task['task_object']
        if is_current:
            # Current task: don't truncate, show full text
            display_text = text
        else:
            # Other tasks: truncate if too long
            fm = painter.fontMetrics()
            display_text = fm.elidedText(text, Qt.ElideRight, int(box_width - 10))
        
        painter.drawText(rect, Qt.AlignCenter, display_text)
    
    def _draw_animated_border(self, painter, rect, color, border_width, force_full=False):
        """Draw animated border that fills left to right based on progress
        
        Args:
            painter: QPainter instance
            rect: Rectangle to draw border in
            color: Base border color
            border_width: Width of the border
            force_full: If True, draw full blue border regardless of progress (for 0-delay tasks)
        """
        # Draw base border (inactive)
        base_pen = QPen(color, border_width)
        painter.setPen(base_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 5, 5)
        
        # Calculate progress width (use full width if forced)
        if force_full:
            progress_width = rect.width()
        else:
            progress_width = rect.width() * self._current_task_progress
        
        if progress_width > 0:
            # Create clipping region for the animated portion
            from PySide6.QtGui import QRegion
            progress_rect = QRect(rect.x(), rect.y(), int(progress_width), rect.height())
            
            # Save current state
            painter.save()
            
            # Set clipping region
            painter.setClipRect(progress_rect)
            
            # Draw animated border (bright blue)
            animated_pen = QPen(self._line_color, border_width + 1)
            painter.setPen(animated_pen)
            painter.drawRoundedRect(rect, 5, 5)
            
            # Add glow effect
            glow_pen = QPen(self._line_color, border_width + 3)
            glow_color = QColor(self._line_color)
            glow_color.setAlpha(100)
            glow_pen.setColor(glow_color)
            painter.setPen(glow_pen)
            painter.drawRoundedRect(rect, 5, 5)
            
            # Restore state
            painter.restore()
    
    def set_colors(self, tars_color=None, pilot_color=None, current_color=None, 
                   background_color=None, text_color=None, line_color=None):
        """Set custom colors for the widget"""
        if tars_color:
            self._tars_color = QColor(tars_color)
        if pilot_color:
            self._pilot_color = QColor(pilot_color)
        if current_color:
            self._current_task_color = QColor(current_color)
        if background_color:
            self._background_color = QColor(background_color)
        if text_color:
            self._text_color = QColor(text_color)
        if line_color:
            self._line_color = QColor(line_color)
        self._cache_valid = False
        self.update()