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
    QGraphicsPathItem, QGraphicsSimpleTextItem
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
    def __init__(self, name, human_can, agent_can, human_supports, agent_supports):
        self.name = name
        self.human_can = bool(int(human_can)) if str(human_can).strip() != "" else False
        self.agent_can = bool(int(agent_can)) if str(agent_can).strip() != "" else False
        self.human_supports = bool(int(human_supports)) if str(human_supports).strip() != "" else False
        self.agent_supports = bool(int(agent_supports)) if str(agent_supports).strip() != "" else False

def load_tasks(csv_path: Path = None):
    """Load tasks from CSV or return demo data"""
    if csv_path and csv_path.exists():
        tasks = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tasks.append(Task(
                    row.get("task","").strip(),
                    row.get("human_can","0"),
                    row.get("agent_can","0"),
                    row.get("human_supports","0"),
                    row.get("agent_supports","0"),
                ))
        return tasks

    # Hardcoded demo data for normal operations
    demo = [
        ("Confirm takeoff clearance", 1, 0, 0, 0),
        ("Align with runway centerline", 1, 1, 0, 0),
        ("Check winds", 1, 1, 0, 1),
        ("Hold brakes", 1, 1, 0, 0),
        ("Advance thrust", 0, 1, 0, 0),
        ("Airspeed alive callout", 1, 1, 0, 0),
        ("80 knots cross-check", 1, 1, 1, 0),
        ("Rotate", 1, 0, 0, 0),
        ("Positive rate", 1, 1, 0, 0),
        ("Gear up", 1, 1, 0, 1),
    ]
    return [Task(*t) for t in demo]

# ---------------------------- Scene items ----------------------------

class ClickNode(QGraphicsEllipseItem):
    """Clickable node for performer selection"""
    
    def __init__(self, row: int, role: str, center: QPointF, radius: float, scene_parent):
        super().__init__(0, 0, radius*2, radius*2)
        self.setPos(center - QPointF(radius, radius))
        self.setBrush(QBrush(Qt.yellow))
        self.setPen(QPen(Qt.black, 1.2))
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
            # Highlight selected nodes
            self.setBrush(QBrush(Qt.green))
            self.setPen(QPen(Qt.darkGreen, 2.0))
        else:
            # Default appearance
            self.setBrush(QBrush(Qt.yellow))
            self.setPen(QPen(Qt.black, 1.2))

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
    def __init__(self, tasks: list[Task], parent=None):
        super().__init__(parent)
        self.tasks = tasks

        # Layout constants
        self.margin_left = 350
        self.margin_right = 10
        self.margin_top = 160
        self.row_h = 100
        self.col_x = {
            "HUMAN": 380,
            "TARS": 820
        }
        self.node_r = 10

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

    def _build_static(self):
        """Build static elements (title, headers, labels)"""
        # Title
        title = QGraphicsSimpleTextItem("NORMAL Operation Briefing and task allocation")
        f = QFont()
        f.setPointSize(20)
        #f.setBold(True)
        title.setFont(f)
        title.setBrush(QBrush(QColor("#ffffff")))  # Set the font color here
        title.setPos(self.margin_left, 20)
        self.addItem(title)

        # Column headers
        for col, x in self.col_x.items():
            h = QGraphicsSimpleTextItem(col)
            hf = QFont()
            hf.setPointSize(16)
            #hf.setBold(True)
            h.setFont(hf)
            h.setPos(x - 30, self.margin_top - 60)
            h.setBrush(QBrush(QColor("#ffffff")))  # Set the font color here
            self.addItem(h)

        # Task labels and row guide lines
        for i, t in enumerate(self.tasks):
            y = self._row_y(i)
            label = QGraphicsSimpleTextItem(t.name)
            lf = QFont()
            lf.setPointSize(14)
            label.setFont(lf)
            label.setPos(20, y - 10)
            label.setBrush(QBrush(QColor("#ffffff")))  # Set the font color here
            self.addItem(label)

            # faint row line
            pen = QPen(Qt.lightGray, 0.8, Qt.DotLine)
            self.addLine(self.margin_left-80, y, self.col_x["TARS"]+200, y, pen)

        # Scene rect adjusted to fit actual content bounds
        content_left = 0  # Where task labels start
        content_right = self.col_x["TARS"] + 100  # Add padding after TARS column
        content_top = 20   # Where title starts
        height = self._row_y(len(self.tasks)-1) + 120
        width = content_right - content_left
        
        self.setSceneRect(content_left, content_top, width, height)

    def _build_nodes_and_supporters(self):
        """Build clickable performer nodes and supporter rectangles"""
        for row, t in enumerate(self.tasks):
            y = self._row_y(row)

            # HUMAN performer
            if t.human_can:
                node = ClickNode(row, "HUMAN", QPointF(self.col_x["HUMAN"], y), self.node_r, self)
                self.addItem(node)
                self.nodes[(row, "HUMAN")] = node  # Store reference
                # supporter marker & dashed line
                if t.human_supports:
                    sup = SupportNode(QPointF(self.col_x["TARS"], y))
                    self.addItem(sup)
                    self._add_dashed(self.col_x["HUMAN"], self.col_x["TARS"], y)

            # TARS performer
            if t.agent_can:
                node = ClickNode(row, "TARS", QPointF(self.col_x["TARS"], y), self.node_r, self)
                self.addItem(node)
                self.nodes[(row, "TARS")] = node  # Store reference
                if t.agent_supports:
                    sup = SupportNode(QPointF(self.col_x["HUMAN"], y))
                    self.addItem(sup)
                    self._add_dashed(self.col_x["TARS"], self.col_x["HUMAN"], y)

    def _add_dashed(self, x1, x2, y):
        """Add dashed support line"""
        pen = QPen(Qt.darkGreen, 1.4, Qt.DashLine)
        line = self.addLine(x1, y, x2, y, pen)
        line.setZValue(1)
        self.dashed_items.append(line)

    def _row_y(self, row: int) -> float:
        """Get Y coordinate for row"""
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
        
        # Update connecting paths
        self._update_path()
        print(f"Selected {role} for task {row}: {self.tasks[row].name}")
        
        # If selection changed, log it
        if old_selection != role:
            print(f"  Changed from {old_selection} to {role}")
        else:
            print(f"  Confirmed selection: {role}")

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
            self.tasks = load_tasks()
            
            # Create and setup the interdependence scene
            self.interdependence_scene = InterdependenceScene(self.tasks)
            
            # Connect the scene to the QGraphicsView widget
            if hasattr(self.widgets, 'normal_operation_ia_graph'):
                self.widgets.normal_operation_ia_graph.setScene(self.interdependence_scene)
                # Enable mouse interaction
                self.widgets.normal_operation_ia_graph.setDragMode(QGraphicsView.RubberBandDrag)
                self.widgets.normal_operation_ia_graph.setRenderHint(QPainter.Antialiasing, True)
                
                # Fit the scene content in the view to eliminate shifting
                self.widgets.normal_operation_ia_graph.fitInView(
                    self.interdependence_scene.sceneRect(), 
                    Qt.KeepAspectRatio
                )
                
                print("Interdependence analysis setup completed")
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
        # Example: Connect buttons, input fields, etc.
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