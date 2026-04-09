"""
Home Page
Main landing page for the TARS GUI application
"""

# Set to True to show ALL procedures (NORM + EMER + ABNORM) from startup.
# Set to False to only show NORM procedures initially; EMER/ABNORM tabs
# will be injected dynamically as they are triggered during the scenario.
SHOW_ALL_PROCEDURES = True

from operator import index
from tabnanny import check
from pages.task_page_base import TaskPageBase
from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget, QVBoxLayout
import warnings
from widgets.circular_countdown import CircularCountdown
from widgets.task_timeline import TaskTimelineWidget
from pathlib import Path
from typing import TYPE_CHECKING

# Import for type hints only (prevents circular imports)
if TYPE_CHECKING:
    from modules.ui_main import Ui_MainWindow
    from main import MainWindow

class HomePage(TaskPageBase):
    def set_checklist_label_current(self, procedure_name, task_object, value):
        """Set the checklist button to 'current' (grey box) and scroll to it if needed"""
        button = self.checklist_item_labels.get(procedure_name, {}).get((task_object, value))
        if button:
            button.setStyleSheet("""
                QPushButton {
                    font: 600 12pt 'OCR A';
                    color: white;
                    text-align: left;
                    border: 2px solid #888888;
                    border-radius: 8px;
                    padding: 4px;
                    background-color: transparent;
                }
                QPushButton:hover {
                    background-color: rgba(85, 170, 255, 30);
                }
                QPushButton:pressed {
                    background-color: rgba(85, 170, 255, 50);
                }
            """)
            
            # Auto-scroll to make the current button visible
            scroll_area = self.checklist_scroll_areas.get(procedure_name)
            if scroll_area:
                # Ensure the button is visible in the scroll area
                scroll_area.ensureWidgetVisible(button, 50, 50)

    def set_checklist_label_passed(self, procedure_name, task_object, value, autonomy_role=None):
        """Set the checklist button to 'passed' (blue for TARS/performer, green for human)"""
        button = self.checklist_item_labels.get(procedure_name, {}).get((task_object, value))
        if not button:
            return  # or handle the missing button case appropriately
        target = task_object
        button_text = button.text() if button else ""
        index = button_text.find(target)
        # Only add ": " if it's not already there
        if index != -1:
            end_index = index + len(target)
            # Check if ": " is already present after the target
            if not button_text[end_index:end_index+2] == ": ":
                button_text = button_text[:end_index] + ": " + button_text[end_index:]
        #button_text = button_text.replace("-", "")
        button.setText(button_text)
        color = "#55aaff" if autonomy_role == "performer" else "#55de71"
        if button:
            button.setStyleSheet(f"""
                QPushButton {{
                    font: 600 12pt 'OCR A';
                    color: {color};
                    text-align: left;
                    border: none;
                    border-radius: 0px;
                    padding: 4px;
                    background-color: transparent;
                }}
                QPushButton:hover {{
                    background-color: rgba(85, 170, 255, 30);
                    border-radius: 5px;
                }}
                QPushButton:pressed {{
                    background-color: rgba(85, 170, 255, 50);
                }}
            """)
    """
    Home page implementation
    Contains the main dashboard and status information
    """
    
    def __init__(self, widgets: 'Ui_MainWindow', main_window: 'MainWindow'):
        """
        Initialize the home page
        
        Args:
            widgets: UI widgets object (Ui_MainWindow instance)
            main_window: Main window instance
        """
        super().__init__(widgets, main_window)
        self.page_widget = widgets.home
        
        # Set widget references for base class (home uses regular names, not _flight suffix)
        self.current_task_container = widgets.current_task_container_3
        self.interaction_panel_text = widgets.interaction_panel_text
        self.interaction_panel_tars_input = widgets.interaction_panel_tars_input
        self.int_panel_right_button = widgets.int_panel_right_button
        self.int_panel_left_button = widgets.int_panel_left_button
        self.check_radio_button = widgets.check_radio_button
        self.cancel_task_button = widgets.cancel_task_button_2
        
        # Explicitly declare widgets type for better IDE support
        self.widgets: 'Ui_MainWindow' = widgets
        self.main_window: 'MainWindow' = main_window
        
        # Create task timeline widgets - one per procedure (stored in dict)
        self.task_timeline_widgets = {}  # Dict: procedure_name -> TaskTimelineWidget
        self.current_procedure = None  # Track current active procedure
        self.discovered_procedures = set()  # Track which procedures have been revealed

        # Guard flag: True while we do programmatic tab switches so the
        # currentChanged handler does not trigger a force_state_jump.
        self._programmatic_tab_switch = False
        
        # Initialize glow effect timer (inherited from base but needs tracking here)
        # self._glow_timer, self._glow_steps, etc. already in TaskPageBase

        # Store checklist item labels for later access
        self.checklist_item_labels = {}  # Dict: procedure_name -> dict of (task_object, value) -> QLabel
        self.checklist_scroll_areas = {}  # Dict: procedure_name -> QScrollArea

        radio_style = """
        QRadioButton {
            padding: 5px 5px;
            padding-left: 10px;
            padding-right: 10px;
            border: 2px solid rgba(221,221,221,255);
            border-radius: 5px;
            background-color: rgba(33, 37, 43, 255);
            font: 600 16pt "JetBrains Mono";
            color: white;
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
        QRadioButton:checked {
            border: 2px solid #35de71;
        }
        """
    
        self.widgets.check_radio_button.setStyleSheet(radio_style)
        
        self.setup_page()
    
    def setup_page(self):
        """
        Setup home page specific functionality
        """
        # Set object name for current task container
        self.widgets.current_task_container_3.setObjectName("currentTaskContainer")
        
        # Replace text labels with circular countdown widgets
        self._setup_circular_countdowns()
        
        # Connect task buttons (from base class)
        self.connect_task_buttons()
        
        # Make previous/next task containers clickable
        self._setup_clickable_task_containers()
        
        # Apply radio button styling
        radio_style = """
        QRadioButton {
            padding: 5px 5px;
            padding-left: 10px;
            padding-right: 10px;
            border: 2px solid rgba(221,221,221,255);
            border-radius: 5px;
            background-color: rgba(33, 37, 43, 255);
            font: 600 16pt "JetBrains Mono";
            color: white;
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
        QRadioButton:checked {
            border: 2px solid #35de71;
        }
        """
        self.widgets.check_radio_button.setStyleSheet(radio_style)
        
        # Connect emergency stop button
        if hasattr(self.widgets, 'stop_button'):
            self.widgets.stop_button.clicked.connect(self.stop_all_signal.emit)

        # Setup task timeline widget
        self._setup_task_timeline()

        # Connect to allocation sent signal so timeline refreshes when allocations change
        try:
            if hasattr(self.main_window, 'allocation_sent_signal'):
                self.main_window.allocation_sent_signal.connect(self.refresh_task_timeline_data)
        except Exception:
            pass

        #print("Home page setup complete")
    
    def disconnect_int_panel_buttons(self):
        """Disconnect the interaction panel buttons from their signals"""
        # Suppress RuntimeWarning for failed disconnects
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                self.widgets.int_panel_right_button.clicked.disconnect(self.task_done_clicked)
            except Exception:
                pass
            try:
                self.widgets.int_panel_left_button.clicked.disconnect(self.task_cancel_clicked)
            except Exception:
                pass
            try:
                self.widgets.int_panel_right_button.clicked.disconnect(self.task_allowed_clicked)
            except Exception:
                pass
            try:
                self.widgets.int_panel_left_button.clicked.disconnect(self.task_not_allowed_clicked)
            except Exception:
                pass

    def connect_int_panel_buttons(self, default=True):
        """Reconnect the internal panel buttons to their signals"""
        self.disconnect_int_panel_buttons()
        if default:
            self.widgets.int_panel_right_button.clicked.connect(self.task_done_clicked)
            self.widgets.int_panel_left_button.clicked.connect(self.task_cancel_clicked)
        else:
            self.widgets.int_panel_right_button.clicked.connect(self.task_allowed_clicked)
            self.widgets.int_panel_left_button.clicked.connect(self.task_not_allowed_clicked)


    def _setup_circular_countdowns(self):
        """Replace the QLabel countdown displays with circular countdown widgets"""
        # Use base class method to setup countdown widgets
        self.setup_countdown_widgets(
            current_container=self.widgets.c_t_s_container_2,
            next_container=self.widgets.n_t_s_container_2,
            current_value_label=self.widgets.c_t_s_value_2,
            current_unit_label=self.widgets.c_t_s_unit_2,
            next_value_label=self.widgets.n_t_s_value_2,
            next_unit_label=self.widgets.n_t_s_unit_2
        )
    
    def _setup_clickable_task_containers(self):
        """Make previous and next task containers clickable for navigation"""
        # Get the containers
        previous_container = self.widgets.previous_task_container_6
        next_container = self.widgets.next_task_container_6
        
        # Install event filters
        previous_container.installEventFilter(self)
        next_container.installEventFilter(self)
        
        # Store references for event handling
        self._previous_task_container = previous_container
        self._next_task_container = next_container
        
        # Add hover cursor
        from PySide6.QtCore import Qt
        previous_container.setCursor(Qt.PointingHandCursor)
        next_container.setCursor(Qt.PointingHandCursor)
        
        print("✅ Previous/Next task containers are now clickable")
    
    def eventFilter(self, obj, event):
        """Handle events for clickable task containers"""
        from PySide6.QtCore import QEvent, Qt
        
        # Check if it's a mouse press on one of our containers
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if obj == self._previous_task_container:
                print("⬅️ Previous task container clicked")
                self.previous_step_signal.emit()
                return True
            elif obj == self._next_task_container:
                print("➡️ Next task container clicked")
                self.next_step_signal.emit()
                return True
        
        # Pass event to parent
        return super().eventFilter(obj, event)
    
    def _setup_task_timeline(self):
        """Setup the task timeline widget with tabs for each procedure"""
        # Get the tab widget from UI (stack_tab_container)
        if not hasattr(self.widgets, 'stack_tab_container'):
            print("Error: stack_tab_container not found in UI")
            return
        
        tab_widget = self.widgets.stack_tab_container
        
        # Apply styling to tab widget with rounded corners
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid rgb(52, 59, 72);
                border-radius: 10px;
                background-color: rgb(33, 37, 43);
                padding: 5px;
            }
            QTabBar::tab {
                background-color: rgb(44, 49, 60);
                color: rgb(210, 210, 210);
                border: 2px solid rgb(52, 59, 72);
                border-bottom: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                padding: 8px 16px;
                margin-right: 2px;
                font: 600 10pt "JetBrains Mono";
            }
            QTabBar::tab:selected {
                background-color: rgb(33, 37, 43);
                color: #55aaff;
                border-bottom: 2px solid rgb(33, 37, 43);
            }
            QTabBar::tab:hover {
                background-color: rgb(52, 59, 72);
            }
            QTabBar::tab[emergency="true"] {
                background-color: rgb(108, 4, 4);
                color: rgb(255, 200, 200);
                border: 2px solid rgba(235, 0, 20, 255);
            }
            QTabBar::tab[emergency="true"]:selected {
                background-color: rgb(150, 10, 10);
                color: #ff6666;
            }
        """)
        
        # Clear any existing tabs
        tab_widget.clear()
        self.task_timeline_widgets.clear()
        self.discovered_procedures = set()
        self.current_procedure = None
        
        # Load tasks directly from agent (single source of truth)
        if not (hasattr(self.main_window, 'agent') and self.main_window.agent):
            print("Warning: Agent not available, TaskTimeline will be empty")
            return
        
        agent = self.main_window.agent
        
        # Extract unique procedures from agent states (in order of appearance)
        # Only include NORM classification procedures initially
        procedures_data = []  # List of (procedure_name, classification) tuples
        procedures_seen = []
        
        for state_key, state in agent.states.items():
            # Skip special states (IDLE, FINISHED)
            if state.procedure in ['IDLE', 'FINISHED']:
                continue
            
            # Add procedure if not seen before (maintains order)
            if state.procedure not in procedures_seen:
                procedures_seen.append(state.procedure)
                classification = getattr(state, 'classification', 'NORM')
                procedures_data.append((state.procedure, classification))
        
        # Filter: only create tabs for NORM procedures initially,
        # unless SHOW_ALL_PROCEDURES is True (debugging / full-preview mode).
        if SHOW_ALL_PROCEDURES:
            displayed_procedures = procedures_data
            print(f"SHOW_ALL_PROCEDURES=True — creating tabs for ALL procedures: {[p[0] for p in displayed_procedures]}")
        else:
            displayed_procedures = [(name, cls) for name, cls in procedures_data if cls == 'NORM']
            print(f"Creating timeline tabs for NORMAL procedures: {[p[0] for p in displayed_procedures]}")

        # Create a tab for each selected procedure
        for procedure_name, classification in displayed_procedures:
            self._create_procedure_tab(procedure_name, classification)
            self.discovered_procedures.add(procedure_name)
        
        print(f"Created {len(self.task_timeline_widgets)} normal procedure timeline tabs")

        # Connect tab change for BASELINE manual procedure switching
        tab_widget.currentChanged.connect(self._on_tab_changed_by_user)

        self._create_checklists_tabs(agent.checklists)

    def _create_procedure_tab(self, procedure_name, classification='NORM'):
        """Create a single procedure tab
        
        Args:
            procedure_name: Name of the procedure
            classification: NORM, EMER, or ABNORM
        """
        tab_widget = self.widgets.stack_tab_container
        
        # Create a new TaskTimelineWidget for this procedure with proper parent
        # IMPORTANT: Pass tab_widget as parent to prevent standalone window
        timeline_widget = TaskTimelineWidget(parent=tab_widget)
        
        # Ensure it's not set as a window (should be embedded widget only)
        timeline_widget.setWindowFlags(QtCore.Qt.Widget)
        
        # Connect task click signal to handler
        timeline_widget.task_clicked.connect(self.on_task_clicked)
        
        # Determine tab label based on classification
        tab_label = procedure_name
        
        # Add widget to tab FIRST before loading data
        # This ensures Qt properly manages the widget hierarchy
        tab_index = tab_widget.addTab(timeline_widget, tab_label)
        
        # NOW load tasks and configure the widget after it's in the tab
        timeline_widget.load_tasks_from_agent(self.main_window.agent)
        timeline_widget.set_current_procedure(procedure_name)
        
        # Store widget in dictionary
        self.task_timeline_widgets[procedure_name] = timeline_widget
        
        # Mark emergency tabs for styling
        if classification == 'EMER':
            tab_widget.tabBar().setTabData(tab_index, {'emergency': 'true'})
        
        #print(f"Created tab for {procedure_name} (classification: {classification}) at index {tab_index}")

    def _create_checklists_tabs(self, checklists):
        tab_widget = self.widgets.ecl_tab_container
        # Remove all existing tabs (first call: Qt Designer placeholders; subsequent calls: previous checklist tabs)
        while tab_widget.count() > 0:
            tab_widget.removeTab(0)
        # Reset dictionaries so stale button/scroll-area references are cleared
        self.checklist_item_labels = {}
        self.checklist_scroll_areas = {}
        from PySide6.QtWidgets import QScrollArea, QPushButton
        from PySide6.QtWidgets import QScroller
        for checklist in checklists.values():
            procedure_name = checklist[0]['procedure']
            item_labels = {}  # (task_object, value) -> QPushButton (changed from QLabel)
            # Create a container widget for the checklist items
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(14)
            for checklist_item in checklist:
                line = self.format_checklist_line(checklist_item['task_object'], checklist_item['value'])
                # Create QPushButton instead of QLabel for clickability
                item_button = QPushButton(line)
                item_button.setFlat(True)  # Flat button for minimal look
                item_button.setCursor(QtCore.Qt.PointingHandCursor)  # Show pointer cursor
                item_button.setStyleSheet("""
                    QPushButton {
                        font: 600 12pt 'OCR A';
                        color: white;
                        text-align: left;
                        border: none;
                        padding: 4px;
                        background-color: transparent;
                    }
                    QPushButton:hover {
                        background-color: rgba(85, 170, 255, 30);
                        border-radius: 5px;
                    }
                    QPushButton:pressed {
                        background-color: rgba(85, 170, 255, 50);
                    }
                """)
                
                # Store the task key with the button for later retrieval
                task_key = (checklist_item['procedure'], checklist_item['task_object'], checklist_item['value'])
                item_button.setProperty('task_key', task_key)
                
                # Connect button click to handler
                item_button.clicked.connect(lambda checked=False, key=task_key: self.on_checklist_item_clicked(key))
                
                layout.addWidget(item_button)
                key = (checklist_item['task_object'], checklist_item['value'])
                item_labels[key] = item_button  # Store button reference (not label)
            layout.addStretch(1)
            self.checklist_item_labels[procedure_name] = item_labels
            # Make scrollable area
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(container)
            # Enable touch / click-and-drag kinetic scrolling (same as speech log)
            QScroller.grabGesture(
                scroll.viewport(),
                QScroller.ScrollerGestureType.TouchGesture
            )
            self.checklist_scroll_areas[procedure_name] = scroll  # Store reference for auto-scroll
            tab_index = tab_widget.addTab(scroll, procedure_name)
        print(f"Created checklist tab with {len(checklists)} checklists at index {tab_index}")
    
    def inject_emergency_procedure(self, procedure_name):
        """Dynamically inject a procedure tab (emergency, abnormal, or any newly discovered procedure)
        
        This is called when a new procedure is encountered during runtime.
        The tab will be created and automatically switched to.
        
        Args:
            procedure_name: Name of the procedure to inject
        """
        # Check if this procedure is already displayed
        if procedure_name in self.task_timeline_widgets:
            print(f"Procedure {procedure_name} already exists, switching to it")
            # Just switch to it
            tab_widget = self.widgets.stack_tab_container
            for i in range(tab_widget.count()):
                # Remove emoji prefix for comparison
                tab_text = tab_widget.tabText(i).replace("⚠️ ", "").replace("⚡ ", "").replace("📋 ", "").strip()
                if tab_text == procedure_name:
                    self._programmatic_tab_switch = True
                    tab_widget.setCurrentIndex(i)
                    self._programmatic_tab_switch = False
                    break
            return
        
        # Get the classification for this procedure
        agent = self.main_window.agent
        classification = 'NORM'  # Default
        
        for state_key, state in agent.states.items():
            if state.procedure == procedure_name:
                classification = getattr(state, 'classification', 'NORM')
                break
        
        print(f"➕ Injecting procedure: {procedure_name} (classification: {classification})")
        
        # Find the current tab index to insert right after current procedure
        tab_widget = self.widgets.stack_tab_container
        current_tab_index = tab_widget.currentIndex()
        insert_position = current_tab_index + 1  # Insert right after current tab
        
        # Create the widget
        timeline_widget = TaskTimelineWidget(parent=tab_widget)
        
        # Ensure it's not set as a window (should be embedded widget only)
        timeline_widget.setWindowFlags(QtCore.Qt.Widget)
        
        # Connect task click signal to handler
        timeline_widget.task_clicked.connect(self.on_task_clicked)
        
        # Determine tab label based on classification
        tab_label = procedure_name
        
        # Insert tab at specific position (not at the end)
        tab_index = tab_widget.insertTab(insert_position, timeline_widget, tab_label)
        
        # NOW load tasks and configure the widget after it's in the tab
        timeline_widget.load_tasks_from_agent(agent)
        timeline_widget.set_current_procedure(procedure_name)
        
        # Store widget in dictionary
        self.task_timeline_widgets[procedure_name] = timeline_widget
        self.discovered_procedures.add(procedure_name)
        
        # Mark emergency tabs for styling
        if classification == 'EMER':
            tab_widget.tabBar().setTabData(tab_index, {'emergency': 'true'})
        
        # Switch to the newly created tab
        self._programmatic_tab_switch = True
        tab_widget.setCurrentIndex(tab_index)
        self._programmatic_tab_switch = False
        
        print(f"✅ Inserted procedure tab at position {insert_position}, switched to index {tab_index}")
    
    def update_task_timeline(self, current_state_obj):
        """Update the task timeline to show current procedure and highlight current task
        
        Args:
            current_state_obj: State object with procedure, task_object, value attributes
        """
        if not current_state_obj:
            return
        
        procedure_name = current_state_obj.procedure
        classification = getattr(current_state_obj, 'classification', 'NORM')
        
        # AUTO-DISCOVERY: Check if this procedure hasn't been discovered yet
        # This handles emergency procedures AND their cascading checklists/subsequent procedures
        if procedure_name not in self.discovered_procedures:
            # New procedure discovered! Inject it dynamically
            if classification in ['EMER', 'ABNORM']:
                print(f"🚨 Emergency/Abnormal procedure discovered: {procedure_name} ({classification})")
            else:
                print(f"� New procedure discovered: {procedure_name} ({classification})")
            
            self.inject_emergency_procedure(procedure_name)
        
        # Switch to the tab for the current procedure
        if procedure_name != self.current_procedure:
            self.current_procedure = procedure_name

            # Find and activate the tab using the stored widget reference (avoids
            # fragile label-text matching which breaks when labels have emoji prefixes)
            tab_widget = self.widgets.stack_tab_container
            timeline_widget_for_lookup = self.task_timeline_widgets.get(procedure_name)
            if timeline_widget_for_lookup:
                idx = tab_widget.indexOf(timeline_widget_for_lookup)
                if idx >= 0:
                    self._programmatic_tab_switch = True
                    tab_widget.setCurrentIndex(idx)
                    self._programmatic_tab_switch = False
        
        # Get the timeline widget for this procedure
        timeline_widget = self.task_timeline_widgets.get(procedure_name)
        if not timeline_widget:
            return
        
        # Get previous task key to detect task changes
        previous_task_key = timeline_widget._current_task_key
        
        # Set current procedure (should already be set, but ensure it)
        timeline_widget.set_current_procedure(procedure_name)
        
        # Set current task (highlight it) - use the same key format as agent
        task_key = (current_state_obj.procedure, current_state_obj.task_object, current_state_obj.value)
        timeline_widget.set_current_task(task_key)
        
        # If task actually changed, advance the animation
        if previous_task_key != task_key and previous_task_key is not None:
            print(f"Task changed from {previous_task_key} to {task_key}")
            timeline_widget.advance_to_next_task()
            # Don't start connection animation here - it will start when next_countdown begins
        elif previous_task_key is None:
            # First task - reset animation
            timeline_widget.reset_animation()
    
    def refresh_task_timeline_data(self):
        """Refresh task timeline data from agent (call when agent data updates)"""
        # Recreate all tabs with fresh data
        self._setup_task_timeline()
    
    @QtCore.Slot(int)
    def _on_tab_changed_by_user(self, index: int):
        """Handle manual tab click — jump FSM to first task of the selected procedure.

        Programmatic tab switches (from update_task_timeline / inject_emergency_procedure)
        set ``_programmatic_tab_switch`` so this handler early-returns for those.
        """
        if self._programmatic_tab_switch:
            return

        tab_widget = self.widgets.stack_tab_container
        widget = tab_widget.widget(index)
        if widget is None:
            return

        # Reverse-lookup: widget → procedure name
        procedure_name = None
        for proc, timeline in self.task_timeline_widgets.items():
            if timeline is widget:
                procedure_name = proc
                break

        if not procedure_name:
            return  # Likely a checklist tab, ignore

        # Only jump to first task when in BASELINE mode (no autonomy roles assigned);
        # in TARP-S/TARP-F the FSM drives procedure sequencing automatically.
        if not getattr(self.main_window, 'is_baseline_mode', False):
            return

        # Find the first task of this procedure from agent states
        agent = getattr(self.main_window, 'agent', None)
        if not agent:
            return

        for state_key, state in agent.states.items():
            if state.procedure == procedure_name:
                procedure, task_object, value = state_key
                gui_agent = getattr(self.main_window, 'gui_agent', None)
                if gui_agent:
                    print(f"📑 Tab clicked → jumping to first task of {procedure_name}")
                    gui_agent.send_force_state_jump(procedure, task_object, value)
                break

    @QtCore.Slot(tuple)
    def on_task_clicked(self, task_key):
        """Handle task click from timeline widget
        
        Args:
            task_key: Tuple of (procedure, task_object, value) identifying the clicked task
        """
        print(f"🖱️ Task clicked: {task_key}")
        
        # Send force_state_jump via GUIAgent to TARS subprocess
        if hasattr(self.main_window, 'gui_agent') and self.main_window.gui_agent:
            procedure, task_object, value = task_key
            self.main_window.gui_agent.send_force_state_jump(procedure, task_object, value)
        else:
            print("⚠️ GUI Agent not available")
    
    @QtCore.Slot(tuple)
    def on_checklist_item_clicked(self, task_key):
        """Handle checklist item click from electronic checklist
        
        Args:
            task_key: Tuple of (procedure, task_object, value) identifying the clicked checklist item
        """
        print(f"📋 Checklist item clicked: {task_key}")
        
        # Send force_state_jump via GUIAgent to TARS subprocess
        if hasattr(self.main_window, 'gui_agent') and self.main_window.gui_agent:
            procedure, task_object, value = task_key
            self.main_window.gui_agent.send_force_state_jump(procedure, task_object, value)
        else:
            print("⚠️ GUI Agent not available")
    
    def get_current_timeline_widget(self):
        """Get the timeline widget for the current active procedure
        
        Returns:
            TaskTimelineWidget or None if no current procedure
        """
        if self.current_procedure and self.current_procedure in self.task_timeline_widgets:
            return self.task_timeline_widgets[self.current_procedure]
        return None
    
    def show_page(self):
        """
        Show the home page
        """
        self.widgets.stackedWidget.setCurrentWidget(self.page_widget)
        #print("Showing home page")
    
    def hide_page(self):
        """
        Hide the home page
        """
        # Home page doesn't need specific hiding logic
        # as it's handled by the stacked widget
        print("Hiding home page")
    
    def refresh_data(self):
        """
        Refresh home page data
        """
        # Add any data refresh logic for home page here
        print("Refreshing home page data")
    
    # COUNTDOWN TIMER METHODS
    # ///////////////////////////////////////////////////////////////
    def update_current_countdown(self):
        """Update current task countdown display"""
        # Check if task was cancelled - ignore timer events if so
        if self._task_cancelled:
            return
        
        if self.current_countdown_value > 0:
            self.current_countdown_value -= 1
            # Update both the old label (for compatibility) and the circular widget
            self.widgets.c_t_s_value_2.setText(str(self.current_countdown_value))
            if self.current_circular_countdown:
                # Animate to the new value over 1 second
                self.current_circular_countdown.animate_to(self.current_countdown_value, duration_ms=1000)
            
            # Update timeline animation for current task border (delay_before_action countdown)
            timeline_widget = self.get_current_timeline_widget()
            if timeline_widget and self.current_countdown_max > 0:
                # Progress from 0.0 to 1.0 as countdown decreases
                progress = 1.0 - (self.current_countdown_value / self.current_countdown_max)
                timeline_widget.set_task_border_progress(progress)
            
            # Check if we just reached 0
            if self.current_countdown_value == 0:
                # Task border is now complete - NOW start the connection animation
                if timeline_widget:
                    timeline_widget.complete_current_task()
                    # Start connection animation immediately after task completion
                    timeline_widget._active_connection_index = timeline_widget._current_task_index
                    timeline_widget.set_connection_progress(0.0)
                # Only emit signal if task was not cancelled
                if not self._task_cancelled:
                    self.countdown_zero_signal.emit()
        else:
            self.widgets.c_t_s_value_2.setText("0")
            if self.current_circular_countdown:
                self.current_circular_countdown.set_value(0, self.current_countdown_max)
            # Complete the timeline animation for current task border
            timeline_widget = self.get_current_timeline_widget()
            if timeline_widget:
                timeline_widget.complete_current_task()
            self.current_countdown_timer.stop()

    def update_next_countdown(self):
        """Update next task countdown display"""
        if self.next_countdown_value > 0:
            self.next_countdown_value -= 1
            # Update both the old label (for compatibility) and the circular widget
            self.widgets.n_t_s_value_2.setText(str(self.next_countdown_value))
            if self.next_circular_countdown:
                # Animate to the new value over 1 second
                self.next_circular_countdown.animate_to(self.next_countdown_value, duration_ms=1000)
            
            # Only animate connection line if current task border is complete (progress = 1.0)
            timeline_widget = self.get_current_timeline_widget()
            if timeline_widget and self.next_countdown_max > 0:
                # Check if current task border is complete
                if timeline_widget._current_task_progress >= 1.0:
                    # Current task is complete, now animate the connection
                    progress = 1.0 - (self.next_countdown_value / self.next_countdown_max)
                    timeline_widget.set_connection_progress(progress)
                # If current task border isn't complete, don't animate connection yet
        else:
            self.widgets.n_t_s_value_2.setText("0")
            if self.next_circular_countdown:
                self.next_circular_countdown.set_value(0, self.next_countdown_max)
            # Complete the connection animation to next task
            timeline_widget = self.get_current_timeline_widget()
            if timeline_widget:
                timeline_widget.set_connection_progress(1.0)
            self.next_countdown_timer.stop()
    
    def start_current_countdown(self, seconds):
        """Start countdown for current task"""
        # Reset cancellation flag and button mode for new countdown
        self._task_cancelled = False
        self._reset_cancel_button_to_normal()
        
        self.current_countdown_value = seconds
        self.current_countdown_max = seconds  # Store max for progress calculation
        if self.current_circular_countdown:
            self.current_circular_countdown.set_value(seconds, seconds)
        # Reset task border animation when starting new countdown
        timeline_widget = self.get_current_timeline_widget()
        if timeline_widget:
            timeline_widget.set_task_border_progress(0.0)
        self.current_countdown_timer.start()
    
    def start_next_countdown(self, seconds):
        """Start countdown for next task"""
        self.next_countdown_value = seconds
        self.next_countdown_max = seconds  # Store max for progress calculation
        if self.next_circular_countdown:
            self.next_circular_countdown.set_value(seconds, seconds)
        # DON'T start connection animation here - it will start when current task border completes
        # Just prepare the connection index but keep progress at 0
        timeline_widget = self.get_current_timeline_widget()
        if timeline_widget:
            timeline_widget._active_connection_index = timeline_widget._current_task_index
            # Connection stays at 0 until current task border is complete
        self.next_countdown_timer.start()
        self.next_countdown_timer.start()
    
    def handle_human_task(self):
        """Handle task when performer is human (no countdown needed)"""
        # Reset cancellation flag and button mode - human tasks don't have countdown to cancel
        self._task_cancelled = False
        self._reset_cancel_button_to_normal()
        
        # Stop any running countdown
        self.current_countdown_timer.stop()
        self.current_countdown_value = 0
        self.current_countdown_max = 1  # Set a default for progress calculation
        
        # Immediately complete the task border animation for human tasks
        timeline_widget = self.get_current_timeline_widget()
        if timeline_widget:
            timeline_widget.set_task_border_progress(1.0)
            timeline_widget.complete_current_task()
            # Start connection animation immediately since there's no countdown
            timeline_widget._active_connection_index = timeline_widget._current_task_index
            timeline_widget.set_connection_progress(0.0)
        
        # Emit signal that the "countdown" is complete (for FSM synchronization)
        self.countdown_zero_signal.emit()
    
    # LABEL UTILITY METHODS
    # ///////////////////////////////////////////////////////////////
    def hide_label(self, label):
        """Hide a label with opacity effect"""
        opacity_effect = label.graphicsEffect()
        if not isinstance(opacity_effect, QGraphicsOpacityEffect):
            opacity_effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(opacity_effect)
        opacity_effect.setOpacity(0.0)
    
    def show_label(self, label):
        """Show a label with opacity effect"""
        opacity_effect = label.graphicsEffect()
        if not isinstance(opacity_effect, QGraphicsOpacityEffect):
            opacity_effect = QGraphicsOpacityEffect(label)
            label.setGraphicsEffect(opacity_effect)
        opacity_effect.setOpacity(0.99)
        label.show()
    
    def hide_button(self, button):
        """Hide a button"""
        button.hide()
    
    # TASK BUTTON HANDLERS
    # ///////////////////////////////////////////////////////////////
    def task_done_clicked(self):
        """Handle task done button click"""
        #self.start_glow_effect(self.widgets.current_task_container_3, "green")
        # Emit signal to notify MainWindow
        self.task_done_signal.emit()
    
    def task_allowed_clicked(self):
        """Handle task allowed button click"""
        self.start_glow_effect(self.widgets.current_task_container_3, "blue")
        # Emit signal to notify MainWindow
        self.task_allowed_signal.emit()

    def task_not_allowed_clicked(self):
        """Handle task not allowed button click"""
        print("Task not allowed clicked")
        self.start_glow_effect(self.widgets.current_task_container_3, "red")
        # Emit signal to notify MainWindow
        self.task_not_allowed_signal.emit()

    def task_cancel_clicked(self):
        """Handle task cancel/override button click - behavior depends on button mode"""
        
        if self._button_in_override_mode:
            # Button is in OVERRIDE mode - force transition to next state
            self.start_glow_effect(self.widgets.current_task_container_3, "green")
            self.task_override_signal.emit()
        else:
            # Button is in CANCEL mode - cancel the current task
            self.start_glow_effect(self.widgets.current_task_container_3, "red")
            
            # Mark task as cancelled
            self._task_cancelled = True
            
            # Stop the countdown timer and update UI
            self.current_countdown_timer.stop()
            self.current_countdown_value = 0
            if self.current_circular_countdown:
                self.current_circular_countdown.hide()
            self.widgets.c_t_s_unit_2.show()
            self.widgets.c_t_s_value_2.show()
            self.widgets.c_t_s_value_2.setText("N/A")
            
            # Complete the task border animation in timeline widget
            timeline_widget = self.get_current_timeline_widget()
            if timeline_widget:
                # Set border progress to 100% (completed)
                timeline_widget._target_task_progress = 1.0
                timeline_widget._current_task_progress = 1.0
                # Mark task as complete and start connection animation
                timeline_widget.complete_current_task()
                timeline_widget.update()
            
            # Emit signal to inhibit current action
            self.task_cancel_signal.emit()
            
            # Switch button to OVERRIDE mode
            self._button_in_override_mode = True
            self._update_cancel_button_text()
    
    def _update_cancel_button_text(self):
        """Update cancel button text based on current mode (override from TaskPageBase)"""
        if self._button_in_override_mode:
            self.cancel_task_button.setText("OVERRIDE")
        else:
            self.cancel_task_button.setText("CANCEL")
    
    # VISUAL EFFECTS
    # ///////////////////////////////////////////////////////////////
    def start_glow_effect(self, widget, color):
        """Start glow effect on widget"""
        # Check if this widget is already glowing - don't start a new effect
        if self._glow_active_widget is widget:
            return
        
        # Mark this widget as actively glowing
        self._glow_active_widget = widget
        
        # Flicker parameters: border width and color alpha
        if color == "red":
            self._glow_steps = [
                (2, "#ff3333"), (4, "#ff3333"), (6, "#ff3333"), (8, "#ff3333"),
                (6, "#ff3333"), (4, "#ff3333"), (2, "#ff3333"), (2, "#ff3333"), 
                (4, "#ff3333"), (6, "#ff3333"), (8, "#ff3333"),
                (6, "#ff3333"), (4, "#ff3333"), (2, "#ff3333")
            ]       
        elif color == "blue":
            self._glow_steps = [
                (2, "#3399ff"), (4, "#3399ff"), (6, "#3399ff"), (8, "#3399ff"),
                (6, "#3399ff"), (4, "#3399ff"), (2, "#3399ff"), (2, "#3399ff"), 
                (4, "#3399ff"), (6, "#3399ff"), (8, "#3399ff"),
                (6, "#3399ff"), (4, "#3399ff"), (2, "#3399ff")
            ]
        elif color == "green":
            self._glow_steps = [
                (2, "#00ff00"), (4, "#00ff00"), (6, "#00ff00"), (8, "#00ff00"),
                (6, "#00ff00"), (4, "#00ff00"), (2, "#00ff00"), (2, "#00ff00"), 
                (4, "#00ff00"), (6, "#00ff00"), (8, "#00ff00"),
                (6, "#00ff00"), (4, "#00ff00"), (2, "#00ff00")
            ]
        
        self._glow_index = 0
        if self._glow_timer is None:
            self._glow_timer = QtCore.QTimer(self.main_window)
            self._glow_timer.timeout.connect(lambda: self._glow_tick(widget))
            self._glow_timer.setSingleShot(False)
        self._glow_timer.start(30)  # Flicker speed

    def _glow_tick(self, widget):
        """Handle glow effect tick"""
        width, color = self._glow_steps[self._glow_index]
        widget.setStyleSheet(f"""
            #currentTaskContainer {{
            border: {width}px solid {color};
            border-radius: 8px;
            background-color: rgba(19, 20, 23, 255);
            }}
        """)
        self._glow_index += 1
        if self._glow_index >= len(self._glow_steps):
            # Stabilize to a steady glow after flicker
            self._glow_timer.stop()
            widget.setStyleSheet(f"""
                #currentTaskContainer {{
                border: 4px solid {color};
                border-radius: 8px;
                background-color: rgba(19, 20, 23, 255);
                }}
            """)
            # Clear the active widget tracking since glow is complete
            self._glow_active_widget = None
    
    def reset_radio_button(self, button):
        button.setChecked(False)

    def show_button(self, button, color):
        """Show button with specified color styling"""
        #if color == "grey":
            #button.setStyleSheet("""
            #QPushButton {
                #border: 2px solid rgba(52, 59, 72, 255);
                #border-radius: 5px;
                #background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    #stop:0 rgba(33, 37, 43, 255), stop:1 rgba(40,40,50,255));
                #font: 600 16pt "JetBrains Mono";
                #padding: 6px 10px;
            #}
            #QPushButton:pressed {
                #/* darker, slightly inset 3D pressed look */
                #background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    #stop:0 rgba(52, 59, 72, 255), stop:1 rgba(60,60,70,255));
                #border: 2px solid rgba(52, 59, 72, 255);
                #padding-top: 8px;    /* push content down to simulate depression */
                #padding-bottom: 4px;
            #}
            #QPushButton:focus {
                #outline: none;
            #}
            #""")
            #button.setIcon(QtGui.QIcon())
        button.show()

    @QtCore.Slot(str, str)
    def displayAlert(self, text: str, color: str = "red"):
        """Display alert with specified text and color
        
        Args:
            text: Alert text to display
            color: Alert border color (red, orange, yellow, etc.)
        """
        self.widgets.alert_container_3.setStyleSheet(f"""
            QWidget#alert_container_3 {{
                border: 2px solid {color};
                border-radius: 5px;
                background-color: rgba(33, 37, 43, 255);
            }}
        """)
        self.widgets.alert_label_2.setText(text)
        self.start_glow_effect(self.widgets.alert_container_3, color)
    
    @QtCore.Slot()
    def clearAlert(self):
        """Clear the alert display"""
        self.widgets.alert_container_3.setStyleSheet("""
            QWidget#alert_container_3 {
                border: 2px solid rgba(52, 59, 72, 255);
                border-radius: 5px;
                background-color: rgba(33, 37, 43, 255);
            }
        """)
        self.widgets.alert_label_2.setText("")

    # Helper function
    def format_checklist_line(self, left: str, right: str, total_width: int = 60, dash_char: str = "-") -> str:
        """Return a string with left and right text separated by dashes, aligned to total_width."""
        left = str(left)
        right = str(right)
        dash_count = max(2, total_width - len(left) - len(right))
        return f"{left}{dash_char * dash_count}{right}"