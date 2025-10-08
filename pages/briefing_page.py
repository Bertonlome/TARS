"""
Briefing Page Module
Handles all functionality for the briefing page
"""

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QPen, QBrush, QPainterPath, QFont, QPainter, QColor
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsLineItem,
    QGraphicsPathItem, QGraphicsSimpleTextItem, QGraphicsTextItem
)
from pages.base_page import BasePage
from typing import TYPE_CHECKING
import csv
from pathlib import Path

# Import for type hints only
if TYPE_CHECKING:
    from modules.ui_main import Ui_MainWindow
    from main import MainWindow

# ---------------------------- Data ----------------------------

class Task:
    def __init__(self, procedure_name, name, human_can, agent_can, human_supports, agent_supports):
        self.procedure_name = procedure_name
        self.name = name
        self.human_can = bool(int(human_can)) if str(human_can).strip() != "" else False
        self.agent_can = bool(int(agent_can)) if str(agent_can).strip() != "" else False
        self.human_supports = bool(int(human_supports)) if str(human_supports).strip() != "" else False
        self.agent_supports = bool(int(agent_supports)) if str(agent_supports).strip() != "" else False

def load_tasks(csv_path: Path = None):
    """Load tasks from CSV or return demo data"""
    if csv_path and csv_path.exists():
        tasks = []
        
        def color_to_capability(color_value):
            """Convert color values to capability (1 for green, 0 for red/yellow/empty)"""
            if isinstance(color_value, str):
                color_value = color_value.strip().lower()
                return 1 if color_value == "green" else 0
            return 0
        
        def color_to_support(color_value):
            """Convert color values to support (1 for green/yellow, 0 for red/empty)"""
            if isinstance(color_value, str):
                color_value = color_value.strip().lower()
                return 1 if color_value in ["green", "yellow"] else 0
            return 0
        
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Get values from your CSV columns
                procedure_name = row.get("Procedure", "").strip()
                task_name = row.get("Task Object", "").strip()
                human_capability = row.get("Human*", "").strip()
                agent_capability = row.get("TARS", "").strip()
                agent_support = row.get("TARS*", "").strip()
                human_support = row.get("Human", "").strip()
                
                # Skip empty rows
                if not task_name or not procedure_name:
                    continue
                
                # Convert colors to numbers
                human_can = color_to_capability(human_capability)
                agent_can = color_to_capability(agent_capability)
                human_supports = color_to_support(human_support)
                agent_supports = color_to_support(agent_support)
                
                tasks.append(Task(
                    procedure_name,
                    task_name,
                    human_can,
                    agent_can,
                    human_supports,
                    agent_supports,
                ))
        return tasks

    # Hardcoded demo data for normal operations
    demo = [
        ("pre-takeoff", "Confirm takeoff clearance", 1, 0, 0, 0),
        ("pre-takeoff", "Align with runway centerline", 1, 1, 0, 0),
        ("pre-takeoff", "Check winds", 1, 1, 1, 1),
        ("pre-takeoff", "Hold brakes", 1, 1, 0, 0),
        ("takeoff", "Advance thrust", 0, 1, 0, 0),
        ("takeoff", "Airspeed alive callout", 1, 1, 0, 0),
        ("takeoff", "80 knots cross-check", 1, 1, 1, 0),
        ("takeoff", "Rotate", 1, 0, 0, 0),
        ("takeoff", "Positive rate", 1, 1, 0, 0),
        ("takeoff", "Gear up", 1, 1, 0, 1),
    ]
    return [Task(*t) for t in demo]

# ---------------------------- Scene items ----------------------------

