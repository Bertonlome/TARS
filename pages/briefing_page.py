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

IA_NAME_FILE = "IA_V3.csv"

# ---------------------------- Data ----------------------------

class Task:
    def __init__(self, procedure_name, name, classification, task_type, category, value, human_can, agent_can, human_supports, agent_supports, **extra_fields):
        self.procedure_name = procedure_name
        self.name = name
        self.classification = classification  # NORM, EMER, ABNORM
        self.task_type = task_type  # SOP, Checklist, Memory Item, etc.
        self.category = category  # Task category (e.g., "Switch / Lever", "Environment Check", etc.)
        self.value = value  # Task value (e.g., "CONFIRM", "PITOT-STATIC", etc.)
        self.human_can = bool(int(human_can)) if str(human_can).strip() != "" else False
        self.agent_can = bool(int(agent_can)) if str(agent_can).strip() != "" else False
        self.human_supports = bool(int(human_supports)) if str(human_supports).strip() != "" else False
        self.agent_supports = bool(int(agent_supports)) if str(agent_supports).strip() != "" else False
        
        # Store all additional CSV columns for preservation during export
        self.extra_fields = extra_fields

def load_tasks(csv_path: Path = None, classification_filter: list = None):
    """Load tasks from CSV or return demo data
    
    Args:
        csv_path: Path to CSV file
        classification_filter: List of categories to include (e.g., ['NORM'] or ['EMER', 'ABNORM'])
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
                classification = row.get("Classification", "").strip()
                task_type = row.get("Type", "").strip()
                category = row.get("Category", "").strip()
                task_name = row.get("Task Object", "").strip()
                value = row.get("Value", "").strip()
                human_capability = row.get("Human*", "").strip()
                agent_capability = row.get("TARS*", "").strip()
                agent_support = row.get("TARS", "").strip()
                human_support = row.get("Human", "").strip()
                
                # Skip empty rows
                if not task_name or not procedure_name:
                    continue
                
                # Filter by Classification if specified
                if classification_filter and classification not in classification_filter:
                    continue
                
                # Convert colors to numbers
                human_can = color_to_capability(human_capability)
                agent_can = color_to_capability(agent_capability)
                human_supports = color_to_support(human_support)
                agent_supports = color_to_support(agent_support)
                
                # Collect all extra fields to preserve them
                extra_fields = {
                    'observability': row.get("Observability", "").strip(),
                    'predictability': row.get("Predictability", "").strip(),
                    'directability': row.get("Directability", "").strip(),
                    'information_requirement': row.get("Information Requirement", "").strip(),
                    'constraint_type': row.get("Constraint Type", "").strip(),
                    'time_constraint': row.get("Time constraint (in s)", "").strip(),
                    'execution_type': row.get("Execution Type", "").strip(),
                    'interaction': row.get("interaction", "").strip(),
                    'time_to_initiate_action': row.get("Time to Initiate Action", "").strip(),
                    'time_after_ending_action': row.get("Time after Ending Action", "").strip(),
                    'callout': row.get("Callout", "").strip(),
                }
                
                tasks.append(Task(
                    procedure_name,
                    task_name,
                    classification,
                    task_type,
                    category,
                    value,
                    human_can,
                    agent_can,
                    human_supports,
                    agent_supports,
                    **extra_fields
                ))
        return tasks

    # Hardcoded demo data for normal operations (backward compatibility)
    demo = [
        ("pre-takeoff", "Confirm takeoff clearance", "NORM", "SOP", "Communication", "CONFIRM", 1, 0, 0, 0),
        ("pre-takeoff", "Align with runway centerline", "NORM", "SOP", "Flight Control", "ALIGN", 1, 1, 0, 0),
        ("pre-takeoff", "Check winds", "NORM", "SOP", "Environment Check", "CHECK", 1, 1, 1, 1),
        ("pre-takeoff", "Hold brakes", "NORM", "SOP", "Flight Control", "HOLD", 1, 1, 0, 0),
        ("takeoff", "Advance thrust", "NORM", "SOP", "Flight Control", "ADVANCE", 0, 1, 0, 0),
        ("takeoff", "Airspeed alive callout", "NORM", "SOP", "Communication", "CALLOUT", 1, 1, 0, 0),
        ("takeoff", "80 knots cross-check", "NORM", "SOP", "Parameter Check", "80 KTS", 1, 1, 1, 0),
        ("takeoff", "Rotate", "NORM", "SOP", "Flight Control", "ROTATE", 1, 0, 0, 0),
        ("takeoff", "Positive rate", "NORM", "SOP", "Parameter Check", "POS RATE", 1, 1, 0, 0),
        ("takeoff", "Gear up", "NORM", "SOP", "Switch / Lever", "GEAR UP", 1, 1, 0, 1),
    ]
    
    # Filter demo data by classification if specified
    if classification_filter:
        demo = [task for task in demo if task[2] in classification_filter]
    
    return [Task(*t) for t in demo]

def load_normal_tasks(csv_path: Path = None):
    """Load only normal operation tasks (Classification == NORM)"""
    return load_tasks(csv_path, classification_filter=['NORM'])

def load_contingency_tasks(csv_path: Path = None):
    """Load only contingency tasks (Classification == EMER or ABNORM)"""
    return load_tasks(csv_path, classification_filter=['EMER', 'ABNORM'])

def load_all_tasks_preserve_order(csv_path: Path = None):
    """Load all tasks in original CSV order (no filtering)"""
    return load_tasks(csv_path, classification_filter=None)

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
        
        # Category filtering state
        self.active_category_filter = None  # None means no filter, otherwise holds category name
        
        # Store all visual elements per task row for filtering
        self.row_elements: dict[int, list] = {}  # row_index -> [list of QGraphicsItems for that row]
        
        # Store all non-task-specific items (titles, headers) separately
        self.static_header_items = []

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

    def _build_static(self, filtered_category=None):
        """Build static elements (title, headers, labels)
        
        Args:
            filtered_category: If provided, only build elements for tasks in this category
        """
        # Main title
        title_text = "NORMAL Operation Briefing and task allocation"
        if filtered_category:
            title_text = f"NORMAL Operation - {filtered_category} Tasks"
        
        title = QGraphicsSimpleTextItem(title_text)
        f = QFont()
        f.setPointSize(20)
        title.setFont(f)
        title.setBrush(QBrush(QColor("#ffffff")))
        title.setPos(self.margin_left, 20)
        self.addItem(title)
        self.static_header_items.append(title)

        # Build procedure sections
        current_y = self.margin_top
        
        for proc_name, tasks_in_proc in self.procedures:
            # Filter tasks if category filter is active
            if filtered_category:
                tasks_in_proc = [(idx, task) for idx, task in tasks_in_proc if task.category == filtered_category]
            
            # Skip procedure if no tasks match filter
            if not tasks_in_proc:
                continue
            
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
            self.static_header_items.append(proc_title)
            
            # Column headers for this procedure (HUMAN and TARS above each procedure)
            for col, x in self.col_x.items():
                h = QGraphicsSimpleTextItem(col)
                hf = QFont()
                hf.setPointSize(16)
                h.setFont(hf)
                h.setPos(x - 30, current_y - 60)  # Position just above the procedure tasks
                h.setBrush(QBrush(QColor("#ffffff")))
                self.addItem(h)
                self.static_header_items.append(h)
            
            # Task labels and row guide lines for this procedure
            for local_index, (task_index, task) in enumerate(tasks_in_proc):
                y = current_y + local_index * self.row_h
                
                # Initialize list to store all elements for this row
                if task_index not in self.row_elements:
                    self.row_elements[task_index] = []
                
                # Task label with text wrapping
                label, num_lines = self._create_wrapped_text_item(task.name + " " + task.value, max_width_chars=60)
                # Right-align the label by positioning it based on its width
                label_width = label.boundingRect().width()
                label.setPos(250 - label_width, y - 10)  # Subtract width to right-align
                self.addItem(label)
                self.row_elements[task_index].append(label)  # Track this element

                # Faint row line
                pen = QPen(Qt.lightGray, 0.8, Qt.DotLine)
                row_line = self.addLine(self.margin_left-80, y, self.col_x["TARS"]+200, y, pen)
                self.row_elements[task_index].append(row_line)  # Track this element
            
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

    def _build_nodes_and_supporters(self, filtered_category=None):
        """Build clickable performer nodes and supporter rectangles
        
        Args:
            filtered_category: If provided, only build nodes for tasks in this category
        """
        for row, t in enumerate(self.tasks):
            # Skip tasks not in the filtered category
            if filtered_category and t.category != filtered_category:
                continue
            
            y = self._row_y(row, filtered_category)
            
            # Initialize row elements if not exists
            if row not in self.row_elements:
                self.row_elements[row] = []

            # HUMAN performer
            if t.human_can:
                node = ClickNode(row, "HUMAN", QPointF(self.col_x["HUMAN"], y), self.node_r, self)
                self.addItem(node)
                self.nodes[(row, "HUMAN")] = node  # Store reference
                self.row_elements[row].append(node)  # Track this element
                
                # Show support rectangle in TARS column if TARS can support this task
                if t.agent_supports:
                    sup = SupportNode(QPointF(self.col_x["TARS"], y))
                    self.addItem(sup)
                    self.row_elements[row].append(sup)  # Track this element

            # TARS performer
            if t.agent_can:
                node = ClickNode(row, "TARS", QPointF(self.col_x["TARS"], y), self.node_r, self)
                self.addItem(node)
                self.nodes[(row, "TARS")] = node  # Store reference
                self.row_elements[row].append(node)  # Track this element
                
                # Show support rectangle in HUMAN column if HUMAN can support this task
                if t.human_supports:
                    sup = SupportNode(QPointF(self.col_x["HUMAN"], y))
                    self.addItem(sup)
                    self.row_elements[row].append(sup)  # Track this element

    def _add_dashed(self, x1, x2, y):
        """Add dashed support line"""
        pen = QPen(Qt.darkGreen, 1.4, Qt.DashLine)
        line = self.addLine(x1, y, x2, y, pen)
        line.setZValue(1)
        self.dashed_items.append(line)

    def _row_y(self, row: int, filtered_category=None) -> float:
        """Get Y coordinate for row based on procedure grouping
        
        Args:
            row: Task row index
            filtered_category: If provided, calculate position considering only filtered tasks
        """
        # Find which procedure this row belongs to
        current_y = self.margin_top
        
        for proc_name, tasks_in_proc in self.procedures:
            # Filter tasks if category filter is active
            if filtered_category:
                filtered_tasks = [(idx, task) for idx, task in tasks_in_proc if task.category == filtered_category]
            else:
                filtered_tasks = tasks_in_proc
            
            # Skip procedure if no tasks match filter
            if not filtered_tasks:
                continue
            
            # Check if the row is in this procedure
            task_indices = [task_index for task_index, _ in filtered_tasks]
            
            if row in task_indices:
                # Find the position within this procedure
                local_index = task_indices.index(row)
                return current_y + local_index * self.row_h
            
            # Move to next procedure (only count filtered tasks for spacing)
            current_y += len(filtered_tasks) * self.row_h + self.procedure_spacing
        
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
        
        # Skip support line creation if a category filter is active
        if self.active_category_filter:
            return
        
        # Add support lines only for selected performers who have support available
        for row, selected_role in self.selected.items():
            task = self.tasks[row]
            y = self._row_y(row, self.active_category_filter)
            
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

        # Skip path creation if a category filter is active
        if self.active_category_filter:
            return

        # Build path only through rows that have a selection
        pen = QPen(Qt.black, 3.0, Qt.SolidLine)  # Made thicker for visibility

        # Solid segments between consecutive selected rows:
        paths_created = 0
        for i in range(len(self.tasks) - 1):
            if i in self.selected and (i+1) in self.selected:
                y1 = self._row_y(i, self.active_category_filter)
                y2 = self._row_y(i+1, self.active_category_filter)
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
    
    def _clear_all_scene_items(self):
        """Remove all items from the scene"""
        # Clear all items
        self.clear()
        
        # Reset tracking dictionaries
        self.row_elements.clear()
        self.static_header_items.clear()
        self.nodes.clear()
        self.path_items.clear()
        self.dashed_items.clear()
    
    def _rebuild_scene(self, filtered_category=None):
        """Completely rebuild the scene with optional category filter
        
        Args:
            filtered_category: If provided, only show tasks from this category
        """
        # Clear everything except selections
        self._clear_all_scene_items()
        
        # Rebuild with filter
        self._build_static(filtered_category)
        self._build_nodes_and_supporters(filtered_category)
        
        # Restore visual state of all nodes based on current selections
        self._restore_node_selections()
        
        # Update path and support lines
        self._update_path()
        self._update_support_lines()
    
    def _restore_node_selections(self):
        """Restore the visual state of nodes based on self.selected dictionary"""
        for row, selected_role in self.selected.items():
            # Update all nodes in this row
            if (row, "HUMAN") in self.nodes:
                self.nodes[(row, "HUMAN")].set_selected(selected_role == "HUMAN")
            if (row, "TARS") in self.nodes:
                self.nodes[(row, "TARS")].set_selected(selected_role == "TARS")
    
    def filter_by_category(self, category: str):
        """Filter the graph to show only tasks from the specified category"""
        self.active_category_filter = category
        #print(f"Filtering graph to show only category: {category}")
        
        # Completely rebuild the scene with only the filtered category
        self._rebuild_scene(filtered_category=category)
        
        # Force scene update
        self.update()
    
    def clear_category_filter(self):
        """Clear the category filter and show all tasks"""
        self.active_category_filter = None
        #print("Clearing category filter - showing all tasks")
        
        # Completely rebuild the scene with all tasks
        self._rebuild_scene(filtered_category=None)
        
        # Force scene update
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
        self.all_tasks = None  # Store all tasks in original order
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
        
        # Store validated allocation data at app level
        self.validated_allocation_data = None
        
        # Store category radio buttons for reference (now for both tabs)
        self.category_radio_buttons = {}  # {category: {"TARS": QRadioButton, "HUMAN": QRadioButton, "TARS_2": QRadioButton, "HUMAN_2": QRadioButton}}
        
        # Store category filter buttons
        self.category_filter_buttons = {}  # {category: {"button_1": QPushButton, "button_2": QPushButton}}
        self.active_filter_category = None
        
        # Store clear filter buttons (created dynamically)
        self.clear_filter_button_1 = None
        self.clear_filter_button_2 = None
        
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
            # Load ALL tasks from CSV in original order
            csv_file_path = Path(__file__).parent.parent / IA_NAME_FILE 
            self.all_tasks = load_all_tasks_preserve_order(csv_file_path)
            #print(f"Loaded {len(self.all_tasks)} total tasks in original order")
            
            # Debug: Print first few tasks to verify order preservation
            #for i, task in enumerate(self.all_tasks[:10]):
            #    print(f"  {i+1}. {task.procedure_name} - {task.name} ({task.classification})")

            # Filter for display (but maintain references to original order)
            self.normal_tasks = [task for task in self.all_tasks if task.classification == 'NORM']
            self.contingency_tasks = [task for task in self.all_tasks if task.classification in ['EMER', 'ABNORM']]
            
            #print(f"Filtered: {len(self.normal_tasks)} normal, {len(self.contingency_tasks)} contingency tasks")
            
            # Setup normal operations graph
            self._setup_normal_operations_graph()
            
            # Setup contingency planning graph  
            self._setup_contingency_planning_graph()
            
            # Auto-select tasks with only one possible performer
            self._auto_select_single_performer_tasks()
            
            # Setup category radio buttons for task allocation
            self._setup_category_radio_buttons()
                
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
        
    def _auto_select_single_performer_tasks(self):
        """Automatically select tasks that have only one possible performer"""
        #print("Auto-selecting tasks with single performer options...")
        
        # Auto-select normal operation tasks
        if self.normal_interdependence_scene and self.normal_tasks:
            auto_selected_normal = 0
            for task_id, task in enumerate(self.normal_tasks):
                # Check if only one performer option is available
                performers_available = []
                if task.human_can:
                    performers_available.append("HUMAN")
                if task.agent_can:
                    performers_available.append("TARS")
                
                # If exactly one performer is possible, auto-select it
                if len(performers_available) == 1:
                    performer = performers_available[0]
                    self.normal_interdependence_scene.on_node_clicked(task_id, performer)
                    auto_selected_normal += 1
                    #print(f"Auto-selected {performer} for normal task {task_id}: {task.name}")
            
            #print(f"Auto-selected {auto_selected_normal} normal operation tasks")
        
        # Auto-select contingency planning tasks
        if self.contingency_interdependence_scene and self.contingency_tasks:
            auto_selected_contingency = 0
            for task_id, task in enumerate(self.contingency_tasks):
                # Check if only one performer option is available
                performers_available = []
                if task.human_can:
                    performers_available.append("HUMAN")
                if task.agent_can:
                    performers_available.append("TARS")
                
                # If exactly one performer is possible, auto-select it
                if len(performers_available) == 1:
                    performer = performers_available[0]
                    self.contingency_interdependence_scene.on_node_clicked(task_id, performer)
                    auto_selected_contingency += 1
                    #print(f"Auto-selected {performer} for contingency task {task_id}: {task.name}")
            
            #print(f"Auto-selected {auto_selected_contingency} contingency planning tasks")
    
    def _get_unique_categories(self):
        """Extract unique task categories from all loaded tasks"""
        categories = set()
        
        # Extract from normal tasks
        if self.normal_tasks:
            for task in self.normal_tasks:
                if task.category:
                    categories.add(task.category)
        
        # Extract from contingency tasks
        if self.contingency_tasks:
            for task in self.contingency_tasks:
                if task.category:
                    categories.add(task.category)
        
        # Return sorted list for consistent ordering
        return sorted(list(categories))
    
    def _setup_category_radio_buttons(self):
        """Create radio button groups for each task category in both tabs"""
        from PySide6.QtWidgets import QRadioButton, QPushButton, QVBoxLayout, QButtonGroup
        from PySide6.QtCore import Qt
        
        # Get both container layouts
        if not hasattr(self.widgets, 'task_type_button_container'):
            print("Warning: task_type_button_container not found in UI")
            return
        
        if not hasattr(self.widgets, 'task_type_button_container_2'):
            print("Warning: task_type_button_container_2 not found in UI")
            return
        
        container_1 = self.widgets.task_type_button_container
        container_2 = self.widgets.task_type_button_container_2
        
        # Clear any existing widgets in both containers
        for container in [container_1, container_2]:
            while container.count():
                child = container.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        
        # Get unique categories
        categories = self._get_unique_categories()
        
        if not categories:
            print("No categories found in tasks")
            return
        
        #print(f"Creating radio buttons for {len(categories)} categories: {categories}")
        
        # Create radio button group for each category in both containers
        for category in categories:
            # Create layouts for both tabs
            category_layout_1 = QVBoxLayout()
            category_layout_1.setSpacing(5)
            category_layout_2 = QVBoxLayout()
            category_layout_2.setSpacing(5)
            
            # Create clickable category buttons (labels) for both tabs
            category_button_1 = QPushButton(category)
            category_button_2 = QPushButton(category)
            
            # Style the buttons to look like labels but be clickable
            button_style = """
                QPushButton {
                    font: 600 12pt "JetBrains Mono";
                    color: white;
                    padding: 5px;
                    background-color: transparent;
                    border: 2px solid transparent;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.1);
                    border: 2px solid rgba(255, 255, 255, 0.3);
                }
                QPushButton:pressed {
                    background-color: rgba(255, 255, 255, 0.2);
                }
            """
            
            category_button_1.setStyleSheet(button_style)
            category_button_2.setStyleSheet(button_style)
            
            category_button_1.setCursor(Qt.PointingHandCursor)
            category_button_2.setCursor(Qt.PointingHandCursor)
            
            category_layout_1.addWidget(category_button_1, alignment=Qt.AlignCenter)
            category_layout_2.addWidget(category_button_2, alignment=Qt.AlignCenter)
            
            # Store references to the filter buttons
            self.category_filter_buttons[category] = {
                "button_1": category_button_1,
                "button_2": category_button_2
            }
            
            # Connect filter button clicks (synchronized between tabs)
            # Use default argument to capture current button reference in lambda
            category_button_1.clicked.connect(
                lambda checked, cat=category, btn1=category_button_1, btn2=category_button_2: 
                self._on_category_filter_clicked(cat, btn1, btn2))
            
            category_button_2.clicked.connect(
                lambda checked, cat=category, btn1=category_button_2, btn2=category_button_1: 
                self._on_category_filter_clicked(cat, btn1, btn2))
            
            # Create button groups for both tabs to ensure only one can be selected per tab
            button_group_1 = QButtonGroup(self.main_window)
            button_group_2 = QButtonGroup(self.main_window)
            
            # Create TARS radio buttons for both tabs
            tars_radio_1 = QRadioButton("TARS")
            tars_radio_2 = QRadioButton("TARS")
            
            radio_style = """
                QRadioButton {
                    font: 500 10pt "JetBrains Mono";
                    color: white;
                    padding: 3px;
                }
                QRadioButton::indicator {
                    width: 15px;
                    height: 15px;
                    border-radius: 10px;
                    border: 3px solid rgb(52, 59, 72);
                    background: rgb(44, 49, 60);
                }
                QRadioButton::indicator:hover {
                    border: 3px solid rgb(58, 66, 81);
                }
                QRadioButton::indicator:checked {
                    background: #35de71;
                    border: 3px solid rgb(52, 59, 72);
                }
            """
            
            tars_radio_1.setStyleSheet(radio_style)
            tars_radio_2.setStyleSheet(radio_style)
            
            button_group_1.addButton(tars_radio_1)
            button_group_2.addButton(tars_radio_2)
            
            category_layout_1.addWidget(tars_radio_1, alignment=Qt.AlignCenter)
            category_layout_2.addWidget(tars_radio_2, alignment=Qt.AlignCenter)
            
            # Create HUMAN radio buttons for both tabs
            human_radio_1 = QRadioButton("HUMAN")
            human_radio_2 = QRadioButton("HUMAN")
            
            human_radio_1.setStyleSheet(radio_style)
            human_radio_2.setStyleSheet(radio_style)
            
            button_group_1.addButton(human_radio_1)
            button_group_2.addButton(human_radio_2)
            
            category_layout_1.addWidget(human_radio_1, alignment=Qt.AlignCenter)
            category_layout_2.addWidget(human_radio_2, alignment=Qt.AlignCenter)
            
            # Store references to all radio buttons
            self.category_radio_buttons[category] = {
                "TARS_1": tars_radio_1,
                "HUMAN_1": human_radio_1,
                "TARS_2": tars_radio_2,
                "HUMAN_2": human_radio_2,
                "button_group_1": button_group_1,
                "button_group_2": button_group_2
            }
            
            # Connect signals with synchronization
            # When tab 1 TARS is toggled, sync to tab 2 and allocate
            tars_radio_1.toggled.connect(
                lambda checked, cat=category, performer="TARS", other=tars_radio_2: 
                self._on_category_radio_toggled_with_sync(cat, performer, checked, other))
            
            # When tab 2 TARS is toggled, sync to tab 1 and allocate
            tars_radio_2.toggled.connect(
                lambda checked, cat=category, performer="TARS", other=tars_radio_1: 
                self._on_category_radio_toggled_with_sync(cat, performer, checked, other))
            
            # When tab 1 HUMAN is toggled, sync to tab 2 and allocate
            human_radio_1.toggled.connect(
                lambda checked, cat=category, performer="HUMAN", other=human_radio_2: 
                self._on_category_radio_toggled_with_sync(cat, performer, checked, other))
            
            # When tab 2 HUMAN is toggled, sync to tab 1 and allocate
            human_radio_2.toggled.connect(
                lambda checked, cat=category, performer="HUMAN", other=human_radio_1: 
                self._on_category_radio_toggled_with_sync(cat, performer, checked, other))
            
            # Add the category layouts to both containers
            container_1.addLayout(category_layout_1)
            container_2.addLayout(category_layout_2)
        
        # Add stretches at the end to push everything to the left
        container_1.addStretch()
        container_2.addStretch()
    
    def _on_category_radio_toggled_with_sync(self, category, performer, checked, other_radio):
        """Handle radio button toggle with synchronization between tabs"""
        if not checked:
            return
        
        # Block signals on the other radio button to prevent infinite loop
        other_radio.blockSignals(True)
        other_radio.setChecked(True)
        other_radio.blockSignals(False)
        
        # Now perform the allocation
        self._on_category_radio_toggled(category, performer, checked)
    
    def _on_category_filter_clicked(self, category, clicked_button, other_button):
        """Handle category filter button click (apply filter and show clear button)"""
        # Check if this category is already filtered
        if self.active_filter_category == category:
            # Do nothing - already filtered, user should use clear button
            return
        
        # Apply the filter
        self.active_filter_category = category
        
        # Reset all other filter buttons first
        for cat, buttons in self.category_filter_buttons.items():
            self._reset_filter_button_style(buttons["button_1"])
            self._reset_filter_button_style(buttons["button_2"])
        
        # Highlight the active filter buttons
        self._set_filter_button_active_style(clicked_button)
        self._set_filter_button_active_style(other_button)
        
        # Apply filter to both graphs
        if self.normal_interdependence_scene:
            self.normal_interdependence_scene.filter_by_category(category)
        if self.contingency_interdependence_scene:
            self.contingency_interdependence_scene.filter_by_category(category)
        
        # Show the clear filter buttons
        self._show_clear_filter_buttons()
        
        #print(f"Applied filter for category: {category}")
    
    def _show_clear_filter_buttons(self):
        """Show clear filter buttons in both tabs"""
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import Qt
        
        # Get both container layouts
        container_1 = self.widgets.task_type_button_container
        container_2 = self.widgets.task_type_button_container_2
        
        # Remove existing clear buttons if they exist
        if self.clear_filter_button_1:
            container_1.removeWidget(self.clear_filter_button_1)
            self.clear_filter_button_1.deleteLater()
            self.clear_filter_button_1 = None
        
        if self.clear_filter_button_2:
            container_2.removeWidget(self.clear_filter_button_2)
            self.clear_filter_button_2.deleteLater()
            self.clear_filter_button_2 = None
        
        # Create clear filter buttons
        self.clear_filter_button_1 = QPushButton("✕ Clear Filter")
        self.clear_filter_button_2 = QPushButton("✕ Clear Filter")
        
        clear_button_style = """
            QPushButton {
                font: 700 11pt "JetBrains Mono";
                color: white;
                padding: 8px 12px;
                background-color: rgba(220, 53, 69, 200);
                border: 2px solid rgba(220, 53, 69, 255);
                border-radius: 5px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: rgba(200, 35, 51, 230);
                border: 2px solid rgba(255, 70, 85, 255);
            }
            QPushButton:pressed {
                background-color: rgba(180, 25, 41, 255);
            }
        """
        
        self.clear_filter_button_1.setStyleSheet(clear_button_style)
        self.clear_filter_button_2.setStyleSheet(clear_button_style)
        
        self.clear_filter_button_1.setCursor(Qt.PointingHandCursor)
        self.clear_filter_button_2.setCursor(Qt.PointingHandCursor)
        
        # Connect both buttons to clear the filter (synchronized)
        self.clear_filter_button_1.clicked.connect(self._clear_category_filter)
        self.clear_filter_button_2.clicked.connect(self._clear_category_filter)
        
        # Insert the clear buttons at the end (before the stretch)
        # Remove the stretch temporarily
        stretch_1 = container_1.takeAt(container_1.count() - 1)
        stretch_2 = container_2.takeAt(container_2.count() - 1)
        
        # Add clear buttons
        container_1.addWidget(self.clear_filter_button_1)
        container_2.addWidget(self.clear_filter_button_2)
        
        # Re-add stretches
        if stretch_1:
            container_1.addItem(stretch_1)
        if stretch_2:
            container_2.addItem(stretch_2)
    
    def _clear_category_filter(self):
        """Clear the active category filter"""
        if not self.active_filter_category:
            return
        
        # Clear the filter state
        self.active_filter_category = None
        
        # Reset all filter button styles
        for cat, buttons in self.category_filter_buttons.items():
            self._reset_filter_button_style(buttons["button_1"])
            self._reset_filter_button_style(buttons["button_2"])
        
        # Clear filters on both graphs
        if self.normal_interdependence_scene:
            self.normal_interdependence_scene.clear_category_filter()
        if self.contingency_interdependence_scene:
            self.contingency_interdependence_scene.clear_category_filter()
        
        # Hide the clear filter buttons
        self._hide_clear_filter_buttons()
        
        #print("Cleared category filter")
    
    def _hide_clear_filter_buttons(self):
        """Hide and remove clear filter buttons from both tabs"""
        container_1 = self.widgets.task_type_button_container
        container_2 = self.widgets.task_type_button_container_2
        
        if self.clear_filter_button_1:
            container_1.removeWidget(self.clear_filter_button_1)
            self.clear_filter_button_1.deleteLater()
            self.clear_filter_button_1 = None
        
        if self.clear_filter_button_2:
            container_2.removeWidget(self.clear_filter_button_2)
            self.clear_filter_button_2.deleteLater()
            self.clear_filter_button_2 = None
    
    def _reset_filter_button_style(self, button):
        """Reset filter button to normal (non-active) style"""
        button.setStyleSheet("""
            QPushButton {
                font: 600 12pt "JetBrains Mono";
                color: white;
                padding: 5px;
                background-color: transparent;
                border: 2px solid transparent;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border: 2px solid rgba(255, 255, 255, 0.3);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """)
    
    def _set_filter_button_active_style(self, button):
        """Set filter button to active (filtered) style"""
        button.setStyleSheet("""
            QPushButton {
                font: 600 12pt "JetBrains Mono";
                color: black;
                padding: 5px;
                background-color: rgba(0, 168, 120, 255);
                border: 2px solid rgba(0, 200, 150, 255);
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: rgba(0, 150, 108, 255);
                border: 2px solid rgba(0, 180, 135, 255);
            }
            QPushButton:pressed {
                background-color: rgba(0, 134, 96, 255);
            }
        """)
    
    def _on_category_radio_toggled(self, category, performer, checked):
        """Handle radio button toggle for category-based allocation"""
        if not checked:
            return
        
        #print(f"Allocating all '{category}' tasks to {performer}")
        
        # Allocate normal tasks in this category
        if self.normal_interdependence_scene and self.normal_tasks:
            for task_id, task in enumerate(self.normal_tasks):
                if task.category == category:
                    # Check if this performer can perform the task
                    if performer == "HUMAN" and task.human_can:
                        self.normal_interdependence_scene.on_node_clicked(task_id, performer)
                    elif performer == "TARS" and task.agent_can:
                        self.normal_interdependence_scene.on_node_clicked(task_id, performer)
        
        # Allocate contingency tasks in this category
        if self.contingency_interdependence_scene and self.contingency_tasks:
            for task_id, task in enumerate(self.contingency_tasks):
                if task.category == category:
                    # Check if this performer can perform the task
                    if performer == "HUMAN" and task.human_can:
                        self.contingency_interdependence_scene.on_node_clicked(task_id, performer)
                    elif performer == "TARS" and task.agent_can:
                        self.contingency_interdependence_scene.on_node_clicked(task_id, performer)
    
    def connect_briefing_signals(self):
        """
        Connect signals specific to the briefing page
        """
        # Connect validate briefing button (normal operations)
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
        
        # Connect export briefing buttons (both tabs)
        try:
            if hasattr(self.widgets, 'export_briefing_button'):
                self.widgets.export_briefing_button.clicked.connect(self.export_briefing)
                self.widgets.export_briefing_button.setEnabled(False)  # Initially disabled
                #print("Connected export briefing button (Normal Operations)")
            else:
                print("Warning: export_briefing_button not found in UI")
        except Exception as e:
            print(f"Error connecting export briefing button: {e}")
        
        try:
            if hasattr(self.widgets, 'export_briefing_button_2'):
                self.widgets.export_briefing_button_2.clicked.connect(self.export_briefing)
                self.widgets.export_briefing_button_2.setEnabled(False)  # Initially disabled
                #print("Connected export briefing button (Contingency Planning)")
            else:
                print("Warning: export_briefing_button_2 not found in UI")
        except Exception as e:
            print(f"Error connecting export briefing button 2: {e}")
        
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
        
        # Connect send to agent buttons (NEW - separate from export)
        try:
            if hasattr(self.widgets, 'send_briefing_button'):
                self.widgets.send_briefing_button.clicked.connect(self.send_allocation_to_agent)
                self.widgets.send_briefing_button.setEnabled(False)  # Initially disabled
                #print("Connected send briefing button (Normal Operations)")
            else:
                print("Warning: send_briefing_button not found in UI")
        except Exception as e:
            print(f"Error connecting send briefing button: {e}")
        
        try:
            if hasattr(self.widgets, 'send_briefing_button_2'):
                self.widgets.send_briefing_button_2.clicked.connect(self.send_allocation_to_agent)
                self.widgets.send_briefing_button_2.setEnabled(False)  # Initially disabled
                #print("Connected send briefing button 2 (Contingency Planning)")
            else:
                print("Warning: send_briefing_button_2 not found in UI")
        except Exception as e:
            print(f"Error connecting send briefing button 2: {e}")
        
        # Example: Connect other buttons, input fields, etc.
        # self.widgets.briefing.btn_start_mission.clicked.connect(self.start_mission)
        # self.widgets.briefing.btn_load_briefing.clicked.connect(self.load_briefing_file)
        
    # Validation methods
    def toggle_normal_validation_state(self):
        """
        Toggle between validation and reset states for normal operations
        """
        # Only allow toggle if all normal tasks are assigned    
        if not self.all_normal_tasks_assigned and not self.normal_validation_active:
            print("Cannot validate normal operations: Not all tasks have been assigned performers")
            return
            
        if not self.normal_validation_active:
            # Currently in normal state, validate the briefing
            self.validate_briefing()
            self._set_normal_button_to_reset_state()
            self.normal_validation_active = True
            
            # Switch to contingency planning tab to remind user
            if hasattr(self.widgets, 'tabWidget'):
                self.widgets.tabWidget.setCurrentIndex(1)  # Index 1 is contingency planning tab
                #print("Switched to Contingency Planning tab")
            
            # Check if both are validated and enable export button if so
            self._update_export_button_state()
        else:
            # Currently in validated state, reset the validation
            self.reset_normal_validation()
            self._set_normal_button_to_validate_state()
            self.normal_validation_active = False
            
            # Update export button state
            self._update_export_button_state()
    
    def toggle_contingency_validation_state(self):
        """
        Toggle between validation and reset states for contingency planning
        """
        # Only allow toggle if all contingency tasks are assigned    
        if not self.all_contingency_tasks_assigned and not self.contingency_validation_active:
            print("Cannot validate contingency planning: Not all tasks have been assigned performers")
            return
            
        if not self.contingency_validation_active:
            # Currently in normal state, validate the contingency planning
            self.validate_contingency_planning()
            self._set_contingency_button_to_reset_state()
            self.contingency_validation_active = True
            
            # Check if both are validated and enable export button if so
            self._update_export_button_state()
        else:
            # Currently in validated state, reset the validation
            self.reset_contingency_validation()
            self._set_contingency_button_to_validate_state()
            self.contingency_validation_active = False
            
            # Update export button state
            self._update_export_button_state()
    
    def _update_export_button_state(self):
        """Enable/disable export and send buttons based on validation state"""
        both_validated = self.normal_validation_active and self.contingency_validation_active
        
        # Update export button 1 (Normal Operations tab)
        if hasattr(self.widgets, 'export_briefing_button'):
            self.widgets.export_briefing_button.setEnabled(both_validated)
            if both_validated:
                self._set_export_button_enabled_style(self.widgets.export_briefing_button)
            else:
                self._set_export_button_disabled_style(self.widgets.export_briefing_button)
        
        # Update export button 2 (Contingency Planning tab)
        if hasattr(self.widgets, 'export_briefing_button_2'):
            self.widgets.export_briefing_button_2.setEnabled(both_validated)
            if both_validated:
                self._set_export_button_enabled_style(self.widgets.export_briefing_button_2)
            else:
                self._set_export_button_disabled_style(self.widgets.export_briefing_button_2)
        
        # Update send to agent button 1 (Normal Operations tab)
        if hasattr(self.widgets, 'send_briefing_button'):
            self.widgets.send_briefing_button.setEnabled(both_validated)
            if both_validated:
                self._set_send_button_enabled_style(self.widgets.send_briefing_button)
            else:
                self._set_send_button_disabled_style(self.widgets.send_briefing_button)
        
        # Update send to agent button 2 (Contingency Planning tab)
        if hasattr(self.widgets, 'send_briefing_button_2'):
            self.widgets.send_briefing_button_2.setEnabled(both_validated)
            if both_validated:
                self._set_send_button_enabled_style(self.widgets.send_briefing_button_2)
            else:
                self._set_send_button_disabled_style(self.widgets.send_briefing_button_2)
        
        if both_validated:
            # Store the validated allocation data
            self._store_validated_allocation()
            #print("Both briefings validated - Export and Send buttons enabled")
        else:
            print("Export and Send buttons disabled - both briefings must be validated")
    
    def _set_export_button_enabled_style(self, button):
        """Set orange background style for enabled export button"""
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
    
    def _set_export_button_disabled_style(self, button):
        """Set gray style for disabled export button"""
        button.setStyleSheet("""
            QPushButton {
                border: 2px solid rgba(128, 128, 128, 255) !important;
                border-radius: 5px !important;
                background-color: rgba(100, 100, 100, 255) !important;
                font: 600 16pt "JetBrains Mono" !important;
                color: rgba(255, 255, 255, 120) !important;
            }
            QPushButton:disabled {
                border: 2px solid rgba(100, 100, 100, 255) !important;
                background-color: rgba(80, 80, 80, 255) !important;
            }
        """)
    
    def _set_send_button_enabled_style(self, button):
        """Set green/cyan background style for enabled send button (distinct from export)"""
        button.setStyleSheet("""
            QPushButton {
                border: 2px solid rgba(0, 200, 150, 255) !important;
                border-radius: 5px !important;
                background-color: rgba(0, 200, 150, 255) !important;
                font: 600 16pt "JetBrains Mono" !important;
                color: white !important;
            }
            QPushButton:hover {
                background-color: rgba(0, 220, 170, 255) !important;
                border-color: rgba(0, 220, 170, 255) !important;
            }
            QPushButton:pressed {
                background-color: rgba(0, 180, 130, 255) !important;
                border-color: rgba(0, 180, 130, 255) !important;
            }
        """)
    
    def _set_send_button_disabled_style(self, button):
        """Set gray style for disabled send button"""
        button.setStyleSheet("""
            QPushButton {
                border: 2px solid rgba(128, 128, 128, 255) !important;
                border-radius: 5px !important;
                background-color: rgba(100, 100, 100, 255) !important;
                font: 600 16pt "JetBrains Mono" !important;
                color: rgba(255, 255, 255, 120) !important;
            }
            QPushButton:disabled {
                border: 2px solid rgba(100, 100, 100, 255) !important;
                background-color: rgba(80, 80, 80, 255) !important;
            }
        """)
    
    def _store_validated_allocation(self):
        """Store the validated allocation data at app level for use by other pages"""
        # Create export data list
        export_data = []
        
        # Get selections for both normal and contingency tasks
        normal_selections = self.get_selected_performers()
        contingency_selections = self.get_contingency_selected_performers()
        
        # Process ALL tasks in original order
        for i, task in enumerate(self.all_tasks):
            # Determine which selection dictionary to use based on task classification
            if task.classification == 'NORM':
                # Find the task index in normal_tasks list
                try:
                    normal_task_index = self.normal_tasks.index(task)
                    if normal_task_index in normal_selections:
                        performer = normal_selections[normal_task_index]
                    else:
                        continue  # Skip tasks without selection
                except ValueError:
                    continue  # Task not found in normal_tasks
            elif task.classification in ['EMER', 'ABNORM']:
                # Find the task index in contingency_tasks list
                try:
                    contingency_task_index = self.contingency_tasks.index(task)
                    if contingency_task_index in contingency_selections:
                        performer = contingency_selections[contingency_task_index]
                    else:
                        continue  # Skip tasks without selection
                except ValueError:
                    continue  # Task not found in contingency_tasks
            else:
                continue  # Skip unknown classification
            
            # Determine roles based on performer selection and task capabilities
            if performer == "HUMAN":
                human_role = "performer"
                # Only assign autonomy as supporter if the task supports it
                autonomy_role = "supporter" if task.agent_supports else ""
            else:  # performer == "TARS"
                autonomy_role = "performer"
                # Only assign human as supporter if the task supports it
                human_role = "supporter" if task.human_supports else ""
            
            # Build export row with all original CSV columns preserved
            export_row = {
                'procedure': task.procedure_name,
                'classification': task.classification,
                'type': task.task_type,
                'category': task.category,
                'task_object': task.name,
                'value': task.value,
                'human_role': human_role,
                'autonomy_role': autonomy_role
            }
            
            # Add all extra fields from the original CSV
            if hasattr(task, 'extra_fields'):
                export_row.update(task.extra_fields)
            
            export_data.append(export_row)
        
        # Store at app level (accessible to main_window and other pages)
        self.validated_allocation_data = export_data
        self.main_window.briefing_allocation_data = export_data
        
        #print(f"Stored validated allocation data: {len(export_data)} task assignments")
        #print(f"  - Processed in original chronological order")
    
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
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        import csv
        from pathlib import Path
        from datetime import datetime
        
        # Check if we have validated data
        if not self.validated_allocation_data:
            QMessageBox.warning(None, "No Data to Export", 
                              "Please validate both Normal Operations and Contingency Planning briefings before exporting.")
            return
        
        # Open file dialog to choose export location
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"briefing_export_{timestamp}.csv"
        
        file_path, _ = QFileDialog.getSaveFileName(
            None,
            "Export Briefing Allocation",
            str(Path.home() / default_filename),
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if not file_path:
            print("Export cancelled by user")
            return
        
        # Write to CSV
        try:
            # Define the field order - standard fields first, then extra fields
            standard_fields = [
                'Procedure', 'Classification', 'Type', 'Category', 'Task Object', 
                'Value', 'Human Role', 'Autonomy Role'
            ]
            
            extra_fields = [
                'Information Requirement', 'Constraint Type', 'Time constraint (in s)',
                'Execution Type', 'interaction', 'Time to Initiate Action', 
                'Time after Ending Action', 'Callout'
            ]
            
            all_fieldnames = standard_fields + extra_fields
            
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=all_fieldnames)
                
                # Write header
                writer.writeheader()
                
                # Write data
                for row in self.validated_allocation_data:
                    # Map internal field names to CSV column names
                    output_row = {
                        'Procedure': row.get('procedure', ''),
                        'Classification': row.get('classification', ''),
                        'Type': row.get('type', ''),
                        'Category': row.get('category', ''),
                        'Task Object': row.get('task_object', ''),
                        'Value': row.get('value', ''),
                        'Human Role': row.get('human_role', ''),
                        'Autonomy Role': row.get('autonomy_role', ''),
                        'Information Requirement': row.get('information_requirement', ''),
                        'Constraint Type': row.get('constraint_type', ''),
                        'Time constraint (in s)': row.get('time_constraint', ''),
                        'Execution Type': row.get('execution_type', ''),
                        'interaction': row.get('interaction', ''),
                        'Time to Initiate Action': row.get('time_to_initiate_action', ''),
                        'Time after Ending Action': row.get('time_after_ending_action', ''),
                        'Callout': row.get('callout', ''),
                    }
                    writer.writerow(output_row)
            
            QMessageBox.information(None, "Export Successful", 
                                  f"Briefing exported successfully to:\n{file_path}\n\n"
                                  f"Total task assignments: {len(self.validated_allocation_data)}\n\n"
                                  f"File saved. Use 'Send to Agent' button to apply changes.")
            
            print(f"Briefing exported successfully to: {file_path}")
            print(f"Exported {len(self.validated_allocation_data)} task assignments")
            
        except Exception as e:
            print(f"Error exporting briefing: {e}")
            QMessageBox.critical(None, "Export Error", 
                               f"An error occurred while exporting the briefing:\n{str(e)}")

    def send_allocation_to_agent(self):
        """Send validated allocation directly to agent without exporting to file
        
        This method updates the agent's role allocations in real-time based on 
        the current validated briefing data, without saving to disk.
        """
        from PySide6.QtWidgets import QMessageBox
        
        # Check if we have validated allocation data
        if not self.validated_allocation_data:
            QMessageBox.warning(None, "No Allocation Data", 
                              "Please validate the briefing before sending to agent.\n\n"
                              "Click 'Validate Briefing' and 'Validate Contingency Plan' first.")
            return
        
        # Check if both normal and contingency are validated
        if not (self.normal_validation_active and self.contingency_validation_active):
            QMessageBox.warning(None, "Incomplete Validation", 
                              "Both Normal Operations and Contingency Planning must be validated.\n\n"
                              f"Normal Operations: {'✓ Validated' if self.normal_validation_active else '✗ Not validated'}\n"
                              f"Contingency Planning: {'✓ Validated' if self.contingency_validation_active else '✗ Not validated'}")
            return
        
        try:
            # Check if agent is available
            if not hasattr(self.main_window, 'agent'):
                QMessageBox.critical(None, "Agent Not Available", 
                                   "Cannot send allocation: Agent is not initialized.")
                return
            
            # Create temporary allocation data structure for agent
            # The agent expects a dictionary with state keys mapped to roles
            allocation_for_agent = {}
            
            for row_data in self.validated_allocation_data:
                procedure = row_data.get('procedure', '').strip()
                task_object = row_data.get('task_object', '').strip()
                value = row_data.get('value', '').strip()
                human_role = row_data.get('human_role', '').strip()
                autonomy_role = row_data.get('autonomy_role', '').strip()
                
                if procedure and task_object:
                    state_key = (procedure, task_object, value)
                    allocation_for_agent[state_key] = {
                        'human_role': human_role,
                        'autonomy_role': autonomy_role
                    }
            
            # Update agent states directly
            updated_count = 0
            for state_key, roles in allocation_for_agent.items():
                if state_key in self.main_window.agent.states:
                    state = self.main_window.agent.states[state_key]
                    
                    # Check if roles changed
                    old_human = state.human_role
                    old_autonomy = state.autonomy_role
                    new_human = roles['human_role']
                    new_autonomy = roles['autonomy_role']
                    
                    if old_human != new_human or old_autonomy != new_autonomy:
                        state.human_role = new_human
                        state.autonomy_role = new_autonomy
                        updated_count += 1
                        #print(f"Updated {state_key}: H={old_human}→{new_human}, A={old_autonomy}→{new_autonomy}")
            
            # Show success message
            QMessageBox.information(None, "Allocation Sent to Agent", 
                                  f"Successfully updated agent with current allocation:\n\n"
                                  f"• Total tasks: {len(self.validated_allocation_data)}\n"
                                  f"• States updated: {updated_count}\n\n"
                                  f"The agent is now using the validated role assignments.")
            
            # Emit signal so UI (HomePage) can refresh timeline display
            try:
                if hasattr(self.main_window, 'allocation_sent_signal'):
                    self.main_window.allocation_sent_signal.emit()
            except Exception:
                pass

            #print(f"Sent allocation to agent: {updated_count} states updated from {len(self.validated_allocation_data)} tasks")
            
        except Exception as e:
            print(f"Error sending allocation to agent: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(None, "Error Sending to Agent", 
                               f"An error occurred while sending allocation to agent:\n{str(e)}")

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
                expected_headers = ['Procedure', 'Classification', 'Type', 'Task Object', 'Value', 'Human Role', 'Autonomy Role']
                if not all(header in reader.fieldnames for header in expected_headers):
                    QMessageBox.warning(None, "Invalid File Format", 
                                      f"The selected CSV file does not have the expected format.\n"
                                      f"Expected headers: {', '.join(expected_headers)}")
                    return

                # Parse allocation data and separate by classification
                for row in reader:
                    procedure = row['Procedure'].strip()
                    classification = row['Classification'].strip()
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

                    # Store allocation data based on classification
                    allocation_key = (procedure, task_object, value)

                    if classification == "NORM":
                        normal_allocation_data[allocation_key] = performer
                    elif classification in ["EMER", "ABNORM"]:
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
                                  f"• Total: {total_applied} task allocations\n\n"
                                  f"Click 'Send to Agent' to update the agent with these allocations.")
                
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
            
            # Apply gray styling (no checkmark icon)
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid rgba(128, 128, 128, 255) !important;
                    border-radius: 5px !important;
                    background-color: rgba(100, 100, 100, 255) !important;
                    font: 600 16pt "JetBrains Mono" !important;
                    color: white !important;
                }
                QPushButton:hover {
                    background-color: rgba(120, 120, 120, 255) !important;
                    border-color: rgba(140, 140, 140, 255) !important;
                }
                QPushButton:pressed {
                    background-color: rgba(80, 80, 80, 255) !important;
                    border-color: rgba(100, 100, 100, 255) !important;
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
            
            # Apply gray styling (no checkmark icon)
            button.setStyleSheet("""
                QPushButton {
                    border: 2px solid rgba(128, 128, 128, 255) !important;
                    border-radius: 5px !important;
                    background-color: rgba(100, 100, 100, 255) !important;
                    font: 600 16pt "JetBrains Mono" !important;
                    color: white !important;
                }
                QPushButton:hover {
                    background-color: rgba(120, 120, 120, 255) !important;
                    border-color: rgba(140, 140, 140, 255) !important;
                }
                QPushButton:pressed {
                    background-color: rgba(80, 80, 80, 255) !important;
                    border-color: rgba(100, 100, 100, 255) !important;
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