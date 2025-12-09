# ///////////////////////////////////////////////////////////////
#
# BY: WANDERSON M.PIMENTA
# PROJECT MADE WITH: Qt Designer and PySide6
# V: 1.0.0
#
# This project can be used freely for all uses, as long as they maintain the
# respective credits only in the Python scripts, any information in the visual
# interface (GUI) can be modified without any implication.
#
# There are limitations on Qt licenses if you want to use your products
# commercially, I recommend reading them on the official website:
# https://doc.qt.io/qtforpython/licenses.html
#
# ///////////////////////////////////////////////////////////////

import sys
import os
import platform
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtGui import QFont, QFontDatabase
import signal
import threading
import subprocess
from pathlib import Path
from Core.agent import ApprovalStatus, TarsAgent
from Core.fsm_worker import FSMWorker as FSMWorkerCore  # Import the core FSM worker
from Core.tts import format_callout, shutdown, register_speak_callback, register_finished_callback
import time

# IMPORT / GUI AND MODULES AND WIDGETS
# ///////////////////////////////////////////////////////////////
from modules import *
from modules import resources_rc  # Import resources explicitly
from widgets import *
from pages import PageManager  # Import page manager
os.environ["QT_FONT_DPI"] = "96" # FIX Problem for High DPI and Scale above 100%

# SET AS GLOBAL WIDGETS
# ///////////////////////////////////////////////////////////////
widgets = None

# FSM Worker - Qt Wrapper
# ///////////////////////////////////////////////////////////////
class FSMWorker(QtCore.QObject):
    """
    Qt wrapper for FSMWorkerCore - bridges callback pattern to Qt signals
    This allows gradual migration from direct Qt coupling to pure callback pattern
    """
    state_changed = QtCore.Signal(object)  # Changed from str to object to emit State object
    action_about_to_fire = QtCore.Signal(object)  # Emitted right before action executes (after countdown)
    condition_violated_signal = QtCore.Signal(object, str)  # (state, condition_name) - condition now False
    condition_restored_signal = QtCore.Signal(object, str)  # (state, condition_name) - condition now True

    def __init__(self, agent: TarsAgent):
        super().__init__()
        self.agent = agent
        
        # Create the core worker (no Qt dependencies)
        self.core_worker = FSMWorkerCore(agent)
        
        # Register callbacks to emit Qt signals
        self.core_worker.set_state_changed_callback(self._on_state_changed)
        self.core_worker.set_action_about_to_fire_callback(self._on_action_about_to_fire)
        
        # Expose properties for backwards compatibility
        @property
        def active_monitored_conditions(self):
            return self.core_worker.active_monitored_conditions
        
        @property
        def current_procedure(self):
            return self.core_worker.current_procedure
    
    @property
    def current_state(self):
        return self.core_worker.current_state
    
    # Callback handlers that emit Qt signals
    def _on_state_changed(self, state):
        self.state_changed.emit(state)
    
    def _on_action_about_to_fire(self, state):
        self.action_about_to_fire.emit(state)
    
    def _on_condition_violated(self, state, condition_name):
        self.condition_violated_signal.emit(state, condition_name)
    
    def _on_condition_restored(self, state, condition_name):
        self.condition_restored_signal.emit(state, condition_name)
    
    @QtCore.Slot()
    def cancel_current_action(self):
        """Slot to cancel/skip the current action execution"""
        self.core_worker.cancel_current_action()
    
    @QtCore.Slot()
    def run(self):
        """Qt Slot that runs the core worker"""
        self.core_worker.run()
            
# Agent Thread
# ///////////////////////////////////////////////////////////////
class AgentThread(QtCore.QThread):
    def __init__(self, agent):
        super().__init__()
        self.agent = agent

    def run(self):
        self.agent.start()