class ClickNode(QGraphicsEllipseItem):
    """Clickable node for performer selection"""
    
    def __init__(self, row: int, role: str, center: QPointF, radius: float, scene_parent):
        super().__init__(0, 0, radius*2, radius*2)
        self.setPos(center - QPointF(radius, radius))
        # Start with dashed white circle (no fill)
        self.setBrush(QBrush())  # No fill color
        self.setPen(QPen(Qt.white, 2.0, Qt.DashLine))  # Dashed white outline
        self.setZValue(10)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.row = row
        self.role = role
        self.scene_parent = scene_parent
        self.is_selected = False

    def mousePressEvent(self, event):
        """Handle node click"""
        print(f"Node clicked: Row {self.row}, Role {self.role}")
        self.scene_parent.on_node_clicked(self.row, self.role)
        super().mousePressEvent(event)
    
    def set_selected(self, selected: bool):
        """Update visual appearance based on selection state"""
        self.is_selected = selected
        if selected:
            # Selected: filled green circle with solid border
            self.setBrush(QBrush(Qt.green))
            self.setPen(QPen(Qt.darkGreen, 2.0, Qt.SolidLine))
        else:
            # Not selected: dashed white circle with no fill
            self.setBrush(QBrush())  # No fill color (transparent)
            self.setPen(QPen(Qt.white, 2.0, Qt.DashLine))  # Dashed white outline

class SupportNode(QGraphicsRectItem):
    """Rectangle marker for supporter (purely visual)."""
    def __init__(self, center: QPointF, size: float = 14):
        super().__init__(0, 0, size, size)
        self.setPos(center - QPointF(size/2, size/2))
        self.setBrush(QBrush(Qt.white))
        pen = QPen(Qt.darkGreen, 1.2, Qt.SolidLine)
        self.setPen(pen)
        self.setZValue(9)

# ---------------------------- View/Scene ----------------------------

