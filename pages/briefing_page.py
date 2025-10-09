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
    def __init__(self, procedure_name, name, category, task_type, value, human_can, agent_can, human_supports, agent_supports):
        self.procedure_name = procedure_name
        self.name = name
        self.category = category  # NORM, EMER, ABNORM
        self.task_type = task_type  # SOP, Checklist, Memory Item, etc.
        self.value = value  # Task value (e.g., "CONFIRM", "PITOT-STATIC", etc.)
        self.human_can = bool(int(human_can)) if str(human_can).strip() != "" else False
        self.agent_can = bool(int(agent_can)) if str(agent_can).strip() != "" else False
        self.human_supports = bool(int(human_supports)) if str(human_supports).strip() != "" else False
        self.agent_supports = bool(int(agent_supports)) if str(agent_supports).strip() != "" else False

def load_tasks(csv_path: Path = None, category_filter: list = None):
    """Load tasks from CSV or return demo data
    
    Args:
        csv_path: Path to CSV file
        category_filter: List of categories to include (e.g., ['NORM'] or ['EMER', 'ABNORM'])
    """
    if csv_path and csv_path.exists():
        tasks = []
        
        def color_to_capability(color_value):
            """Convert color values to capability (1 for green and yellow and orange, 0 for red/empty)"""
            if isinstance(color_value, str):
                color_value = color_value.strip().lower()
                return 1 if color_value in ["green", "yellow", "orange"] else 0
            return 0
        
        def color_to_support(color_value):
            """Convert color values to support (1 for green/yellow/orange, 0 for red/empty)"""
            if isinstance(color_value, str):
                color_value = color_value.strip().lower()
                return 1 if color_value in ["green", "yellow", "orange"] else 0
            return 0
        
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Get values from your CSV columns
                procedure_name = row.get("Procedure", "").strip()
                category = row.get("Category", "").strip()
                task_type = row.get("Type", "").strip()
                task_name = row.get("Task Object", "").strip()
                value = row.get("Value", "").strip()
                human_capability = row.get("Human*", "").strip()
                agent_capability = row.get("TARS*", "").strip()
                agent_support = row.get("TARS", "").strip()
                human_support = row.get("Human", "").strip()
                
                # Skip empty rows
                if not task_name or not procedure_name:
                    continue
                
                # Filter by category if specified
                if category_filter and category not in category_filter:
                    continue
                
                # Convert colors to numbers
                human_can = color_to_capability(human_capability)
                agent_can = color_to_capability(agent_capability)
                human_supports = color_to_support(human_support)
                agent_supports = color_to_support(agent_support)
                
                tasks.append(Task(
                    procedure_name,
                    task_name,
                    category,
                    task_type,
                    value,
                    human_can,
                    agent_can,
                    human_supports,
                    agent_supports,
                ))
        return tasks

    # Hardcoded demo data for normal operations (backward compatibility)
    demo = [
        ("pre-takeoff", "Confirm takeoff clearance", "NORM", "SOP", "CONFIRM", 1, 0, 0, 0),
        ("pre-takeoff", "Align with runway centerline", "NORM", "SOP", "ALIGN", 1, 1, 0, 0),
        ("pre-takeoff", "Check winds", "NORM", "SOP", "CHECK", 1, 1, 1, 1),
        ("pre-takeoff", "Hold brakes", "NORM", "SOP", "HOLD", 1, 1, 0, 0),
        ("takeoff", "Advance thrust", "NORM", "SOP", "ADVANCE", 0, 1, 0, 0),
        ("takeoff", "Airspeed alive callout", "NORM", "SOP", "CALLOUT", 1, 1, 0, 0),
        ("takeoff", "80 knots cross-check", "NORM", "SOP", "80 KTS", 1, 1, 1, 0),
        ("takeoff", "Rotate", "NORM", "SOP", "ROTATE", 1, 0, 0, 0),
        ("takeoff", "Positive rate", "NORM", "SOP", "POS RATE", 1, 1, 0, 0),
        ("takeoff", "Gear up", "NORM", "SOP", "GEAR UP", 1, 1, 0, 1),
    ]
    
    # Filter demo data by category if specified
    if category_filter:
        demo = [task for task in demo if task[2] in category_filter]
    
    return [Task(*t) for t in demo]