# Main Window
# ///////////////////////////////////////////////////////////////
class MainWindow(QMainWindow):
    tts_speak_signal = QtCore.Signal(str)
    tts_finished_signal = QtCore.Signal(str)
    inject_emergency_signal = QtCore.Signal(str)  # New signal for emergency injection
    allocation_sent_signal = QtCore.Signal()  # Emitted when allocation is sent to agent

    def __init__(self):
        QMainWindow.__init__(self)

        # SET AS GLOBAL WIDGETS
        # ///////////////////////////////////////////////////////////////
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        # Phase 6: Create lightweight agent stub for GUI data loading
        # The real TARS Agent runs in subprocess, but GUI needs access to CSV data
        # This stub DOES NOT run start() - it's just for loading states/procedures
        self.agent = TarsAgent()
        # Don't call agent.start() - we don't want duplicate Ingescape agents!
        # Just keep it for CSV data access (self.agent.states, self.agent.procedures)
        
        # Phase 6 FIX: Run TARS Agent as separate subprocess
        # This fixes Ingescape's "one agent per process" limitation
        self.tars_process = None
        self.start_tars_subprocess()
        self.ui.tars_status_label.setText("TARS Agent RUNNING")
        
        # Start STT (Speech-to-Text) subprocess
        self.stt_process = None
        self.stt_monitor_timer = None
        self.start_stt_subprocess()
        
        # Start ATC (Air Traffic Control) subprocess
        self.atc_process = None
        self.start_atc_subprocess()
        
        # Phase 6: FSM Worker and threading removed - TARS Agent now runs independently
        # All FSM logic is handled by TARS Agent subprocess
        # GUI receives state updates via Ingescape messages from GUIAgent
        self.current_state = None
        self.previous_state = None
        self.next_state = None

        # TTS completion tracking - for TTS callbacks
        self.tts_completion_event = threading.Event()
        self.tts_completion_event.set()  # Initially set (ready - no speech in progress)

        # Countdown completion tracking - for countdown timer
        self.countdown_completion_event = threading.Event()
        self.countdown_completion_event.set()  # Initially set (no countdown in progress)

        self.tts_speak_signal.connect(self.on_tts_speak)
        register_speak_callback(self.tts_callback)
        register_finished_callback(self.tts_finished_callback)
        self.tts_finished_signal.connect(self.on_tts_finished)
        
        # Connect emergency injection signal to slot (thread-safe)
        self.inject_emergency_signal.connect(self.inject_emergency_procedure)
        
        global widgets
        
        widgets = self.ui

        # INITIALIZE PAGE MANAGER
        # ///////////////////////////////////////////////////////////////
        self.page_manager = PageManager(widgets, self)
        
        # CONNECT PAGE SIGNALS
        # ///////////////////////////////////////////////////////////////
        self.setup_page_connections()

        # USE CUSTOM TITLE BAR | USE AS "False" FOR MAC OR LINUX
        # ///////////////////////////////////////////////////////////////
        #Settings.ENABLE_CUSTOM_TITLE_BAR = False
        if platform.system() == "Darwin" or platform.system() == "Linux":
            Settings.ENABLE_CUSTOM_TITLE_BAR = True
        if platform.system() == "Windows":
            Settings.ENABLE_CUSTOM_TITLE_BAR = True

        # APP NAME
        # ///////////////////////////////////////////////////////////////
        title = "TARS Interface"
        description = "TARS Interface"
        # APPLY TEXTS
        self.setWindowTitle(title)
        widgets.titleRightInfo.setText(description)

        # TOGGLE MENU
        # ///////////////////////////////////////////////////////////////
        widgets.toggleButton.clicked.connect(lambda: UIFunctions.toggleMenu(self, True))

        # SET UI DEFINITIONS
        # ///////////////////////////////////////////////////////////////
        UIFunctions.uiDefinitions(self)

        # QTableWidget PARAMETERS
        # ///////////////////////////////////////////////////////////////
        widgets.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # BUTTONS CLICK
        # ///////////////////////////////////////////////////////////////
        # Task buttons are now handled by HomePage
        # LEFT MENUS
        widgets.btn_home.clicked.connect(self.navigateToPageButtonClick)
        widgets.btn_briefing.clicked.connect(self.navigateToPageButtonClick)
        widgets.btn_flight.clicked.connect(self.navigateToPageButtonClick)

        # EXTRA LEFT BOX
        def openCloseLeftBox():
            UIFunctions.toggleLeftBox(self, True)
        widgets.toggleLeftBox.clicked.connect(openCloseLeftBox)
        widgets.extraCloseColumnBtn.clicked.connect(openCloseLeftBox)

        # EXTRA RIGHT BOX
        def openCloseRightBox():
            UIFunctions.toggleRightBox(self, True)
        widgets.settingsTopBtn.clicked.connect(openCloseRightBox)

        # SHOW APP
        # ///////////////////////////////////////////////////////////////
        self.show()

        # SET CUSTOM THEME
        # ///////////////////////////////////////////////////////////////
        useCustomTheme = False
        themeFile = "themes/py_dracula_light.qss"

        # SET THEME AND HACKS
        if useCustomTheme:
            # LOAD AND APPLY STYLE
            UIFunctions.theme(self, themeFile, True)
            # SET HACKS
            AppFunctions.setThemeHack(self)

        # SET HOME PAGE AND SELECT MENU
        # ///////////////////////////////////////////////////////////////
        # Page manager will handle initial page navigation
        widgets.btn_home.setStyleSheet(UIFunctions.selectMenu(widgets.btn_home.styleSheet()))
        widgets = self.ui
        
        # INITIALIZE GUI AGENT (Phase 4 & 6)
        # ///////////////////////////////////////////////////////////////
        # GUI Agent wraps this MainWindow and bridges TARS ↔ GUI via Ingescape
        from gui_agent import create_gui_agent
        self.gui_agent = create_gui_agent(self, device="wlp0s20f3", port=5670)
        print("✅ GUI Agent initialized and connected to TARS Agent")
        
    # End of init
    # /////////////////////////////////////////////////////////////
    
    def setup_page_connections(self):
        """
        Setup signal connections between MainWindow and pages
        """
        # Connect HomePage signals
        home_page = self.page_manager.get_page('home')
        if home_page:
            home_page.task_done_signal.connect(self.handle_task_done)
            home_page.task_cancel_signal.connect(self.handle_task_cancel)
            home_page.task_allowed_signal.connect(self.handle_task_allowed)
            home_page.task_not_allowed_signal.connect(self.handle_task_not_allowed)
            home_page.countdown_zero_signal.connect(self.handle_countdown_zero)
        
        # Connect FlightPage signals (same handlers as HomePage)
        flight_page = self.page_manager.get_page('flight')
        if flight_page:
            flight_page.task_done_signal.connect(self.handle_task_done)
            flight_page.task_cancel_signal.connect(self.handle_task_cancel)
            flight_page.task_allowed_signal.connect(self.handle_task_allowed)
            flight_page.task_not_allowed_signal.connect(self.handle_task_not_allowed)
            flight_page.countdown_zero_signal.connect(self.handle_countdown_zero)
            
            # TODO Phase 4: Agent signals will be replaced by GUI Agent Ingescape subscriptions
            # These connections are temporarily commented out during refactorization
            # if hasattr(self, 'agent') and self.agent:
            #     self.agent.alertRequested.connect(home_page.displayAlert)
            #     self.agent.clearAlertRequested.connect(home_page.clearAlert)
            #     self.agent.interactionPanelMessage.connect(self.display_interaction_panel_message)
    
    def display_interaction_panel_message(self, message: str, tars_input: str = ""):
        """Display message in interaction panel TARS input area"""
        self.ui.interaction_panel_text.setText(message)
        self.ui.interaction_panel_tars_input.show()
        self.ui.interaction_panel_tars_input.setText(tars_input)
    
    def set_interaction_text(self, text: str):
        """Set interaction panel text on both home and flight pages"""
        # Empty string from protocol means "no update" - preserve existing text
        if text:  # Only update if not empty
            self.ui.interaction_panel_text.setText(text)
            self.ui.interaction_panel_text_flight.setText(text)
    
    def set_interaction_tars_input(self, text: str, show: bool = True):
        """Set TARS input text on both home and flight pages"""
        # Empty string from protocol means "no update" - preserve existing text
        if text:  # Only update if not empty
            self.ui.interaction_panel_tars_input.setText(text)
            self.ui.interaction_panel_tars_input_flight.setText(text)
        if show and text:  # Only show if there's actual text
            self.ui.interaction_panel_tars_input.show()
            #self.ui.interaction_panel_tars_input_flight.show()
        elif not text:  # Hide if empty (explicit clear)
            self.ui.interaction_panel_tars_input.hide()
            #self.ui.interaction_panel_tars_input_flight.hide()
    
    def handle_task_done(self):
        """
        Handle task done signal from HomePage
        """
        # This is where MainWindow handles the task completion
        # Update agent state
        self.agent.task_acked[0] = True
        print("Task marked as acked\n\n")
    
    def handle_task_cancel(self):
        """
        Handle task cancel signal from HomePage  
        """
        # Stop countdowns on ALL pages and set their cancellation flags
        home_page = self.get_home_page()
        flight_page = self.get_flight_page()
        
        if home_page:
            home_page._task_cancelled = True
            home_page.current_countdown_timer.stop()
        
        if flight_page:
            flight_page._task_cancelled = True
            flight_page.current_countdown_timer.stop()
        
        # Note: task_cancelled signal is sent to TARS via Ingescape (gui_agent.py)
        # TARS agent will call fsm_worker.cancel_current_action() when it receives the signal
        
        self.countdown_completion_event.set()

    def handle_task_allowed(self):
        """
        Handle task allowed signal from HomePage  
        """
        self.agent.task_approval_status[0] = ApprovalStatus.APPROVED
        self.countdown_completion_event.set()
    
    def handle_task_not_allowed(self):
        """
        Handle task not allowed signal from HomePage  
        """
        self.agent.task_approval_status[0] = ApprovalStatus.DENIED
        self.countdown_completion_event.set()
    
    def handle_countdown_zero(self):
        """
        Handle countdown reaching zero - signals that delay_before_action is complete
        """
        print("⏱️ Countdown reached 0, signaling FSM to continue")
        self.countdown_completion_event.set()
    
    def handle_action_about_to_fire(self, state_obj):
        """
        Handle action about to fire - triggers glow effect
        This is called right before the action executes (after countdown reaches 0)
        """
        # Trigger glow effect based on autonomy role
        home_page = self.get_home_page()
        if state_obj.autonomy_role == "performer":
            # Blue glow for performer tasks
            home_page.start_glow_effect(self.ui.current_task_container_3, "blue")
            
            # Get delay_after_action and convert to int for timer
            delay_after = state_obj.delay_after_action
            if delay_after == 'is_acked':
                # Don't show tick mark for acknowledgment-based tasks
                pass
            else:
                try:
                    delay_after_ms = int(float(delay_after) * 1000)
                    home_page.current_circular_countdown.schedule_task_fired(1000, delay_after_ms)
                except (ValueError, TypeError):
                    # If conversion fails, don't schedule tick mark
                    pass

    def get_home_page(self):
        """
        Get the HomePage instance from page manager
        """
        return self.page_manager.get_page('home')
    
    def get_flight_page(self):
        """
        Get the FlightPage instance from page manager
        """
        return self.page_manager.get_page('flight')
    
    def refresh_task_timeline_data(self):
        """
        Refresh task timeline data from agent - call when agent data is updated
        """
        home_page = self.get_home_page()
        if home_page:
            home_page.refresh_task_timeline_data()
    
    @QtCore.Slot(str)
    def inject_emergency_procedure(self, procedure_name):
        """
        Inject an emergency procedure into the timeline
        Called when an emergency condition is detected
        This runs in the main GUI thread (connected via signal)
        
        Args:
            procedure_name: Name of the emergency procedure (e.g., "ENGINE FIRE")
        """
        home_page = self.get_home_page()
        if home_page:
            home_page.inject_emergency_procedure(procedure_name)
    
    def request_emergency_injection(self, procedure_name):
        """
        Request emergency procedure injection from any thread (thread-safe)
        Use this method when calling from worker threads or agent thread
        
        Args:
            procedure_name: Name of the emergency procedure
        """
        # Emit signal to inject in main GUI thread
        self.inject_emergency_signal.emit(procedure_name)

    def tts_callback(self, text):
        # Clear the event - TTS is starting, not ready yet
        self.tts_completion_event.clear()
        self.tts_speak_signal.emit(text)

    def tts_finished_callback(self, text):
        # Set the event - TTS is finished, ready to proceed
        self.tts_completion_event.set()
        self.tts_finished_signal.emit(text)

    def remove_glow(self, widget):
        """Remove glow effect from widget"""
        widget.setStyleSheet(f"""
                #currentTaskContainer {{
                    border: 2px solid rgba(19, 20, 23, 255);
                    border-radius: 10px;
                    background-color: rgba(19, 20, 23, 255);
                }}
                """)

    @QtCore.Slot(str)
    def on_tts_speak(self, text):
        print(f"🎤 TTS Speaking: {text}")  # Debug
        # Use direct file path as fallback since Qt resources aren't working
        pixmap = QPixmap("images/images/TARS_female_speaking.png")
        self.ui.tars_picture.setPixmap(pixmap)
        self.ui.tars_output_speech_label.show()
        self.ui.tars_output_speech_label.setText(f"\"{text}\"")
    
    @QtCore.Slot(object, str)
    def handle_condition_violation(self, state_obj, condition_name):
        """Handle condition violation signal from FSM worker
        Args:
            state_obj: State object with violated condition
            condition_name: Name of the condition function that was violated
        """
        #print(f"🚨 CONDITION VIOLATION: {state_obj.procedure} - {state_obj.task_object} - {condition_name}")
        # Get home page
        home_page = self.get_home_page()
        if not home_page:
            return
        
        # Update checklist to show violation (revert to white)
        home_page.set_checklist_label_violated(
            state_obj.procedure, 
            state_obj.task_object, 
            state_obj.value
        )
        print(f"  → Checklist item reverted to white for {state_obj.procedure} - {state_obj.task_object}")
        
        # Update timeline to show violation
        timeline_widget = home_page.task_timeline_widgets.get(state_obj.procedure)
        if timeline_widget:
            state_key = (state_obj.procedure, state_obj.task_object, state_obj.value)
            timeline_widget.mark_task_violated(state_key)
            print(f"  → Task marked violated in timeline for procedure {state_obj.procedure}")
    
    @QtCore.Slot(object, str)
    def handle_condition_restoration(self, state_obj, condition_name):
        """Handle condition restoration signal from FSM worker
        Args:
            state_obj: State object with restored condition
            condition_name: Name of the condition function that was restored
        """
        #print(f"✅ CONDITION RESTORED: {state_obj.procedure} - {state_obj.task_object} - {condition_name}")
        # Get home page
        home_page = self.get_home_page()
        if not home_page:
            return
        
        # Update checklist to show restoration (restore green)
        home_page.set_checklist_label_restored(
            state_obj.procedure, 
            state_obj.task_object, 
            state_obj.value
        )
        print(f"  → Checklist item restored to green for {state_obj.procedure} - {state_obj.task_object}")
        
        # Update timeline to show restoration
        timeline_widget = home_page.task_timeline_widgets.get(state_obj.procedure)
        if timeline_widget:
            state_key = (state_obj.procedure, state_obj.task_object, state_obj.value)
            timeline_widget.mark_task_restored(state_key)
            print(f"  → Task marked restored in timeline for procedure {state_obj.procedure}")
    
    @QtCore.Slot(str)
    def on_tts_finished(self, text):
        print(f"✅ TTS Finished: {text}")  # Debug
        # Use direct file path as fallback since Qt resources aren't working
        pixmap = QPixmap("images/images/TARS_female.png")
        self.ui.tars_picture.setPixmap(pixmap)

    @QtCore.Slot(object)
    def update_state(self, current_state_obj):
        """Update UI based on the current state object
        
        Args:
            current_state_obj: State object with attributes like procedure, task_object, value, etc.
        """
        fsm = self.agent.fsm
        
        # Find next state by looking through transitions
        next_state_obj = None
        for t in fsm.transitions:
            if t.from_state == current_state_obj:
                next_state_obj = t.to_state
                break
        
        # Get previous, current, and next state objects
        previous_state_obj = getattr(self, '_previous_state_obj', None)
        
        
        # Extract display text from state objects
        previous_procedure_text = previous_state_obj.procedure if previous_state_obj else ""
        previous_task_text = f"{previous_state_obj.task_object}     {previous_state_obj.value}" if previous_state_obj else ""
        
        current_procedure_text = current_state_obj.procedure
        current_task_text = f"{current_state_obj.task_object}     {current_state_obj.value}"
        
        next_procedure_text = next_state_obj.procedure if next_state_obj else ""
        next_task_text = f"{next_state_obj.task_object}     {next_state_obj.value}" if next_state_obj else ""

        # Handle countdown timers using State object attributes
        home_page = self.get_home_page()
        flight_page = self.get_flight_page()
        
        # Stop timers on both pages
        home_page.current_countdown_timer.stop()
        home_page.next_countdown_timer.stop()
        flight_page.current_countdown_timer.stop()
        flight_page.next_countdown_timer.stop()
        
        home_page.set_checklist_label_passed(previous_state_obj.procedure, previous_state_obj.task_object, previous_state_obj.value) if previous_state_obj else None

        home_page.reset_radio_button(self.ui.check_radio_button)
        home_page.connect_int_panel_buttons()
        self.ui.c_t_s_unit_2.hide()
        self.ui.c_t_s_value_2.hide()

        # Hide TARS input on both pages
        self.ui.interaction_panel_tars_input.hide()
        #self.ui.interaction_panel_tars_input_flight.hide()
        
        # For current task counter (uses delay_before_action)
        # Check if this task has numeric delays that need countdown
        has_numeric_delay = False
        try:
            delay_val = current_state_obj.delay_before_action
            if delay_val and str(delay_val).replace('.','',1).isdigit():
                has_numeric_delay = float(delay_val) > 0
        except (ValueError, TypeError, AttributeError):
            has_numeric_delay = False
        
        if has_numeric_delay:
            # Task with countdown delay - show the circular countdown and start timer
            # This applies to ANY task (human performer, TARS performer, supporter) with delays
            if home_page.current_circular_countdown:
                home_page.current_circular_countdown.show()
            if flight_page.current_circular_countdown:
                flight_page.current_circular_countdown.show()
            try:
                seconds = int(current_state_obj.delay_before_action)
                print(f"\n⏰ Starting {seconds}s countdown for task {current_state_obj.task_object} (autonomy_role: {current_state_obj.autonomy_role})")
                self.ui.c_t_s_value_2.setText(str(seconds))
                home_page.start_current_countdown(seconds)
                flight_page.start_current_countdown(seconds)
            except (ValueError, TypeError, AttributeError):
                self.ui.c_t_s_value_2.setText("0")
        elif current_state_obj.autonomy_role != "performer":
            # Human task with no numeric delay - hide countdown, immediate completion
            if home_page.current_circular_countdown:
                home_page.current_circular_countdown.hide()
            if flight_page.current_circular_countdown:
                flight_page.current_circular_countdown.hide()
            home_page.handle_human_task()
            flight_page.handle_human_task()
            self.ui.c_t_s_value_2.setText("Human")
        else:
            # TARS task with 0 or no delay - immediate completion with animations
            if home_page.current_circular_countdown:
                home_page.current_circular_countdown.show()
            if flight_page.current_circular_countdown:
                flight_page.current_circular_countdown.show()
            try:
                seconds = 0
                print(f"\n⚡ 0-second task {current_state_obj.task_object} (autonomy_role: {current_state_obj.autonomy_role})")
                self.ui.c_t_s_value_2.setText("0")
                # For 0-second TARS tasks, initialize and immediately complete the animation
                home_page.current_countdown_value = 0
                home_page.current_countdown_max = 1
                flight_page.current_countdown_value = 0
                flight_page.current_countdown_max = 1
                if home_page.current_circular_countdown:
                    home_page.current_circular_countdown.set_value(0, 0)
                if flight_page.current_circular_countdown:
                    flight_page.current_circular_countdown.set_value(0, 0)
                
                # Initialize task border animation and immediately complete it
                timeline_widget = home_page.get_current_timeline_widget()
                if timeline_widget:
                    timeline_widget._target_task_progress = 1.0
                    timeline_widget._current_task_progress = 1.0
                    timeline_widget.update()
                    timeline_widget.complete_current_task()
                    if home_page.next_countdown_max > 0 and home_page.next_countdown_value < home_page.next_countdown_max:
                        elapsed_progress = 1.0 - (home_page.next_countdown_value / home_page.next_countdown_max)
                        timeline_widget.set_connection_progress(elapsed_progress)
                    else:
                        timeline_widget.set_connection_progress(0.0)
                
                # Emit completion signal for FSM
                home_page.countdown_zero_signal.emit()
            except (ValueError, TypeError, AttributeError):
                self.ui.c_t_s_value_2.setText("0")

        # For next task counter (current delay_after_action + next delay_before_action)
        try:
            if next_state_obj:
                # Check if either delay is 'is_acked' (waiting for human input)
                current_delay_after = current_state_obj.delay_after_action
                next_delay_before = next_state_obj.delay_before_action
                
                if current_delay_after == 'is_acked' or next_delay_before == 'is_acked':
                    # Waiting for human acknowledgment - show N/A
                    home_page.next_circular_countdown.set_na()
                    home_page.next_countdown_timer.stop()
                    home_page.next_countdown_value = 0
                    flight_page.next_circular_countdown.set_na()
                    flight_page.next_countdown_timer.stop()
                    flight_page.next_countdown_value = 0
                    #print(f"\nNext task : {next_state_obj.task_object} - waiting for acknowledgment")
                else:
                    # Normal time-based delays
                    current_delay_before = int(current_state_obj.delay_before_action) if current_state_obj.delay_before_action else 0
                    current_delay_after = int(current_delay_after) if current_delay_after else 0
                    next_delay_before = int(next_delay_before) if next_delay_before else 0
                    total_seconds = current_delay_before + current_delay_after + next_delay_before
                    print(f"\nNext task : {next_state_obj.task_object} estimated time: {total_seconds} seconds")
                    self.ui.n_t_s_value_2.setText(str(total_seconds))
                    if total_seconds > 0:
                        home_page.start_next_countdown(total_seconds)
                        flight_page.start_next_countdown(total_seconds)
                    else:
                        home_page.next_countdown_value = 0
                        flight_page.next_countdown_value = 0
            else:
                self.ui.n_t_s_value_2.setText("N/A")
        except (ValueError, TypeError, AttributeError) as e:
            print(f"Error calculating next task countdown: {e}")
            home_page.next_countdown_timer.stop()
            flight_page.next_countdown_timer.stop()
            self.ui.n_t_s_value_2.setText("N/A")

        # Update UI labels
        self.ui.p_g_2.setText(previous_procedure_text)
        self.ui.p_t_2.setText(previous_task_text)
        self.ui.c_g_2.setText(current_procedure_text)
        self.ui.c_t_2.setText(current_task_text)
        self.ui.n_g_label_2.setText(next_procedure_text)
        self.ui.n_t_label_2.setText(next_task_text)
        self.ui.alert_label_2.setText(f"{current_procedure_text}")
        self.ui.alert_label_flight.setText(f"{current_procedure_text}")
        
        # Handle previous task autonomy role display (home page)
        if previous_state_obj is not None:
            if previous_state_obj.autonomy_role != "performer":
                self.get_home_page().hide_label(self.ui.p_t_prog_widget_2)
            else:
                self.get_home_page().show_label(self.ui.p_t_prog_widget_2)
        else:
            self.ui.p_t_prog_widget_2.hide()
        
        # Handle previous task autonomy role display (flight page)
        if previous_state_obj is not None:
            if previous_state_obj.autonomy_role == "performer":
                # TARS is performer - show TARS icon, hide human icon
                self.ui.p_t_tars_icon_flight.show()
                self.ui.p_t_human_pilot_icon_flight.hide()
            else:
                # Human is performer - show human icon, hide TARS icon
                self.ui.p_t_human_pilot_icon_flight.show()
                self.ui.p_t_tars_icon_flight.hide()
        else:
            # No previous task - hide both icons
            self.ui.p_t_tars_icon_flight.hide()
            self.ui.p_t_human_pilot_icon_flight.hide()
        
        self.remove_glow(self.ui.current_task_container_3)
        

        # Handle current task autonomy role display and buttons (home page)
        if current_state_obj.autonomy_role != "performer":
            self.get_home_page().hide_label(self.ui.c_t_prog_widget_2)
            self.remove_glow(self.ui.current_task_container_3)
            self.ui.cancel_task_button_2.hide()
        else:
            self.get_home_page().show_label(self.ui.c_t_prog_widget_2)
            # Only reset button style if it's currently hidden (new task starting)
            if not self.ui.cancel_task_button_2.isVisible():
                self.get_home_page().show_button(self.ui.cancel_task_button_2, "red")
        
        # Handle current task autonomy role display (flight page)
        if current_state_obj.autonomy_role == "performer":
            # TARS is performer - show TARS icon, hide human icon
            self.ui.c_t_tars_icon_flight.show()
            self.ui.c_t_human_pilot_icon_flight.hide()
        else:
            # Human is performer - show human icon, hide TARS icon
            self.ui.c_t_human_pilot_icon_flight.show()
            self.ui.c_t_tars_icon_flight.hide()

        # Handle next task autonomy role display (home page)
        if next_state_obj is not None:
            if next_state_obj.autonomy_role != "performer":
                self.get_home_page().hide_label(self.ui.n_t_prog_widget_2)
            else:
                self.get_home_page().show_label(self.ui.n_t_prog_widget_2)
        else:
            self.ui.n_t_prog_widget_2.hide()
        
        # Handle next task autonomy role display (flight page)
        if next_state_obj is not None:
            if next_state_obj.autonomy_role == "performer":
                # TARS is performer - show TARS icon, hide human icon
                self.ui.n_t_tars_icon_flight.show()
                self.ui.n_t_human_pilot_icon_flight.hide()
            else:
                # Human is performer - show human icon, hide TARS icon
                self.ui.n_t_human_pilot_icon_flight.show()
                self.ui.n_t_tars_icon_flight.hide()
        else:
            # No next task - hide both icons
            self.ui.n_t_tars_icon_flight.hide()
            self.ui.n_t_human_pilot_icon_flight.hide()
        
        # Setup Electronic Checklist Panel
        current_tab_text = self.ui.ecl_tab_container.tabText(self.ui.ecl_tab_container.currentIndex())
        if current_tab_text != current_procedure_text:
            # Switch to the tab matching the current procedure
            tab_widget = self.ui.ecl_tab_container
            tab_count = tab_widget.count()
            tab_index = -1
            for i in range(tab_count):
                if tab_widget.tabText(i) == current_procedure_text and current_state_obj.type == "Checklist":
                    tab_index = i
                    break
            if tab_index != -1:
                tab_widget.setCurrentIndex(tab_index)
        home_page.set_checklist_label_current(current_procedure_text, current_state_obj.task_object, current_state_obj.value)

        if current_state_obj.type == "Checklist":
            self.set_interaction_text(self.format_checklist_line(current_state_obj.task_object, current_state_obj.value))
            #if not self.ui.int_panel_right_button.isVisible() :
            self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
            self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
            if current_state_obj.autonomy_role == "performer":
                self.ui.int_panel_right_button.setText("CHECK")
                self.ui.int_panel_right_button_flight.setText("CHECK")
            else:
                self.ui.int_panel_right_button.setText("CHECK")
                self.ui.int_panel_right_button_flight.setText("CHECK")
            self.ui.int_panel_left_button.hide()
            self.ui.int_panel_left_button_flight.hide()
        else :
            self.set_interaction_text(current_state_obj.task_object + "    " + current_state_obj.value)
            self.ui.int_panel_right_button.hide()
            #self.ui.int_panel_right_button_flight.hide()
            self.ui.int_panel_left_button.hide()
            self.ui.int_panel_left_button_flight.hide()
    
        # Handle interaction panel based on current state's interaction attribute
        if current_state_obj.interaction is not None and current_state_obj.interaction != "":
            #self.ui.int_panel_right_button.hide()
            #self.ui.int_panel_left_button.hide()
            match current_state_obj.interaction:
                case "pitot_static_switch":
                    self.set_interaction_text("PITOT STATIC HEAT SWITCH - PITOT-STATIC\nCAUTION\n\nLIMIT GROUND OPERATION OF PITOT-STATIC HEAT TO TWO MINUTES TO PRECLUDE DAMAGE TO THE PITOT-STATIC AND STALL WARNING HEATERS.")
                case "engine_anti_ice_requirement":
                    self.set_interaction_tars_input("LAST METAR TEMPERATURE 05°C - IF VISIBLE MOISTURE PRESENT, ENGINE ANTI-ICE ON")
                case "windshield_anti_ice_requirement":
                    self.set_interaction_tars_input("LAST METAR TEMPERATURE 05°C - IF VISIBLE MOISTURE PRESENT, WINDSHIELD ANTI-ICE ON")
                case "anti_ice_systems_as_required":
                    self.set_interaction_tars_input("LAST METAR TEMPERATURE 05°C - IF VISIBLE MOISTURE PRESENT, ANTI-ICE SYSTEMS ON")
                case "landing_light_as_required":
                    self.set_interaction_tars_input("On an active runway, to enhance visibility: LANDING LIGHTS ON")
                case "landing_light_as_required_after_takeoff":
                    self.set_interaction_tars_input("After takeoff, and under 10 000 ft AGL to enhance visibility: LANDING LIGHTS ON")
                case "radar_requirement":
                    self.set_interaction_tars_input("NO WEATHER RADAR IN THIS AIRCRAFT")
                case "display_winds_and_ack":
                    self.set_interaction_text("WIND REPORT:\n\nMETAR: CYUL 201500Z 09004KT 1SM FG OVC015 05/04 A2992 \nRMK CU OVC TOPS 100 MSL CI BASE 250 TOP 270 DRY RWY")
                    self.set_interaction_tars_input("WIND 090° / 04 kt\nCrosswind Component: 02 kt from the right < Max Crosswind (25 knots)\nHeadwind Component: 3.5 kt")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_right_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "grey")
                    if not self.ui.int_panel_left_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_left_button_flight, "grey")
                    self.ui.int_panel_left_button.setText("EDIT")
                    self.ui.int_panel_left_button_flight.setText("EDIT")
                    self.ui.int_panel_right_button.setText("CHECK")
                    self.ui.int_panel_right_button_flight.setText("CHECK")
                case "alt_preset_as_cleared":
                    self.set_interaction_text("Select altitude AS CLEARED BY ATC")
                case "eng_failure_aft_v1_memo_items":
                    home_page.displayAlert(f"Failure detected: {self.agent.engine_failed_side} ENGINE FIRE", "red")
                    self.set_interaction_text(f"ENGINE FAILURE OR FIRE OR MASTER WARNING \nOR ANY OTHER NON-NORMAL EVENT DURING TAKEOFF SPEED ABOVE V1\n\n1. Maintain directional control\n2. Accelerate to Vr = {self.agent.V_ROTATE}\n3. Rotate at Vr = {self.agent.V_ROTATE}, climb at V2 = {self.agent.V_TWO}\n4. LANDING GEAR - UP (after positive rate of climb)\n5. At 1,500 feet AGL, retract flaps at V2+10  and accelerate to Venr = {self.agent.V_ENR}")
                    self.set_interaction_tars_input("Engine fire detected on " + self.agent.engine_failed_side + " engine.")
                case "engine_fire_memo_items":
                    self.set_interaction_text(f"ENGINE FIRE L OR R\n(ENGINE FIRE WARNING LIGHT ILLUMINATED)\n\n1. Throttle ({self.agent.engine_failed_side}) - IDLE\n\nIF LIGHT REMAINS ON (15 SECONDS)\n\n2. ENGINE FIRE Button ({self.agent.engine_failed_side}) LIFT COVER and PUSH")
                case "immediate_action_items":
                    self.set_interaction_text(f"IMMEDIATE ACTION ITEMS:\n\nNON-NORMAL EVENT DURING TAKEOFF\n1. Climb to a safe altitude (1500ft AGL)\n\nENGINE FIRE L OR R\n(ENGINE FIRE WARNING LIGHT ILLUMINATED)\n1. Throttle ({self.agent.engine_failed_side}) - IDLE\nIF LIGHT REMAINS ON (15 SECONDS)\n2. ENGINE FIRE Button ({self.agent.engine_failed_side}) LIFT COVER and PUSH")
                case "end_emer":
                    home_page.clearAlert()
                    self.ui.alert_label_2.setText("")
                case "prompt_start_checklist":
                    self.set_interaction_text(f"{current_state_obj.callout}?")
                    self.ui.int_panel_right_button.setText("START")
                    self.ui.int_panel_right_button_flight.setText("START")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_right_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
                    self.ui.int_panel_left_button.setText("CANCEL")
                    self.ui.int_panel_left_button_flight.setText("CANCEL")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                    if not self.ui.int_panel_left_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_left_button_flight, "red")
                case "prompt_next_checklist":
                    self.set_interaction_text(f"{current_state_obj.value}?")
                    self.ui.int_panel_right_button.setText("NEXT")
                    self.ui.int_panel_right_button_flight.setText("NEXT")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_right_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
                    self.ui.int_panel_left_button.setText("CANCEL")
                    self.ui.int_panel_left_button_flight.setText("CANCEL")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                    if not self.ui.int_panel_left_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_left_button_flight, "red")
                case "allow_trim_rudder":
                    home_page.connect_int_panel_buttons(default=False)
                    self.set_interaction_text("Allow TARS to adjust trim/rudder settings?")
                    self.ui.int_panel_right_button.setText("APPROVE")
                    self.ui.int_panel_right_button_flight.setText("APPROVE")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_right_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
                    self.ui.int_panel_left_button.setText("DENY")
                    self.ui.int_panel_left_button_flight.setText("DENY")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                    if not self.ui.int_panel_left_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_left_button_flight, "red")
                case "allow_engage_ap":
                    home_page.connect_int_panel_buttons(default=False)
                    self.set_interaction_text("Allow TARS to engage the autopilot?")
                    self.ui.int_panel_right_button.setText("APPROVE")
                    self.ui.int_panel_right_button_flight.setText("APPROVE")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_right_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
                    self.ui.int_panel_left_button.setText("DENY")
                    self.ui.int_panel_left_button_flight.setText("DENY")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                    if not self.ui.int_panel_left_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_left_button_flight, "red")
                case "show_v_enr":
                    self.set_interaction_text(f"Set speed to VEnr = {self.agent.V_ENR} knots")
                case "allow_comm":
                    home_page.connect_int_panel_buttons(default=False)
                    self.set_interaction_text("Allow TARS to communicate with ATC?")
                    formatted_callout = format_callout(current_state_obj.callout)
                    self.set_interaction_tars_input(formatted_callout)
                    self.ui.int_panel_right_button.setText("APPROVE")
                    self.ui.int_panel_right_button_flight.setText("APPROVE")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_right_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
                    self.ui.int_panel_left_button.setText("DENY")
                    self.ui.int_panel_left_button_flight.setText("DENY")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                    if not self.ui.int_panel_left_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_left_button_flight, "red")
                case "prompt_announce_panpan":
                    home_page.connect_int_panel_buttons(default=False)
                    self.set_interaction_text("Do you want me to announce announce PAN-PAN and request vectors to ATC on 119.9?")
                    formatted_callout = format_callout(current_state_obj.callout)
                    self.set_interaction_tars_input(formatted_callout)
                    self.ui.int_panel_right_button.setText("APPROVE")
                    self.ui.int_panel_right_button_flight.setText("APPROVE")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_right_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
                    self.ui.int_panel_left_button.setText("DENY")
                    self.ui.int_panel_left_button_flight.setText("DENY")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                    if not self.ui.int_panel_left_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_left_button_flight, "red")
                case "display_trim_rudder":
                    self.set_interaction_text(f"Current trim : {self.agent.trim_rudder} %")
                case "display_alarm":
                    self.set_interaction_text("Alarm: Engine Fire")
                case "display_engage_autopilot":
                    self.set_interaction_text("Engage Autopilot: ")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_right_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                    if not self.ui.int_panel_left_button_flight.isVisible() : self.get_flight_page().show_button(self.ui.int_panel_left_button_flight, "red")
                    self.ui.int_panel_right_button.setText("APPROVE")
                    self.ui.int_panel_right_button_flight.setText("APPROVE")
                    self.ui.int_panel_left_button.setText("DENY")
                    self.ui.int_panel_left_button_flight.setText("DENY")
                case "immediate_action_item":
                    self.set_interaction_text(f"Immediate action item : \n1. Throttle {self.agent.engine_failed_side} engine throttle IDLE\n- IF LIGHT REMAINS ON (15 SECONDS)\nIlluminated ENGINE FIRE Switch LIFT COVER AND PUSH")
                case "display_checklist_emer_eng_fire_continue":
                    self.set_interaction_text("Emergency Fire Checklist: ")
                    if not self.ui.int_panel_right_button.isVisible(): self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_right_button_flight.isVisible(): self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
                    self.ui.int_panel_right_button.setText("START CHECKLIST")
                    self.ui.int_panel_right_button_flight.setText("START CHECKLIST")
                case "display_checklist_aft_takeoff_continue":
                    self.set_interaction_text("After takeoff Checklist: ")
                    if not self.ui.int_panel_right_button.isVisible(): self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_right_button_flight.isVisible(): self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
                    self.ui.int_panel_right_button.setText("START CHECKLIST")
                    self.ui.int_panel_right_button_flight.setText("START CHECKLIST")
                case "display_checklist_aft_takeoff":
                    self.set_interaction_text("After takeoff Checklist: ")
                case "yaw_damper_as_desired":
                    if self.agent.engine_failed_side != "None":
                        self.set_interaction_tars_input("OFF for full rudder authority during single-engine operations")
                    else:
                        self.set_interaction_tars_input("ON for comfort during normal operations")
                case "pax_safety_switch_as_required":
                    self.set_interaction_tars_input("ABNORMAL SITUATION: PAX SAFETY Switch SET TO SEATBELT")
                case "display_alti_set_std":
                    self.set_interaction_text("Setting altimeter to STD")
                case "display_checklist_eng_fail_proc_continue":
                    self.set_interaction_text("Engine Failure Procedure")
                    if not self.ui.int_panel_right_button.isVisible(): self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_right_button_flight.isVisible(): self.get_flight_page().show_button(self.ui.int_panel_right_button_flight, "green")
                    self.ui.int_panel_right_button.setText("START CHECKLIST")
                    self.ui.int_panel_right_button_flight.setText("START CHECKLIST")
                case "display_checklist_eng_fail_proc":
                    self.set_interaction_text("Engine Failure Procedure")
                case "caution_text_readout":
                    self.set_interaction_text("Caution: \nIf possible, the engines should remain at idle for a minimum of two minutes prior to shutdown to allow the engine inter-turbine temperature to stabilize and avoid turbine blade rub.\nIf the engine windmills for more than 15 minutes without a positive indication of oil pressure, a notation is required in the engine logbook and the engine must be inspected in accordance with the Pratt & Whitney engine maintenance manual.\nIf the engine windmills for more than 30 minutes with the firewall shutoff closed or the boost pump turned off, the engine fuel pump must be inspected in accordance with the Pratt & Whitney engine maintenance manual.")
                case "display_checklist_sing_eng_app":
                    self.set_interaction_text("Single Engine Approach and Landing Checklist")
                case "pressurization_check":
                    self.set_interaction_text("Pressurization Check: ")
                    self.set_interaction_tars_input("CABIN ALTITUDE: NORMAL\nDIFFERENTIAL PRESSURE: NORMAL")
    
        # Update task timeline widget
        home_page.update_task_timeline(current_state_obj)

        # Store current state as previous for next update
        self._previous_state_obj = current_state_obj

    # ///////////////////////////////////////////////////////////////
    # PAGE MENU BUTTONS CLICK
    # Post here your functions for clicked buttons
    # ///////////////////////////////////////////////////////////////
    def navigateToPageButtonClick(self):
        # GET BUTTON CLICKED
        btn = self.sender()
        btnName = btn.objectName()

        # SHOW BRIEFING PAGE
        if btnName == "btn_briefing":
            # Use page manager for briefing page
            self.page_manager.navigate_to_page('briefing')
            UIFunctions.resetStyle(self, btnName)
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet()))
        # SHOW HOME PAGE
        if btnName == "btn_home":
            # Use page manager for home page
            self.page_manager.navigate_to_page('home')
            UIFunctions.resetStyle(self, btnName)
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet()))

        # SHOW WIDGETS PAGE
        if btnName == "btn_widgets":
            widgets.stackedWidget.setCurrentWidget(widgets.widgets)
            UIFunctions.resetStyle(self, btnName)
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet()))

        # SHOW NEW PAGE
        if btnName == "btn_flight":
            widgets.stackedWidget.setCurrentWidget(widgets.flight)
            self.page_manager.navigate_to_page('flight')
            UIFunctions.resetStyle(self, btnName)
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet()))
    # //////////////////////////////////////////////////////////////

    # RESIZE EVENTS
    # ///////////////////////////////////////////////////////////////
    def resizeEvent(self, event):
        # Update Size Grips
        UIFunctions.resize_grips(self)

    # MOUSE CLICK EVENTS
    # ///////////////////////////////////////////////////////////////
    def mousePressEvent(self, event):
        # SET DRAG POS WINDOW
        #self.dragpos = event.globalPos() -- ignore --
        self.dragPos = event.globalPosition().toPoint()

        # PRINT MOUSE EVENTS
        #if event.buttons() == Qt.LeftButton:
            #print('Mouse click: LEFT CLICK')
        #if event.buttons() == Qt.RightButton:
            #print('Mouse click: RIGHT CLICK')
    
    # Helper function
    def format_checklist_line(self, left: str, right: str, total_width: int = 48, dash_char: str = "-") -> str:
        """Return a string with left and right text separated by dashes, aligned to total_width."""
        left = str(left)
        right = str(right)
        
        # Replace dynamic text with actual engine side
        if "affected engine" in left.lower() or "affected side" in left.lower():
            left = left.replace("affected engine", self.agent.engine_failed_side)
            left = left.replace("Affected engine", self.agent.engine_failed_side)
            left = left.replace("affected side", self.agent.engine_failed_side)
            left = left.replace("Affected side", self.agent.engine_failed_side)
        
        dash_count = max(2, total_width - len(left) - len(right))
        return f"{left}{dash_char * dash_count}{right}"
    
    def start_stt_subprocess(self):
        """Start the STT (Speech-to-Text) agent as a subprocess"""
        try:
            # Get path to stt.py
            project_root = Path(__file__).parent
            stt_script = project_root / "Speech" / "stt.py"
            
            if not stt_script.exists():
                print(f"⚠️  STT script not found at {stt_script}")
                return
            
            # Get Python interpreter from virtual environment
            if sys.platform == "win32":
                python_exe = project_root / ".venv" / "Scripts" / "python.exe"
            else:
                python_exe = project_root / ".venv" / "bin" / "python"
            
            if not python_exe.exists():
                # Fallback to system Python
                python_exe = sys.executable
                print(f"⚠️  Virtual environment Python not found, using system Python: {python_exe}")
            
            # Start subprocess with unbuffered output
            self.stt_process = subprocess.Popen(
                [str(python_exe), "-u", str(stt_script)],  # -u for unbuffered output
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout
                text=True,
                encoding='utf-8',
                bufsize=1,
                cwd=str(project_root)
            )
            
            print(f"🎤 STT subprocess started (PID: {self.stt_process.pid})")
            
            # Start monitoring thread to read output and check if process crashes
            self.start_stt_monitor()
            
        except Exception as e:
            print(f"❌ Failed to start STT subprocess: {e}")
            import traceback
            traceback.print_exc()
            self.stt_process = None
    
    def start_stt_monitor(self):
        """Start a background thread to monitor STT subprocess output and health"""
        def monitor_stt():
            if not self.stt_process:
                return
            
            print("📊 STT monitor thread started")
            try:
                # Read output line by line
                for line in iter(self.stt_process.stdout.readline, ''):
                    if line:
                        print(f"[STT] {line.rstrip()}")
                    
                    # Check if process is still running
                    if self.stt_process.poll() is not None:
                        break
                
                # Process has exited
                exit_code = self.stt_process.poll()
                if exit_code != 0:
                    print(f"⚠️  STT subprocess crashed with exit code {exit_code}")
                    # Optionally restart
                    # QtCore.QTimer.singleShot(2000, self.start_stt_subprocess)
                else:
                    print("✅ STT subprocess exited normally")
                    
            except Exception as e:
                print(f"❌ Error in STT monitor thread: {e}")
                import traceback
                traceback.print_exc()
        
        # Start monitor in background thread
        monitor_thread = threading.Thread(target=monitor_stt, daemon=True)
        monitor_thread.start()
    
    def start_tars_subprocess(self):
        """Start the TARS Agent as a subprocess (separate Ingescape agent)"""
        try:
            # Get path to tars_agent_runner.py
            project_root = Path(__file__).parent
            tars_script = project_root / "tars_agent_runner.py"
            
            if not tars_script.exists():
                print(f"⚠️  TARS Agent runner not found at {tars_script}")
                return
            
            # Get Python interpreter from virtual environment
            if sys.platform == "win32":
                python_exe = project_root / ".venv" / "Scripts" / "python.exe"
            else:
                python_exe = project_root / ".venv" / "bin" / "python"
            
            if not python_exe.exists():
                # Fallback to system Python
                python_exe = sys.executable
                print(f"⚠️  Virtual environment Python not found, using system Python: {python_exe}")
            
            # Start subprocess with unbuffered output
            self.tars_process = subprocess.Popen(
                [str(python_exe), "-u", str(tars_script)],  # -u for unbuffered output
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout
                text=True,
                encoding='utf-8',
                bufsize=1,
                cwd=str(project_root)
            )
            
            print(f"📡 TARS Agent subprocess started (PID: {self.tars_process.pid})")
            
            # Start monitoring thread to read output and check if process crashes
            self.start_tars_monitor()
            
        except Exception as e:
            print(f"❌ Failed to start TARS Agent subprocess: {e}")
            import traceback
            traceback.print_exc()
            self.tars_process = None
    
    def start_tars_monitor(self):
        """Start a background thread to monitor TARS subprocess output and health"""
        def monitor_tars():
            if not self.tars_process:
                return
            
            print("📊 TARS monitor thread started")
            try:
                # Read output line by line
                for line in iter(self.tars_process.stdout.readline, ''):
                    if line:
                        print(f"[TARS] {line.rstrip()}")
                    
                    # Check if process is still running
                    if self.tars_process.poll() is not None:
                        break
                
                # Process has exited
                exit_code = self.tars_process.poll()
                if exit_code != 0:
                    print(f"⚠️  TARS Agent subprocess crashed with exit code {exit_code}")
                else:
                    print("✅ TARS Agent subprocess exited cleanly")
                    
            except Exception as e:
                print(f"❌ Error monitoring TARS subprocess: {e}")
        
        # Start monitor thread
        monitor_thread = threading.Thread(target=monitor_tars, daemon=True)
        monitor_thread.start()

    def start_atc_subprocess(self):
        """Start the ATC (Air Traffic Control) agent as a subprocess"""
        try:
            # Get path to atc.py
            project_root = Path(__file__).parent
            atc_script = project_root / "ATC" / "atc.py"
            
            if not atc_script.exists():
                print(f"⚠️  ATC script not found at {atc_script}")
                return
            
            # Get Python interpreter from virtual environment
            if sys.platform == "win32":
                python_exe = project_root / ".venv" / "Scripts" / "python.exe"
            else:
                python_exe = project_root / ".venv" / "bin" / "python"
            
            if not python_exe.exists():
                # Fallback to system Python
                python_exe = sys.executable
                print(f"⚠️  Virtual environment Python not found, using system Python: {python_exe}")
            
            # Start subprocess with unbuffered output
            self.atc_process = subprocess.Popen(
                [str(python_exe), "-u", str(atc_script)],  # -u for unbuffered output
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout
                text=True,
                encoding='utf-8',
                bufsize=1,
                cwd=str(project_root)
            )
            
            print(f"📡 ATC subprocess started (PID: {self.atc_process.pid})")
            
            # Start monitoring thread to read output and check if process crashes
            self.start_atc_monitor()
            
        except Exception as e:
            print(f"❌ Failed to start ATC subprocess: {e}")
            import traceback
            traceback.print_exc()
            self.atc_process = None
    
    def start_atc_monitor(self):
        """Start a background thread to monitor ATC subprocess output and health"""
        def monitor_atc():
            if not self.atc_process:
                return
            
            print("📊 ATC monitor thread started")
            try:
                # Read output line by line
                for line in iter(self.atc_process.stdout.readline, ''):
                    if line:
                        print(f"[ATC] {line.rstrip()}")
                    
                    # Check if process is still running
                    if self.atc_process.poll() is not None:
                        break
                
                # Process has exited
                exit_code = self.atc_process.poll()
                if exit_code != 0:
                    print(f"⚠️  ATC subprocess crashed with exit code {exit_code}")
                    # Optionally restart
                    # QtCore.QTimer.singleShot(2000, self.start_atc_subprocess)
                else:
                    print("✅ ATC subprocess exited normally")
                    
            except Exception as e:
                print(f"❌ Error in ATC monitor thread: {e}")
                import traceback
                traceback.print_exc()
        
        # Start monitor in background thread
        monitor_thread = threading.Thread(target=monitor_atc, daemon=True)
        monitor_thread.start()
    
    def stop_tars_subprocess(self):
        """Stop the TARS Agent subprocess gracefully"""
        if self.tars_process:
            try:
                print("🛑 Stopping TARS Agent subprocess...")
                self.tars_process.terminate()  # Send SIGTERM
                try:
                    self.tars_process.wait(timeout=5)  # Wait up to 5 seconds
                    print("✅ TARS Agent subprocess stopped")
                except subprocess.TimeoutExpired:
                    print("⚠️  TARS Agent subprocess didn't stop gracefully, forcing...")
                    self.tars_process.kill()  # Force kill
                    self.tars_process.wait()
                    print("✅ TARS Agent subprocess killed")
            except Exception as e:
                print(f"❌ Error stopping TARS Agent subprocess: {e}")
            finally:
                self.tars_process = None
    
    def stop_atc_subprocess(self):
        """Stop the ATC subprocess gracefully"""
        if self.atc_process:
            try:
                print("🛑 Stopping ATC subprocess...")
                self.atc_process.terminate()  # Send SIGTERM
                try:
                    self.atc_process.wait(timeout=5)  # Wait up to 5 seconds
                    print("✅ ATC subprocess stopped")
                except subprocess.TimeoutExpired:
                    print("⚠️  ATC subprocess didn't stop gracefully, forcing...")
                    self.atc_process.kill()  # Force kill
                    self.atc_process.wait()
                    print("✅ ATC subprocess killed")
            except Exception as e:
                print(f"❌ Error stopping ATC subprocess: {e}")
            finally:
                self.atc_process = None
    
    def stop_stt_subprocess(self):
        """Stop the STT subprocess gracefully"""
        if self.stt_process:
            try:
                print("🛑 Stopping STT subprocess...")
                self.stt_process.terminate()  # Send SIGTERM
                try:
                    self.stt_process.wait(timeout=5)  # Wait up to 5 seconds
                    print("✅ STT subprocess stopped")
                except subprocess.TimeoutExpired:
                    print("⚠️  STT subprocess didn't stop gracefully, forcing...")
                    self.stt_process.kill()  # Force kill
                    self.stt_process.wait()
                    print("✅ STT subprocess killed")
            except Exception as e:
                print(f"❌ Error stopping STT subprocess: {e}")
            finally:
                self.stt_process = None
    
    def closeEvent(self, event):
        """Override close event to cleanup subprocess"""
        print("Closing application...")
        
        # Stop TARS Agent subprocess
        self.stop_tars_subprocess()
        
        # Stop STT subprocess
        self.stop_stt_subprocess()
        
        # Stop ATC subprocess
        self.stop_atc_subprocess()
        
        # Shutdown TTS
        shutdown()
        
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Add this to allow Ctrl+C to work
    from PySide6.QtCore import QTimer
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(100)

    app.setWindowIcon(QIcon("icon.ico"))
    window = MainWindow()
    sys.exit(app.exec())