class InterdependenceScene(QGraphicsScene):
    def __init__(self, tasks: list[Task], parent=None, selection_callback=None):
        super().__init__(parent)
        self.tasks = tasks
        self.selection_callback = selection_callback  # Callback to notify parent of selection changes

        # Layout constants
        self.margin_left = 350
        self.margin_right = 10
        self.margin_top = 180
        self.row_h = 80  # Reduced row height for more compact layout
        self.procedure_spacing = 120  # Extra space between procedures
        self.col_x = {
            "HUMAN": 380,
            "TARS": 820
        }
        self.node_r = 20

        # Group tasks by procedure
        self.procedures = self._group_tasks_by_procedure()

        # State: which performer is currently selected at each row
        self.selected: dict[int, str] = {}  # row -> "HUMAN"/"TARS"
        
        # Keep track of nodes for visual updates
        self.nodes: dict[tuple[int, str], ClickNode] = {}  # (row, role) -> node

        # Persistent items
        self.path_items: list[QGraphicsPathItem] = []   # solid path between rows
        self.dashed_items: list[QGraphicsLineItem] = [] # dashed supporter lines

        self._build_static()
        self._build_nodes_and_supporters()
        self._update_path()

    def _group_tasks_by_procedure(self):
        """Group tasks by procedure name and maintain order"""
        procedures = {}
        procedure_order = []
        
        for i, task in enumerate(self.tasks):
            if task.procedure_name not in procedures:
                procedures[task.procedure_name] = []
                procedure_order.append(task.procedure_name)
            procedures[task.procedure_name].append((i, task))
        
        # Return ordered list of (procedure_name, [(task_index, task), ...])
        return [(proc_name, procedures[proc_name]) for proc_name in procedure_order]

    def _create_wrapped_text_item(self, text: str, max_width_chars: int = 25) -> tuple[QGraphicsTextItem, int]:
        """Create a QGraphicsTextItem with text wrapping for long task names
        
        Returns:
            tuple: (QGraphicsTextItem, number_of_lines)
        """
        # Check if wrapping is needed
        if len(text) > max_width_chars:
            # Simple word wrapping: split long text into lines
            words = text.split()
            lines = []
            current_line = ""
            
            for word in words:
                # Check if adding this word would exceed the limit
                test_line = current_line + (" " if current_line else "") + word
                if len(test_line) <= max_width_chars:
                    current_line = test_line
                else:
                    # Start a new line
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            
            # Add the last line
            if current_line:
                lines.append(current_line)
            
            # Join with line breaks and add indentation to each line
            display_text = "\n".join(f"  {line}" for line in lines)
            num_lines = len(lines)
        else:
            # Single line with indentation
            display_text = f"  {text}"
            num_lines = 1
        
        # Create QGraphicsTextItem for multi-line support
        text_item = QGraphicsTextItem(display_text)
        text_item.setDefaultTextColor(QColor("#ffffff"))
        
        # Set font
        font = QFont()
        font.setPointSize(14)
        text_item.setFont(font)
        
        return text_item, num_lines

    def _build_static(self):
        """Build static elements (title, headers, labels)"""
        # Main title
        title = QGraphicsSimpleTextItem("NORMAL Operation Briefing and task allocation")
        f = QFont()
        f.setPointSize(20)
        title.setFont(f)
        title.setBrush(QBrush(QColor("#ffffff")))
        title.setPos(self.margin_left, 20)
        self.addItem(title)

        # Build procedure sections
        current_y = self.margin_top
        
        for proc_name, tasks_in_proc in self.procedures:
            # Procedure title
            proc_title = QGraphicsSimpleTextItem(proc_name.upper())
            proc_font = QFont()
            proc_font.setPointSize(18)
            proc_font.setBold(True)
            proc_title.setFont(proc_font)
            proc_title.setBrush(QBrush(QColor("#ffffff")))  # White color for procedure titles
            
            # Center the title between HUMAN and TARS columns
            center_x = (self.col_x["HUMAN"] + self.col_x["TARS"]) / 2
            title_width = proc_title.boundingRect().width()
            centered_x = center_x - (title_width / 2)
            proc_title.setPos(centered_x, current_y - 100)
            self.addItem(proc_title)
            
            # Column headers for this procedure (HUMAN and TARS above each procedure)
            for col, x in self.col_x.items():
                h = QGraphicsSimpleTextItem(col)
                hf = QFont()
                hf.setPointSize(16)
                h.setFont(hf)
                h.setPos(x - 30, current_y - 60)  # Position just above the procedure tasks
                h.setBrush(QBrush(QColor("#ffffff")))
                self.addItem(h)
            
            # Task labels and row guide lines for this procedure
            for local_index, (task_index, task) in enumerate(tasks_in_proc):
                y = current_y + local_index * self.row_h
                
                # Task label with text wrapping
                label, num_lines = self._create_wrapped_text_item(task.name, max_width_chars=20)
                label.setPos(20, y - 10)
                self.addItem(label)

                # Faint row line
                pen = QPen(Qt.lightGray, 0.8, Qt.DotLine)
                self.addLine(self.margin_left-80, y, self.col_x["TARS"]+200, y, pen)
            
            # Update current_y for next procedure (add space between procedures)
            current_y += len(tasks_in_proc) * self.row_h + self.procedure_spacing

        # Scene rect adjusted to fit actual content bounds
        content_left = 0
        content_right = self.col_x["TARS"] + 100
        content_top = 20
        # Calculate total height based on all procedures
        total_height = current_y + 50  # Add some bottom padding
        width = content_right - content_left
        
        self.setSceneRect(content_left, content_top, width, total_height)

    def _build_nodes_and_supporters(self):
        """Build clickable performer nodes and supporter rectangles"""
        for row, t in enumerate(self.tasks):
            y = self._row_y(row)

            # HUMAN performer
            if t.human_can:
                node = ClickNode(row, "HUMAN", QPointF(self.col_x["HUMAN"], y), self.node_r, self)
                self.addItem(node)
                self.nodes[(row, "HUMAN")] = node  # Store reference
                # Only add support rectangle (not the dashed line yet)
                if t.human_supports:
                    sup = SupportNode(QPointF(self.col_x["TARS"], y))
                    self.addItem(sup)

            # TARS performer
            if t.agent_can:
                node = ClickNode(row, "TARS", QPointF(self.col_x["TARS"], y), self.node_r, self)
                self.addItem(node)
                self.nodes[(row, "TARS")] = node  # Store reference
                # Only add support rectangle (not the dashed line yet)
                if t.agent_supports:
                    sup = SupportNode(QPointF(self.col_x["HUMAN"], y))
                    self.addItem(sup)

    def _add_dashed(self, x1, x2, y):
        """Add dashed support line"""
        pen = QPen(Qt.darkGreen, 1.4, Qt.DashLine)
        line = self.addLine(x1, y, x2, y, pen)
        line.setZValue(1)
        self.dashed_items.append(line)

    def _row_y(self, row: int) -> float:
        """Get Y coordinate for row based on procedure grouping"""
        # Find which procedure this row belongs to
        current_y = self.margin_top
        
        for proc_name, tasks_in_proc in self.procedures:
            # Check if the row is in this procedure
            task_indices = [task_index for task_index, _ in tasks_in_proc]
            
            if row in task_indices:
                # Find the position within this procedure
                local_index = task_indices.index(row)
                return current_y + local_index * self.row_h
            
            # Move to next procedure
            current_y += len(tasks_in_proc) * self.row_h + self.procedure_spacing
        
        # Fallback to old calculation if not found
        return self.margin_top + row * self.row_h

    def on_node_clicked(self, row: int, role: str):
        """Handle node click"""
        # Update selection state
        old_selection = self.selected.get(row)
        self.selected[row] = role
        
        # Update visual state of nodes in this row
        for (node_row, node_role), node in self.nodes.items():
            if node_row == row:
                # Set selected state based on whether this node is the selected one
                node.set_selected(node_role == role)
        
        # Update support lines based on current selections
        self._update_support_lines()
        
        # Update connecting paths
        self._update_path()
        print(f"Selected {role} for task {row}: {self.tasks[row].name}")
        
        # If selection changed, log it
        if old_selection != role:
            print(f"  Changed from {old_selection} to {role}")
        else:
            print(f"  Confirmed selection: {role}")
        
        # Notify parent of selection change
        if self.selection_callback:
            self.selection_callback()

    def _update_support_lines(self):
        """Update support lines based on current selections"""
        # Remove old support lines
        for item in self.dashed_items:
            self.removeItem(item)
        self.dashed_items.clear()
        
        # Add support lines only for selected performers who have support
        for row, selected_role in self.selected.items():
            task = self.tasks[row]
            y = self._row_y(row)
            
            if selected_role == "HUMAN" and task.human_supports:
                # Human is selected and can support TARS
                self._add_dashed(self.col_x["HUMAN"], self.col_x["TARS"], y)
                print(f"  Added support line: HUMAN -> TARS for task {row}")
                
            elif selected_role == "TARS" and task.agent_supports:
                # TARS is selected and can support HUMAN
                self._add_dashed(self.col_x["TARS"], self.col_x["HUMAN"], y)
                print(f"  Added support line: TARS -> HUMAN for task {row}")

    def _update_path(self):
        """Update the solid path between selected performers"""
        # Remove old
        for item in self.path_items:
            self.removeItem(item)
        self.path_items.clear()

        # Debug: Print current selections
        print(f"Current selections: {self.selected}")

        # Build path only through rows that have a selection
        pen = QPen(Qt.black, 3.0, Qt.SolidLine)  # Made thicker for visibility

        # Solid segments between consecutive selected rows:
        paths_created = 0
        for i in range(len(self.tasks) - 1):
            if i in self.selected and (i+1) in self.selected:
                y1 = self._row_y(i)
                y2 = self._row_y(i+1)
                x1 = self.col_x[self.selected[i]]
                x2 = self.col_x[self.selected[i+1]]

                print(f"Creating path from task {i} to {i+1}: ({x1}, {y1}) -> ({x2}, {y2})")

                path = QPainterPath(QPointF(x1, y1))
                # straight vertical if x1==x2; else a simple 2-segment line looks good
                if x1 == x2:
                    # Vertical line for same performer
                    path.lineTo(QPointF(x2, y2))
                    print(f"  Vertical path created")
                else:
                    # Angled path for different performers
                    mid_y = (y1 + y2) / 2
                    path.lineTo(QPointF(x1, mid_y))
                    path.lineTo(QPointF(x2, mid_y))
                    path.lineTo(QPointF(x2, y2))
                    print(f"  Angled path created via ({x1}, {mid_y}) -> ({x2}, {mid_y})")

                item = QGraphicsPathItem(path)
                item.setPen(pen)
                item.setZValue(2)
                self.addItem(item)
                self.path_items.append(item)
                paths_created += 1

        print(f"Total paths created: {paths_created}")
        
        # Force scene update
        self.update()

    def hide_non_selected_nodes(self):
        """Hide all non-selected performer nodes to show final selection"""
        print("Hiding non-selected nodes...")
        
        hidden_count = 0
        visible_count = 0
        
        for (row, role), node in self.nodes.items():
            if row in self.selected and self.selected[row] == role:
                # This node is selected, keep it visible
                node.setVisible(True)
                visible_count += 1
            else:
                # This node is not selected, hide it
                node.setVisible(False)
                hidden_count += 1
        
        print(f"  Hidden {hidden_count} non-selected nodes")
        print(f"  Kept {visible_count} selected nodes visible")
        
        # Force scene update to reflect changes
        self.update()

    def show_all_nodes(self):
        """Show all performer nodes (reset from validation state)"""
        print("Showing all nodes...")
        
        for (row, role), node in self.nodes.items():
            node.setVisible(True)
        
        print("  All nodes are now visible")
        
        # Force scene update to reflect changes
        self.update()