def load_normal_tasks(csv_path: Path = None):
    """Load only normal operation tasks (Category == NORM)"""
    return load_tasks(csv_path, category_filter=['NORM'])

def load_contingency_tasks(csv_path: Path = None):
    """Load only contingency tasks (Category == EMER or ABNORM)"""
    return load_tasks(csv_path, category_filter=['EMER', 'ABNORM'])

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
                label, num_lines = self._create_wrapped_text_item(task.name + " " + task.value, max_width_chars=60)
                # Right-align the label by positioning it based on its width
                label_width = label.boundingRect().width()
                label.setPos(250 - label_width, y - 10)  # Subtract width to right-align
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
                # Show support rectangle in TARS column if TARS can support this task
                if t.agent_supports:
                    sup = SupportNode(QPointF(self.col_x["TARS"], y))
                    self.addItem(sup)

            # TARS performer
            if t.agent_can:
                node = ClickNode(row, "TARS", QPointF(self.col_x["TARS"], y), self.node_r, self)
                self.addItem(node)
                self.nodes[(row, "TARS")] = node  # Store reference
                # Show support rectangle in HUMAN column if HUMAN can support this task
                if t.human_supports:
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
        
        # Notify parent of selection change
        if self.selection_callback:
            self.selection_callback()

    def _update_support_lines(self):
        """Update support lines based on current selections"""
        # Remove old support lines
        for item in self.dashed_items:
            self.removeItem(item)
        self.dashed_items.clear()
        
        # Add support lines only for selected performers who have support available
        for row, selected_role in self.selected.items():
            task = self.tasks[row]
            y = self._row_y(row)
            
            if selected_role == "HUMAN" and task.agent_supports:
                # Human is selected as performer and TARS can support
                self._add_dashed(self.col_x["TARS"], self.col_x["HUMAN"], y)
                
            elif selected_role == "TARS" and task.human_supports:
                # TARS is selected as performer and HUMAN can support
                self._add_dashed(self.col_x["HUMAN"], self.col_x["TARS"], y)

    def _update_path(self):
        """Update the solid path between selected performers"""
        # Remove old
        for item in self.path_items:
            self.removeItem(item)
        self.path_items.clear()


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


                path = QPainterPath(QPointF(x1, y1))
                # straight vertical if x1==x2; else a simple 2-segment line looks good
                if x1 == x2:
                    # Vertical line for same performer
                    path.lineTo(QPointF(x2, y2))
                else:
                    # Angled path for different performers
                    mid_y = (y1 + y2) / 2
                    path.lineTo(QPointF(x1, mid_y))
                    path.lineTo(QPointF(x2, mid_y))
                    path.lineTo(QPointF(x2, y2))

                item = QGraphicsPathItem(path)
                item.setPen(pen)
                item.setZValue(2)
                self.addItem(item)
                self.path_items.append(item)
                paths_created += 1

        
        # Force scene update
        self.update()

    def hide_non_selected_nodes(self):
        """Hide all non-selected performer nodes to show final selection"""
        
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
        
        # Force scene update to reflect changes
        self.update()

    def show_all_nodes(self):
        """Show all performer nodes (reset from validation state)"""
        
        for (row, role), node in self.nodes.items():
            node.setVisible(True)
        
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
        
        # Interdependence analysis attributes - separate for normal and contingency
        self.normal_tasks = None
        self.contingency_tasks = None
        self.normal_interdependence_scene = None
        self.contingency_interdependence_scene = None
        
        # Validation state - separate for normal and contingency
        self.normal_validation_active = False
        self.contingency_validation_active = False
        self.original_briefing_button_text = "Validate Briefing"
        self.original_contingency_button_text = "Validate Contingency Plan"
        
        # Track completion state - separate for normal and contingency
        self.all_normal_tasks_assigned = False
        self.all_contingency_tasks_assigned = False
        
    def initialize_page(self):
        """
        Initialize the briefing page UI and connections
        """
        print("Initializing Briefing Page...")
        # Set up interdependence analysis
        self.setup_interdependence_analysis()
        # Connect signals
        self.connect_briefing_signals()

    def setup_interdependence_analysis(self):
        """Setup both normal and contingency interdependence analysis tables"""
        try:
            # Load tasks from CSV
            csv_file_path = Path(__file__).parent / "IA.csv"
            
            # Load normal operation tasks (Category == NORM)
            self.normal_tasks = load_normal_tasks(csv_file_path)
            print(f"Loaded {len(self.normal_tasks)} normal operation tasks")
            
            # Load contingency tasks (Category == EMER or ABNORM)
            self.contingency_tasks = load_contingency_tasks(csv_file_path)
            print(f"Loaded {len(self.contingency_tasks)} contingency tasks")
            
            # Setup normal operations graph
            self._setup_normal_operations_graph()
            
            # Setup contingency planning graph  
            self._setup_contingency_planning_graph()
                
        except Exception as e:
            print(f"Error setting up interdependence analysis: {e}")
            import traceback
            traceback.print_exc()

    def _setup_normal_operations_graph(self):
        """Setup the normal operations interdependence graph"""
        if not self.normal_tasks:
            print("No normal operation tasks to display")
            return
            
        # Create scene for normal operations
        self.normal_interdependence_scene = InterdependenceScene(
            self.normal_tasks, 
            selection_callback=self._check_normal_tasks_assigned
        )
        
        # Connect to normal_operation_ia_graph widget
        if hasattr(self.widgets, 'normal_operation_ia_graph'):
            self._configure_graphics_view(
                self.widgets.normal_operation_ia_graph, 
                self.normal_interdependence_scene,
                "Normal Operations"
            )
        else:
            print("Warning: normal_operation_ia_graph widget not found in UI")

    def _setup_contingency_planning_graph(self):
        """Setup the contingency planning interdependence graph"""
        if not self.contingency_tasks:
            print("No contingency tasks to display")
            return
            
        # Create scene for contingency planning
        self.contingency_interdependence_scene = InterdependenceScene(
            self.contingency_tasks, 
            selection_callback=self._check_contingency_tasks_assigned
        )
        
        # Connect to contingency_planning_ia_graph widget
        if hasattr(self.widgets, 'contingency_planning_ia_graph'):
            self._configure_graphics_view(
                self.widgets.contingency_planning_ia_graph, 
                self.contingency_interdependence_scene,
                "Contingency Planning"
            )
        else:
            print("Warning: contingency_planning_ia_graph widget not found in UI")

    def _configure_graphics_view(self, graphics_view, scene, graph_name):
        """Configure a QGraphicsView with the given scene"""
        graphics_view.setScene(scene)
        
        # Enable mouse interaction
        graphics_view.setDragMode(QGraphicsView.RubberBandDrag)
        graphics_view.setRenderHint(QPainter.Antialiasing, True)
        
        # Enable scrollbars for large content
        graphics_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        graphics_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Set normal scale (no shrinking)
        graphics_view.resetTransform()
        
        # Start at top-left
        graphics_view.ensureVisible(0, 0, 50, 50)
        
    
    def connect_briefing_signals(self):
        """
        Connect signals specific to the briefing page
        """
        # Connect validate briefing button
        try:
            if hasattr(self.widgets, 'validate_briefing_button'):
                self.widgets.validate_briefing_button.clicked.connect(self.toggle_normal_validation_state)
                
                # Store initial button text and ensure initial styling
                self.original_briefing_button_text = self.widgets.validate_briefing_button.text()
                self._set_normal_button_to_disabled_state()  # Ensure initial state is correct
                
                
            else:
                print("Warning: validate_briefing_button not found in UI")
        except Exception as e:
            print(f"Error connecting validate briefing button: {e}")
            
        # Connect validate contingency planning button
        try:
            if hasattr(self.widgets, 'validate_cont_planning_button'):
                self.widgets.validate_cont_planning_button.clicked.connect(self.toggle_contingency_validation_state)
                
                # Store initial button text and ensure initial styling
                self.original_contingency_button_text = self.widgets.validate_cont_planning_button.text()
                self._set_contingency_button_to_disabled_state()  # Ensure initial state is correct
                
                
            else:
                print("Warning: validate_cont_planning_button not found in UI")
        except Exception as e:
            print(f"Error connecting validate contingency planning button: {e}")
        
        # Connect load allocation buttons
        try:
            if hasattr(self.widgets, 'load_allocation_button'):
                self.widgets.load_allocation_button.clicked.connect(self.load_normal_allocation)
            else:
                print("Warning: load_allocation_button not found in UI")
        except Exception as e:
            print(f"Error connecting load normal allocation button: {e}")
            
        try:
            if hasattr(self.widgets, 'load_allocation_button_2'):
                self.widgets.load_allocation_button_2.clicked.connect(self.load_contingency_allocation)
            else:
                print("Warning: load_allocation_button_2 not found in UI")
        except Exception as e:
            print(f"Error connecting load contingency allocation button: {e}")
        
        # Example: Connect other buttons, input fields, etc.
        # self.widgets.briefing.btn_start_mission.clicked.connect(self.start_mission)
        # self.widgets.briefing.btn_load_briefing.clicked.connect(self.load_briefing_file)
        
    # Validation methods
    def toggle_normal_validation_state(self):
        """
        Toggle between validation and reset states for normal operations, or export if both validations complete
        """
        # Check if both validations are complete - if so, export
        if self.normal_validation_active and self.contingency_validation_active:
            self.export_briefing()
            return
            
        # Only allow toggle if all normal tasks are assigned    
        if not self.all_normal_tasks_assigned and not self.normal_validation_active:
            print("Cannot validate normal operations: Not all tasks have been assigned performers")
            return
            
        if not self.normal_validation_active:
            # Currently in normal state, validate the briefing
            self.validate_briefing()
            self._set_normal_button_to_reset_state()
            self.normal_validation_active = True
            if self.contingency_validation_active:
                # If contingency already validated, set both buttons to export state
                self._set_buttons_to_export_state()
        else:
            # Currently in validated state, reset the validation
            self.reset_normal_validation()
            self._set_normal_button_to_validate_state()
            self.normal_validation_active = False
    
    def toggle_contingency_validation_state(self):
        """
        Toggle between validation and reset states for contingency planning, or export if both validations complete
        """
        # Check if both validations are complete - if so, export
        if self.normal_validation_active and self.contingency_validation_active:
            self.export_briefing()
            return
            
        # Only allow toggle if all contingency tasks are assigned    
        if not self.all_contingency_tasks_assigned and not self.contingency_validation_active:
            print("Cannot validate contingency planning: Not all tasks have been assigned performers")
            return
            
        if not self.contingency_validation_active:
            # Currently in normal state, validate the contingency planning
            self.validate_contingency_planning()
            self._set_contingency_button_to_reset_state()
            self.contingency_validation_active = True
            if self.normal_validation_active:
                # If normal already validated, set both buttons to export state
                self._set_buttons_to_export_state()
        else:
            # Currently in validated state, reset the validation
            self.reset_contingency_validation()
            self._set_contingency_button_to_validate_state()
            self.contingency_validation_active = False
    
    def _set_buttons_to_export_state(self):
        """Set both buttons to export state when dual validation is complete"""
        # Set normal button to export state
        if hasattr(self.widgets, 'validate_briefing_button'):
            button = self.widgets.validate_briefing_button
            button.setText("Export Briefing")
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid rgba(255, 165, 0, 255) !important;
                    border-radius: 5px !important;
                    background-color: rgba(255, 165, 0, 255) !important;
                    font: 600 16pt "JetBrains Mono" !important;
                    color: white !important;
                }
                QPushButton:hover {
                    background-color: rgba(255, 140, 0, 255) !important;
                    border-color: rgba(255, 140, 0, 255) !important;
                }
                QPushButton:pressed {
                    background-color: rgba(255, 120, 0, 255) !important;
                    border-color: rgba(255, 120, 0, 255) !important;
                }
            """)
        
        # Set contingency button to export state
        if hasattr(self.widgets, 'validate_cont_planning_button'):
            button = self.widgets.validate_cont_planning_button
            button.setText("Export Briefing")
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid rgba(255, 165, 0, 255) !important;
                    border-radius: 5px !important;
                    background-color: rgba(255, 165, 0, 255) !important;
                    font: 600 16pt "JetBrains Mono" !important;
                    color: white !important;
                }
                QPushButton:hover {
                    background-color: rgba(255, 140, 0, 255) !important;
                    border-color: rgba(255, 140, 0, 255) !important;
                }
                QPushButton:pressed {
                    background-color: rgba(255, 120, 0, 255) !important;
                    border-color: rgba(255, 120, 0, 255) !important;
                }
            """)
    
    def reset_normal_validation(self):
        """Reset the normal operations validation analysis"""
        if self.normal_interdependence_scene:
            # Show all nodes again
            self.normal_interdependence_scene.show_all_nodes()
        else:
            print("Error: Normal interdependence scene not available")
            
    def validate_contingency_planning(self):
        """Handle validation for contingency planning interdependence analysis"""
        if self.contingency_interdependence_scene:
            # Hide non-selected nodes to show user's final selection
            self.contingency_interdependence_scene.hide_non_selected_nodes()
        else:
            print("Error: Contingency interdependence scene not available")

    def reset_contingency_validation(self):
        """Reset the contingency planning validation analysis"""
        if self.contingency_interdependence_scene:
            # Show all nodes again
            self.contingency_interdependence_scene.show_all_nodes()
        else:
            print("Error: Contingency interdependence scene not available")
    
    def export_briefing(self):
        """Export the briefing selections to CSV format"""
        import csv
        from pathlib import Path
        from datetime import datetime
        # Create export data list
        export_data = []
        # Export normal operations tasks
        normal_selections = self.get_selected_performers()
        for task_id, performer in normal_selections.items():
            if task_id < len(self.normal_tasks):
                task = self.normal_tasks[task_id]
                
                # Determine roles based on performer selection and task capabilities
                if performer == "HUMAN":
                    human_role = "performer"
                    # Only assign autonomy as supporter if the task supports it
                    autonomy_role = "supporter" if task.agent_supports else ""
                else:  # performer == "TARS"
                    autonomy_role = "performer"
                    # Only assign human as supporter if the task supports it
                    human_role = "supporter" if task.human_supports else ""
                
                export_data.append([
                    task.procedure_name,   # Procedure
                    task.category,         # Category  
                    task.task_type,        # Type
                    task.name,             # Task Object
                    task.value,            # Value
                    human_role,            # Human Role
                    autonomy_role          # Autonomy Role
                ])
        
        # Export contingency tasks
        contingency_selections = self.get_contingency_selected_performers()
        for task_id, performer in contingency_selections.items():
            if task_id < len(self.contingency_tasks):
                task = self.contingency_tasks[task_id]
                
                # Determine roles based on performer selection and task capabilities
                if performer == "HUMAN":
                    human_role = "performer"
                    # Only assign autonomy as supporter if the task supports it
                    autonomy_role = "supporter" if task.agent_supports else ""
                else:  # performer == "TARS"
                    autonomy_role = "performer"
                    # Only assign human as supporter if the task supports it
                    human_role = "supporter" if task.human_supports else ""
                
                export_data.append([
                    task.procedure_name,   # Procedure
                    task.category,         # Category
                    task.task_type,        # Type
                    task.name,             # Task Object
                    task.value,            # Value
                    human_role,            # Human Role
                    autonomy_role          # Autonomy Role
                ])
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"briefing_export_{timestamp}.csv"
        export_path = Path(__file__).parent / export_filename
        
        # Write to CSV
        try:
            with open(export_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow([
                    'Procedure', 'Category', 'Type', 'Task Object', 
                    'Value', 'Human Role', 'Autonomy Role'
                ])
                
                # Write data
                writer.writerows(export_data)
            
            print(f"Briefing exported successfully to: {export_path}")
            print(f"Exported {len(export_data)} task assignments")
            print(f"  - Normal operations: {len(normal_selections)} tasks")
            print(f"  - Contingency planning: {len(contingency_selections)} tasks")
            
        except Exception as e:
            print(f"Error exporting briefing: {e}")

    def load_normal_allocation(self):
        """Load complete briefing allocation (both normal and contingency) from CSV file"""
        self._load_complete_briefing_from_file()
    
    def load_contingency_allocation(self):
        """Load complete briefing allocation (both normal and contingency) from CSV file"""
        self._load_complete_briefing_from_file()
    
    def _load_complete_briefing_from_file(self):
        """Load complete briefing allocation (normal + contingency) from CSV file with file dialog"""
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        import csv
        # Open file dialog to select CSV file
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Load Complete Briefing Allocation", 
            str(Path.home()),
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if not file_path:
            print("No file selected")
            return
            
        try:
            # Read the CSV file and separate normal vs contingency data
            normal_allocation_data = {}
            contingency_allocation_data = {}
            
            with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                # Validate header format
                expected_headers = ['Procedure', 'Category', 'Type', 'Task Object', 'Value', 'Human Role', 'Autonomy Role']
                if not all(header in reader.fieldnames for header in expected_headers):
                    QMessageBox.warning(None, "Invalid File Format", 
                                      f"The selected CSV file does not have the expected format.\n"
                                      f"Expected headers: {', '.join(expected_headers)}")
                    return
                
                # Parse allocation data and separate by category
                for row in reader:
                    procedure = row['Procedure'].strip()
                    category = row['Category'].strip()
                    task_object = row['Task Object'].strip()
                    value = row['Value'].strip()
                    human_role = row['Human Role'].strip()
                    autonomy_role = row['Autonomy Role'].strip()
                    
                    # Determine performer based on roles
                    if human_role.strip() == "performer":
                        performer = "HUMAN"
                    elif autonomy_role.strip() == "performer":
                        performer = "TARS"
                    else:
                        print(f"Warning: Could not determine performer for task {task_object} (human_role='{human_role}', autonomy_role='{autonomy_role}')")
                        continue
                    
                    # Store allocation data based on category
                    allocation_key = (procedure, task_object, value)
                    
                    if category == "NORM":
                        normal_allocation_data[allocation_key] = performer
                    elif category in ["EMER", "ABNORM"]:
                        contingency_allocation_data[allocation_key] = performer
            
            # Apply allocations to both task sets
            normal_applied = self._apply_allocation_to_normal_tasks(normal_allocation_data)
            contingency_applied = self._apply_allocation_to_contingency_tasks(contingency_allocation_data)
            
            total_applied = normal_applied + contingency_applied
            # Show success message to user
            QMessageBox.information(None, "Briefing Loaded Successfully", 
                                  f"Loaded complete briefing configuration:\n"
                                  f"• Normal operations: {normal_applied} tasks\n"
                                  f"• Contingency planning: {contingency_applied} tasks\n"
                                  f"• Total: {total_applied} task allocations")
                
        except Exception as e:
            print(f"Error loading briefing file: {e}")
            QMessageBox.critical(None, "Error Loading File", 
                               f"An error occurred while loading the briefing file:\n{str(e)}")
    
    def _apply_allocation_to_normal_tasks(self, allocation_data):
        """Apply loaded allocation data to normal operation tasks"""
        if not self.normal_interdependence_scene or not self.normal_tasks:
            print("Normal tasks not available for allocation")
            return 0
            
        applied_count = 0
        
        for task_id, task in enumerate(self.normal_tasks):
            allocation_key = (task.procedure_name, task.name, task.value)
            
            if allocation_key in allocation_data:
                performer = allocation_data[allocation_key]
                
                # Set the selection in the scene
                self.normal_interdependence_scene.selected[task_id] = performer
                
                # Update visual representation
                if (task_id, "HUMAN") in self.normal_interdependence_scene.nodes:
                    human_node = self.normal_interdependence_scene.nodes[(task_id, "HUMAN")]
                    human_node.set_selected(performer == "HUMAN")
                    
                if (task_id, "TARS") in self.normal_interdependence_scene.nodes:
                    tars_node = self.normal_interdependence_scene.nodes[(task_id, "TARS")]
                    tars_node.set_selected(performer == "TARS")
                
                applied_count += 1
        
        # Update path visualization and check assignment status
        self.normal_interdependence_scene._update_path()
        self._check_normal_tasks_assigned()
        
        return applied_count
    
    def _apply_allocation_to_contingency_tasks(self, allocation_data):
        """Apply loaded allocation data to contingency planning tasks"""
        if not self.contingency_interdependence_scene or not self.contingency_tasks:
            print("Contingency tasks not available for allocation")
            return 0
            
        applied_count = 0
        
        for task_id, task in enumerate(self.contingency_tasks):
            allocation_key = (task.procedure_name, task.name, task.value)
            
            if allocation_key in allocation_data:
                performer = allocation_data[allocation_key]
                
                # Set the selection in the scene
                self.contingency_interdependence_scene.selected[task_id] = performer
                
                # Update visual representation
                if (task_id, "HUMAN") in self.contingency_interdependence_scene.nodes:
                    human_node = self.contingency_interdependence_scene.nodes[(task_id, "HUMAN")]
                    human_node.set_selected(performer == "HUMAN")
                    
                if (task_id, "TARS") in self.contingency_interdependence_scene.nodes:
                    tars_node = self.contingency_interdependence_scene.nodes[(task_id, "TARS")]
                    tars_node.set_selected(performer == "TARS")
                
                applied_count += 1
        
        # Update path visualization and check assignment status
        self.contingency_interdependence_scene._update_path()
        self._check_contingency_tasks_assigned()
        
        return applied_count

    def _set_normal_button_to_reset_state(self):
        """Set normal operation button appearance and text for reset state"""
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
    
    def _set_normal_button_to_validate_state(self):
        """Set normal operation button appearance and text for validate state"""
        if hasattr(self.widgets, 'validate_briefing_button'):
            button = self.widgets.validate_briefing_button
            
            # Change text back to validate
            button.setText(getattr(self, 'original_briefing_button_text', 'Validate Briefing'))
            
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

    def _set_normal_button_to_disabled_state(self):
        """Set normal operation button appearance and text for disabled state"""
        if hasattr(self.widgets, 'validate_briefing_button'):
            button = self.widgets.validate_briefing_button
            
            # Change text to indicate validation not available
            button.setText("Cannot Validate")
            
            # Apply disabled styling
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid gray !important;
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

    def _check_normal_tasks_assigned(self):
        """Check if all normal operation tasks have been assigned performers"""
        if not self.normal_interdependence_scene or not self.normal_tasks:
            return False
        
        # Check if we have selections for all normal operation tasks
        total_tasks = len(self.normal_tasks)
        assigned_tasks = len(self.normal_interdependence_scene.selected)
        
        all_assigned = assigned_tasks == total_tasks
        
        # Update button state if assignment status changed
        if all_assigned != self.all_normal_tasks_assigned:
            self.all_normal_tasks_assigned = all_assigned
            self._update_normal_button_state()
            
        return all_assigned
    
    def _check_contingency_tasks_assigned(self):
        """Check if all contingency tasks have been assigned performers"""
        if not self.contingency_interdependence_scene or not self.contingency_tasks:
            return False
        
        # Check if we have selections for all contingency tasks
        total_tasks = len(self.contingency_tasks)
        assigned_tasks = len(self.contingency_interdependence_scene.selected)
        
        all_assigned = assigned_tasks == total_tasks
        
        # Update button state if assignment status changed
        if all_assigned != self.all_contingency_tasks_assigned:
            self.all_contingency_tasks_assigned = all_assigned
            self._update_contingency_button_state()
            
        return all_assigned
    
    def _update_normal_button_state(self):
        """Update normal operation button enabled/disabled state and styling"""
        if hasattr(self.widgets, 'validate_briefing_button'):
            button = self.widgets.validate_briefing_button
            
            if self.all_normal_tasks_assigned:
                # All tasks assigned - enable button
                button.setEnabled(True)
                if self.normal_validation_active:
                    self._set_normal_button_to_reset_state()
                else:
                    self._set_normal_button_to_validate_state()
            else:
                # Not all tasks assigned - disable button
                button.setEnabled(False)
                self._set_normal_button_to_disabled_state()
                
    def _update_contingency_button_state(self):
        """Update contingency planning button enabled/disabled state and styling"""
        if hasattr(self.widgets, 'validate_cont_planning_button'):
            button = self.widgets.validate_cont_planning_button
            
            if self.all_contingency_tasks_assigned:
                # All tasks assigned - enable button
                button.setEnabled(True)
                if self.contingency_validation_active:
                    self._set_contingency_button_to_reset_state()
                else:
                    self._set_contingency_button_to_validate_state()
            else:
                # Not all tasks assigned - disable button
                button.setEnabled(False)
                self._set_contingency_button_to_disabled_state()
    
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
    
    # Contingency planning button styling methods
    def _set_contingency_button_to_reset_state(self):
        """Set contingency planning button appearance and text for reset state"""
        if hasattr(self.widgets, 'validate_cont_planning_button'):
            button = self.widgets.validate_cont_planning_button
            
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
    
    def _set_contingency_button_to_validate_state(self):
        """Set contingency planning button appearance and text for validate state"""
        if hasattr(self.widgets, 'validate_cont_planning_button'):
            button = self.widgets.validate_cont_planning_button
            
            # Change text back to validate
            button.setText(getattr(self, 'original_contingency_button_text', 'Validate Contingency Planning'))
            
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

    def _set_contingency_button_to_disabled_state(self):
        """Set contingency planning button appearance and text for disabled state"""
        if hasattr(self.widgets, 'validate_cont_planning_button'):
            button = self.widgets.validate_cont_planning_button
            
            # Change text to indicate validation not available
            button.setText("Cannot Validate")
            
            # Apply disabled styling
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid gray !important;
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
        if self.normal_interdependence_scene:
            # Hide non-selected nodes to show user's final selection
            self.normal_interdependence_scene.hide_non_selected_nodes()
            # Get current selections for feedback
        else:
            print("Error: Interdependence scene not available")
    
    def reset_validation(self):
        """
        Reset validation state and show all nodes again
        """
        if self.normal_interdependence_scene:
            # Show all nodes again
            self.normal_interdependence_scene.show_all_nodes()
        else:
            print("Error: Normal interdependence scene not available")
        
    # Interdependence analysis methods
    def get_selected_performers(self):
        """Get currently selected performers for each task"""
        if self.normal_interdependence_scene:
            return self.normal_interdependence_scene.selected.copy()
        return {}
    
    def get_contingency_selected_performers(self):
        """Get currently selected performers for each contingency task"""
        if self.contingency_interdependence_scene:
            return self.contingency_interdependence_scene.selected.copy()
        return {}
    
    def reset_interdependence_analysis(self):
        """Reset all performer selections"""
        if self.normal_interdependence_scene:
            self.normal_interdependence_scene.selected.clear()
            self.normal_interdependence_scene._update_path()