class BriefingPage(BasePage):
    """
    Briefing page functionality with interdependence analysis
    """
    
    def __init__(self, widgets: 'Ui_MainWindow', main_window: 'MainWindow'):
        super().__init__(widgets, main_window)
        
        # Page-specific attributes
        self.briefing_data = {}
        self.current_mission = None
        
        # Interdependence analysis attributes
        self.tasks = None
        self.interdependence_scene = None
        
        # Validation state
        self.validation_active = False
        self.original_button_text = ""
        
        # Track completion state
        self.all_tasks_assigned = False
        
    def initialize_page(self):
        """
        Initialize the briefing page UI and connections
        """
        print("Initializing Briefing Page...")
        
        # Set up UI elements
        self.setup_briefing_ui()
        
        # Set up interdependence analysis
        self.setup_interdependence_analysis()
        
        # Connect signals
        self.connect_briefing_signals()
        
        # Load initial data
        self.load_briefing_data()
        
    def setup_interdependence_analysis(self):
        """Setup the interdependence analysis table"""
        try:
            # Load tasks from CSV or use demo data
            csv_file_path = Path(__file__).parent / "table_data_with_opd.csv"
            self.tasks = load_tasks(csv_file_path)
            
            # Create and setup the interdependence scene with callback
            self.interdependence_scene = InterdependenceScene(
                self.tasks, 
                selection_callback=self._check_all_tasks_assigned
            )
            
            # Connect the scene to the QGraphicsView widget
            if hasattr(self.widgets, 'normal_operation_ia_graph'):
                self.widgets.normal_operation_ia_graph.setScene(self.interdependence_scene)
                # Enable mouse interaction
                self.widgets.normal_operation_ia_graph.setDragMode(QGraphicsView.RubberBandDrag)
                self.widgets.normal_operation_ia_graph.setRenderHint(QPainter.Antialiasing, True)
                
                # Enable scrollbars for large content instead of fitting everything
                self.widgets.normal_operation_ia_graph.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                self.widgets.normal_operation_ia_graph.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                
                # Set a reasonable scale (1.0 = normal size, no shrinking)
                self.widgets.normal_operation_ia_graph.resetTransform()
                
                # Optionally, scroll to top-left to show the beginning
                self.widgets.normal_operation_ia_graph.ensureVisible(0, 0, 50, 50)
                
                print("Interdependence analysis setup completed")
                
                # Set initial button state (should be disabled initially)
                self._check_all_tasks_assigned()
                
            else:
                print("Warning: normal_operation_ia_graph widget not found in UI")
                
        except Exception as e:
            print(f"Error setting up interdependence analysis: {e}")
        
    def setup_briefing_ui(self):
        """
        Set up UI elements specific to the briefing page
        """
        # Example: If you have specific widgets on the briefing page
        # You can access them through self.widgets.briefing.findChild()
        
        # Example: Set page title or labels
        try:
            # Look for common widget names that might exist
            if hasattr(self.widgets.briefing, 'label_title'):
                self.widgets.briefing.label_title.setText("Mission Briefing")
            
            # Add more UI setup as needed
            print("Briefing UI setup completed")
            
        except Exception as e:
            print(f"Note: Some UI elements not found (this is normal): {e}")
    
    def connect_briefing_signals(self):
        """
        Connect signals specific to the briefing page
        """
        # Connect validate briefing button
        try:
            if hasattr(self.widgets, 'validate_briefing_button'):
                self.widgets.validate_briefing_button.clicked.connect(self.toggle_validation_state)
                
                # Store initial button text and ensure initial styling
                self.original_button_text = self.widgets.validate_briefing_button.text()
                self._set_button_to_disabled_state()  # Ensure initial state is correct
                
                print("Validate briefing button connected")
                
            else:
                print("Warning: validate_briefing_button not found in UI")
        except Exception as e:
            print(f"Error connecting validate briefing button: {e}")
        
        # Example: Connect other buttons, input fields, etc.
        # self.widgets.briefing.btn_start_mission.clicked.connect(self.start_mission)
        # self.widgets.briefing.btn_load_briefing.clicked.connect(self.load_briefing_file)
        
        print("Briefing signals connected")
    
    def load_briefing_data(self):
        """
        Load briefing data when page initializes
        """
        # Example: Load mission data, weather info, etc.
        self.briefing_data = {
            'mission_type': 'Training',
            'duration': '2 hours',
            'weather': 'Clear',
            'objectives': [
                'Navigate to waypoint Alpha',
                'Perform system checks',
                'Return to base'
            ]
        }
        
        # Update UI with loaded data
        self.update_briefing_display()
        
    def update_briefing_display(self):
        """
        Update the briefing display with current data
        """
        # Example: Update labels, lists, etc. with briefing data
        print(f"Briefing updated: {self.briefing_data}")

        # Note: These widget references are available for interdependence analysis
        # self.widgets.normal_operation_IA_page - the tab containing the analysis
        # self.widgets.normal_operation_ia_graph - the QGraphicsView for the graph

        # You can add actual UI updates here when you have specific widgets
    
    def on_page_show(self):
        """
        Called every time the briefing page is shown
        """
        print("Briefing page shown")
        
        # Example: Refresh data, update displays, etc.
        self.refresh_briefing_info()
        
        # Example: Start any timers or background processes
        self.start_page_updates()
    
    def on_page_hide(self):
        """
        Called when leaving the briefing page
        """
        print("Briefing page hidden")
        
        # Example: Save current state, stop timers, etc.
        self.save_briefing_state()
        
        # Example: Stop any background processes
        self.stop_page_updates()
    
    def refresh_briefing_info(self):
        """
        Refresh briefing information when page is shown
        """
        # Example: Update weather, mission status, etc.
        print("Refreshing briefing information...")
        
        # Refresh interdependence analysis if needed
        if self.interdependence_scene:
            print("Interdependence analysis ready")
    
    def start_page_updates(self):
        """
        Start any periodic updates needed for this page
        """
        # Example: Start timers for real-time updates
        pass
    
    def stop_page_updates(self):
        """
        Stop periodic updates when leaving the page
        """
        # Example: Stop timers
        pass
    
    def save_briefing_state(self):
        """
        Save current briefing state when leaving page
        """
        # Example: Save user inputs, selections, etc.
        pass
    
    # Custom methods for briefing functionality
    def start_mission(self):
        """
        Start a mission from the briefing
        """
        print("Starting mission from briefing...")
        # Add mission start logic here
    
    def load_briefing_file(self):
        """
        Load a briefing from file
        """
        print("Loading briefing file...")
        # Add file loading logic here
    
    def export_briefing(self):
        """
        Export current briefing
        """
        print("Exporting briefing...")
        # Add export logic here
    
    # Validation methods
    def toggle_validation_state(self):
        """
        Toggle between validation and reset states
        """
        if not hasattr(self, 'validation_active'):
            self.validation_active = False
        
        # Only allow toggle if all tasks are assigned    
        if not self.all_tasks_assigned and not self.validation_active:
            print("Cannot validate: Not all tasks have been assigned performers")
            return
            
        if not self.validation_active:
            # Currently in normal state, validate the briefing
            self.validate_briefing()
            self._set_button_to_reset_state()
            self.validation_active = True
        else:
            # Currently in validated state, reset the validation
            self.reset_validation()
            self._set_button_to_validate_state()
            self.validation_active = False
    
    def _set_button_to_reset_state(self):
        """Set button appearance and text for reset state"""
        if hasattr(self.widgets, 'validate_briefing_button'):
            button = self.widgets.validate_briefing_button
            
            # Change text to reset
            button.setText("Reset Selection")
            
            # Apply darker pressed/active styling
            button.setStyleSheet("""
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
    
    def _set_button_to_validate_state(self):
        """Set button appearance and text for validate state"""
        if hasattr(self.widgets, 'validate_briefing_button'):
            button = self.widgets.validate_briefing_button
            
            # Change text back to validate
            button.setText("Validate Briefing")
            
            # Apply original styling
            button.setStyleSheet("""
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

    def _check_all_tasks_assigned(self):
        """Check if all tasks have been assigned performers"""
        if not self.interdependence_scene or not self.tasks:
            return False
        
        # Check if we have selections for all tasks
        total_tasks = len(self.tasks)
        assigned_tasks = len(self.interdependence_scene.selected)
        
        all_assigned = assigned_tasks == total_tasks
        
        # Update button state if assignment status changed
        if all_assigned != self.all_tasks_assigned:
            self.all_tasks_assigned = all_assigned
            self._update_button_state()
            
        return all_assigned
    
    def _update_button_state(self):
        """Update button enabled/disabled state and styling"""
        if hasattr(self.widgets, 'validate_briefing_button'):
            button = self.widgets.validate_briefing_button
            
            if self.all_tasks_assigned:
                # All tasks assigned - enable button
                button.setEnabled(True)
                if self.validation_active:
                    self._set_button_to_reset_state()
                else:
                    self._set_button_to_validate_state()
            else:
                # Not all tasks assigned - disable button
                button.setEnabled(False)
                self._set_button_to_disabled_state()
    
    def _set_button_to_disabled_state(self):
        """Set button appearance for disabled state"""
        if hasattr(self.widgets, 'validate_briefing_button'):
            button = self.widgets.validate_briefing_button
            
            # Show how many tasks still need assignment
            button.setText("Assign all tasks")
            
            # Apply disabled styling with !important to override Qt Designer styles
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid rgba(128, 128, 128, 255) !important;
                    border-radius: 5px !important;
                    background-color: rgba(128, 128, 128, 255) !important;
                    font: 600 16pt "JetBrains Mono" !important;
                    color: rgba(255, 255, 255, 180) !important;
                }
                QPushButton:disabled {
                    border: 2px solid rgba(100, 100, 100, 255) !important;
                    border-radius: 5px !important;
                    background-color: rgba(100, 100, 100, 255) !important;
                    font: 600 16pt "JetBrains Mono" !important;
                    color: rgba(255, 255, 255, 120) !important;
                }
                QPushButton:hover:disabled {
                    border: 2px solid rgba(100, 100, 100, 255) !important;
                    background-color: rgba(100, 100, 100, 255) !important;
                }
            """)

    def validate_briefing(self):
        """
        Validate the briefing and hide non-selected nodes for feedback
        """
        print("Validating briefing...")
        
        if self.interdependence_scene:
            # Hide non-selected nodes to show user's final selection
            self.interdependence_scene.hide_non_selected_nodes()
            
            # Get current selections for feedback
            selections = self.get_selected_performers()
            
            if selections:
                print(f"Briefing validated with {len(selections)} tasks assigned:")
                for task_id, performer in selections.items():
                    task_name = self.tasks[task_id].name if self.tasks else f"Task {task_id}"
                    print(f"  {task_name}: {performer}")
            else:
                print("Warning: No tasks have been assigned to performers")
        else:
            print("Error: Interdependence scene not available")
    
    def reset_validation(self):
        """
        Reset validation state and show all nodes again
        """
        print("Resetting validation...")
        
        if self.interdependence_scene:
            # Show all nodes again
            self.interdependence_scene.show_all_nodes()
            print("Validation reset - all nodes visible again")
        else:
            print("Error: Interdependence scene not available")
        
    # Interdependence analysis methods
    def get_selected_performers(self):
        """Get currently selected performers for each task"""
        if self.interdependence_scene:
            return self.interdependence_scene.selected.copy()
        return {}
    
    def reset_interdependence_analysis(self):
        """Reset all performer selections"""
        if self.interdependence_scene:
            self.interdependence_scene.selected.clear()
            self.interdependence_scene._update_path()
            print("Interdependence analysis reset")