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
from PySide6.QtWidgets import QGraphicsOpacityEffect, QPushButton
from PySide6.QtGui import QFont, QFontDatabase
import signal
import threading
import subprocess
from pathlib import Path
from Core.agent import ApprovalStatus, TarsAgent
from Core.fsm_worker import FSMWorker as FSMWorkerCore  # Import the core FSM worker
import time

# Import page types for type hints
from pages.home_page import HomePage
from pages.flight_page import FlightPage

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
NO_NEXT_COUNTDOWN = False

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
        self.tars_process: subprocess.Popen | None = None
        self.start_tars_subprocess()
        self.ui.tars_status_label.setText("TARS Agent RUNNING")
        
        # Start STT (Speech-to-Text) subprocess
        self.stt_process: subprocess.Popen | None = None
        self.stt_monitor_timer = None
        self.start_stt_subprocess()
        
        # Start ATC (Air Traffic Control) subprocess
        self.atc_process: subprocess.Popen | None = None
        self.start_atc_subprocess()
        
        # Start TTS (Text-to-Speech) subprocess
        self.tts_process: subprocess.Popen | None = None
        self.start_tts_subprocess()
        
        # Phase 6: FSM Worker and threading removed - TARS Agent now runs independently
        # All FSM logic is handled by TARS Agent subprocess
        # GUI receives state updates via Ingescape messages from GUIAgent
        self.current_state = None
        self.previous_state = None
        self.next_state = None

        # Countdown completion tracking - for countdown timer
        self.countdown_completion_event = threading.Event()
        self.countdown_completion_event.set()  # Initially set (no countdown in progress)

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
        widgets.toggleButton.clicked.connect(lambda: UIFunctions.toggleMenu(self, True)) # type: ignore

        # SET UI DEFINITIONS
        # ///////////////////////////////////////////////////////////////
        UIFunctions.uiDefinitions(self) # type: ignore

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
            UIFunctions.toggleLeftBox(self, True) # type: ignore
        widgets.toggleLeftBox.clicked.connect(openCloseLeftBox)
        widgets.extraCloseColumnBtn.clicked.connect(openCloseLeftBox)

        # EXTRA RIGHT BOX
        def openCloseRightBox():
            UIFunctions.toggleRightBox(self, True) # type: ignore
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
            UIFunctions.theme(self, themeFile, True) # type: ignore
            # SET HACKS
            AppFunctions.setThemeHack(self) # type: ignore

        # SET HOME PAGE AND SELECT MENU
        # ///////////////////////////////////////////////////////////////
        # Page manager will handle initial page navigation
        widgets.btn_home.setStyleSheet(UIFunctions.selectMenu(widgets.btn_home.styleSheet())) # type: ignore
        widgets = self.ui
        
        # INITIALIZE SPEECH LOG (replaces tars_output_speech_label)
        # ///////////////////////////////////////////////////////////////
        self._init_speech_log()

        # INITIALIZE GUI AGENT (Phase 4 & 6)
        # ///////////////////////////////////////////////////////////////
        # GUI Agent wraps this MainWindow and bridges TARS ↔ GUI via Ingescape
        from gui_agent import create_gui_agent
        self.gui_agent = create_gui_agent(self, device="wlp0s20f3", port=5670, no_next_countdown=NO_NEXT_COUNTDOWN)
        print("✅ GUI Agent initialized and connected to TARS Agent")

        # TTS speaking state - used to gate the picture click handler
        self._tts_speaking = False
        # Persistent mute state - set by clicking the TARS picture
        self._tts_muted = False

        # Make tars_picture clickable to toggle TTS mute/unmute
        def _tars_picture_clicked(event):
            if not hasattr(self, 'gui_agent'):
                return
            if self._tts_muted:
                # Unmute
                self._tts_muted = False
                self.gui_agent.send_tts_unmute()
                if self._tts_speaking:
                    pixmap = QPixmap("images/images/TARS_female_speaking.png")
                    self.ui.tars_picture.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
                else:
                    pixmap = QPixmap("images/images/TARS_female.png")
                    self.ui.tars_picture.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
                self.ui.tars_picture.setPixmap(pixmap)
            else:
                # Mute
                self._tts_muted = True
                self.gui_agent.send_tts_stop()
                pixmap = QPixmap("images/images/tars_female_muted.png")
                self.ui.tars_picture.setPixmap(pixmap)
                self.ui.tars_picture.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.ui.tars_picture.mousePressEvent = _tars_picture_clicked
        
    # End of init
    # /////////////////////////////////////////////////////////////

    def _init_speech_log(self):
        """Replace tars_output_speech_label with the SpeechLogWidget chat panel."""
        layout = self.ui.row_1_col_1_container          # QVBoxLayout
        label  = self.ui.tars_output_speech_label       # QLabel to remove
        idx    = layout.indexOf(label)
        layout.removeWidget(label)
        label.hide()
        label.setParent(None)

        from widgets.speech_log import SpeechLogWidget
        self.speech_log = SpeechLogWidget(self.ui.row_1_col_1_container_2)
        self.speech_log.setMinimumSize(480, 180)
        # Expand horizontally so it fills the column nicely
        from PySide6.QtWidgets import QSizePolicy
        self.speech_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.insertWidget(idx, self.speech_log, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)

    def setup_page_connections(self):
        """
        Setup signal connections between MainWindow and pages
        """
        # Connect HomePage signals
        home_page = self.get_home_page()
        if home_page:
            home_page.task_done_signal.connect(self.handle_task_done)
            home_page.task_cancel_signal.connect(self.handle_task_cancel)
            home_page.task_allowed_signal.connect(self.handle_task_allowed)
            home_page.task_not_allowed_signal.connect(self.handle_task_not_allowed)
            home_page.countdown_zero_signal.connect(self.handle_countdown_zero)
        
        # Connect FlightPage signals (same handlers as HomePage)
        flight_page = self.get_flight_page()
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
        if home_page is not None:
            # Show tick mark for both performer and supporter tasks
            if state_obj.autonomy_role in ("performer", "supporter"):
                # Blue glow for performer/supporter tasks
                home_page.start_glow_effect(self.ui.current_task_container_3, "blue")
                
                # Get delay_after_action and convert to int for timer
                delay_after = state_obj.delay_after_action
                try:
                    if delay_after == "is_acked":
                        # Short tick (2 s) so spinner appears quickly while FSM waits on pilot ack
                        tick_duration = 2000
                    else:
                        delay_after_ms = int(float(delay_after) * 1000)
                        # Show tick for at least 3 seconds, or delay_after duration (whichever is longer)
                        tick_duration = max(3000, delay_after_ms) if delay_after_ms > 0 else 3000
                    
                    if home_page.current_circular_countdown is not None:
                        # After the tick mark, always start the spinner so the pilot
                        # sees the agent is now waiting for the transition condition.
                        if state_obj.autonomy_role == "supporter":
                            home_page.current_circular_countdown.show_task_fired(tick_duration, then_spin=True)
                        else:
                            home_page.current_circular_countdown.schedule_task_fired(1000, tick_duration, then_spin=True)
                except (ValueError, TypeError):
                    # If conversion fails, show for default 3 seconds
                    if home_page.current_circular_countdown is not None:
                        if state_obj.autonomy_role == "supporter":
                            home_page.current_circular_countdown.show_task_fired(3000, then_spin=True)
                        else:
                            home_page.current_circular_countdown.schedule_task_fired(1000, 3000, then_spin=True)
            elif state_obj.delay_after_action == "is_acked":
                # State with no/empty autonomy_role but FSM waits for pilot ack after the action —
                # show spinner directly (countdown has already finished at this point)
                if home_page.current_circular_countdown is not None:
                    home_page.current_circular_countdown.show()
                    home_page.current_circular_countdown.set_spinning()

            # Start next task countdown with delay_after_action of the current state
            flight_page = self.get_flight_page()
            delay_after = state_obj.delay_after_action
            try:
                if delay_after == "is_acked":
                    if home_page.next_circular_countdown is not None:
                        home_page.next_circular_countdown.show()
                        home_page.next_circular_countdown.set_na()
                    if flight_page and flight_page.next_circular_countdown is not None:
                        flight_page.next_circular_countdown.show()
                        flight_page.next_circular_countdown.set_na()
                    self.ui.n_t_s_value_2.setText("N/A")
                else:
                    delay_after_s = int(float(delay_after)) if delay_after else 0
                    if delay_after_s > 0:
                        self.ui.n_t_s_value_2.setText(str(delay_after_s))
                        if home_page.next_circular_countdown is not None:
                            home_page.next_circular_countdown.show()
                        home_page.start_next_countdown(delay_after_s)
                        if flight_page:
                            if flight_page.next_circular_countdown is not None:
                                flight_page.next_circular_countdown.show()
                            flight_page.start_next_countdown(delay_after_s)
                    else:
                        self.ui.n_t_s_value_2.setText("—")
            except (ValueError, TypeError):
                self.ui.n_t_s_value_2.setText("N/A")

    def get_home_page(self) -> HomePage | None:
        """
        Get the HomePage instance from page manager
        """
        page = self.page_manager.get_page('home')
        return page if isinstance(page, HomePage) else None
    
    def get_flight_page(self) -> FlightPage | None:
        """
        Get the FlightPage instance from page manager
        """
        page = self.page_manager.get_page('flight')
        return page if isinstance(page, FlightPage) else None
    
    def refresh_task_timeline_data(self):
        """
        Refresh task timeline data from agent - call when agent data is updated
        """
        home_page = self.get_home_page()
        if home_page:
            home_page.refresh_task_timeline_data()

    @QtCore.Slot(str)
    def on_allocation_reloaded(self, csv_filename: str):
        """
        Called when TARS fully reloaded its task allocation from a new CSV.
        Reload the local agent stub and refresh the timeline in the GUI.
        """
        from pathlib import Path as _Path
        csv_path = _Path(__file__).parent / "Core" / csv_filename
        if not csv_path.exists():
            print(f"⚠️ on_allocation_reloaded: CSV not found locally: {csv_path}")
            return
        try:
            self.agent.states = self.agent.create_states_from_csv(csv_path)
            self.agent.checklists = self.agent.create_checklists_from_states(self.agent.states)
            self.agent.CURRENT_BRIEFING_EXPORT_LOADED = csv_filename
            print(f"✅ GUI reloaded allocation: '{csv_filename}' ({len(self.agent.states)} states)")
            self.refresh_task_timeline_data()
        except Exception as e:
            print(f"❌ on_allocation_reloaded failed: {e}")
    
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
        self._tts_speaking = True
        pixmap = QPixmap("images/images/TARS_female_speaking.png")
        self.ui.tars_picture.setPixmap(pixmap)
        self.ui.tars_picture.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        # Append to the speech log (right-aligned, blue)
        if hasattr(self, 'speech_log'):
            self.speech_log.append_tars_message(text)
    
    @QtCore.Slot(bool)
    def on_stt_listening(self, is_listening):
        """Handle STT listening status change"""
        print(f"🎧 STT Listening: {is_listening}")  # Debug
        if is_listening:
            # Show listening image when STT is active
            pixmap = QPixmap("images/images/TARS_female_listening.png")
            self.ui.tars_picture.setPixmap(pixmap)
        else:
            # Return to muted image if muted, otherwise default
            if self._tts_muted:
                pixmap = QPixmap("images/images/tars_female_muted.png")
            else:
                pixmap = QPixmap("images/images/TARS_female.png")
            self.ui.tars_picture.setPixmap(pixmap)
    
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
    def on_atc_speech(self, text):
        """Handle ATC speech output for display in the speech log."""
        print(f"📻 ATC Speech: {text}")
        if hasattr(self, 'speech_log'):
            self.speech_log.append_atc_message(text)

    @QtCore.Slot(str)
    def on_pilot_speech(self, text):
        """Handle pilot STT recognized text for display in the speech log."""
        print(f"🎙️ Pilot speech: {text}")
        if hasattr(self, 'speech_log'):
            self.speech_log.append_pilot_message(text)

    @QtCore.Slot(str)
    def on_state_divider(self, label):
        """Insert a state-transition divider in the speech log."""
        if hasattr(self, 'speech_log'):
            self.speech_log.append_state_divider(label)

    @QtCore.Slot()
    def reset_speech_log(self):
        """Clear the speech log (called on TARS agent reset)."""
        if hasattr(self, 'speech_log'):
            self.speech_log.clear_log()

    @QtCore.Slot(str)
    def on_tars_status(self, text: str):
        """Update the TARS status label from any thread via signal."""
        self.ui.tars_status_label.setText(text)

    @QtCore.Slot(str)
    def on_tts_finished(self, text):
        print(f"✅ TTS Finished: {text}")  # Debug
        self._tts_speaking = False
        if self._tts_muted:
            pixmap = QPixmap("images/images/tars_female_muted.png")
            self.ui.tars_picture.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        else:
            pixmap = QPixmap("images/images/TARS_female.png")
            self.ui.tars_picture.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
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
            if t is None:  # Skip None transitions
                continue
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

        if home_page is None or flight_page is None:
            print("⚠️ HomePage or FlightPage not found, cannot update state")
            return
        
        # Stop timers on both pages
        if home_page.current_countdown_timer is not None:
            home_page.current_countdown_timer.stop()
        if home_page.next_countdown_timer is not None:
            home_page.next_countdown_timer.stop()
        if flight_page.current_countdown_timer is not None:
            flight_page.current_countdown_timer.stop()
        if flight_page.next_countdown_timer is not None:
            flight_page.next_countdown_timer.stop()
        
        home_page.set_checklist_label_passed(previous_state_obj.procedure, previous_state_obj.task_object, previous_state_obj.value, getattr(previous_state_obj, 'autonomy_role', None)) if previous_state_obj else None

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
            # Human task with no numeric delay - show spinner (agent waiting for pilot)
            if home_page.current_circular_countdown:
                home_page.current_circular_countdown.show()
                home_page.current_circular_countdown.set_spinning()
            if flight_page.current_circular_countdown:
                flight_page.current_circular_countdown.show()
                flight_page.current_circular_countdown.set_spinning()
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

        # Reset next task counter on state change — started by handle_action_about_to_fire
        if home_page.next_circular_countdown is not None:
            home_page.next_circular_countdown.hide()
        home_page.next_countdown_value = 0
        if flight_page.next_circular_countdown is not None:
            flight_page.next_circular_countdown.hide()
        flight_page.next_countdown_value = 0
        self.ui.n_t_s_value_2.setText("—")

        # Update UI labels (home page)
        self.ui.p_g_2.setText(previous_procedure_text)
        self.ui.p_t_2.setText(previous_task_text)
        self.ui.c_g_2.setText(current_procedure_text)
        self.ui.c_t_2.setText(current_task_text)
        self.ui.n_g_label_2.setText(next_procedure_text)
        self.ui.n_t_label_2.setText(next_task_text)
        self.ui.alert_label_2.setText(f"{current_procedure_text}")
        
        # Update UI labels (flight page)
        self.ui.p_g_flight.setText(previous_procedure_text)
        self.ui.p_t_flight.setText(previous_task_text)
        self.ui.n_g_label_flight.setText(next_procedure_text)
        self.ui.n_t_label_flight.setText(next_task_text)
        self.ui.alert_label_flight.setText(f"{current_procedure_text}")
        
        # Handle previous task autonomy role display (home page)
        if previous_state_obj is not None:
            if previous_state_obj.autonomy_role == "performer":
                home_page.show_label(self.ui.p_t_prog_widget_2)
                home_page.hide_label(self.ui.p_t_pilot_icon)
            elif previous_state_obj.autonomy_role == "supporter":
                home_page.hide_label(self.ui.p_t_prog_widget_2)
                home_page.hide_label(self.ui.p_t_pilot_icon)
            else:
                home_page.show_label(self.ui.p_t_pilot_icon)
                home_page.hide_label(self.ui.p_t_prog_widget_2)
        else:
            home_page.hide_label(self.ui.p_t_prog_widget_2)
            home_page.hide_label(self.ui.p_t_pilot_icon)
        
        # Handle previous task autonomy role display (flight page)
        if previous_state_obj is not None:
            if previous_state_obj.autonomy_role == "performer":
                # TARS is performer - show TARS icon, hide human icon
                self.ui.p_t_tars_icon_flight.show()
                self.ui.p_t_human_pilot_icon_flight.hide()
            elif previous_state_obj.autonomy_role == "supporter":
                # TARS is only supporting - hide both icons
                self.ui.p_t_tars_icon_flight.hide()
                self.ui.p_t_human_pilot_icon_flight.hide()
            else:
                # Human performs - show human icon, hide TARS icon
                self.ui.p_t_human_pilot_icon_flight.show()
                self.ui.p_t_tars_icon_flight.hide()
        else:
            # No previous task - hide both icons
            self.ui.p_t_tars_icon_flight.hide()
            self.ui.p_t_human_pilot_icon_flight.hide()
        

        self.remove_glow(self.ui.current_task_container_3)

        # Handle current task autonomy role display and buttons (home page)
        if current_state_obj.autonomy_role != "performer" and current_state_obj.autonomy_role != "supporter":
            home_page.show_label(self.ui.c_t_pilot_icon)
            home_page.hide_label(self.ui.c_t_prog_widget_2)
            home_page.hide_button(self.ui.cancel_task_button_2)
        elif current_state_obj.autonomy_role == "performer" :
            home_page.show_label(self.ui.c_t_prog_widget_2)
            home_page.hide_label(self.ui.c_t_pilot_icon)
            # Only reset button style if it's currently hidden (new task starting)
            if not self.ui.cancel_task_button_2.isVisible():
                home_page.show_button(self.ui.cancel_task_button_2, "red")
        elif current_state_obj.autonomy_role == "supporter" :
            home_page.hide_label(self.ui.c_t_prog_widget_2)
            home_page.hide_label(self.ui.c_t_pilot_icon)
            # Only reset button style if it's currently hidden (new task starting)
            if not self.ui.cancel_task_button_2.isVisible():
                home_page.show_button(self.ui.cancel_task_button_2, "red")
        
        # Handle current task autonomy role display (flight page)
        if current_state_obj.autonomy_role != "performer" and current_state_obj.autonomy_role != "supporter":
            self.ui.c_t_human_pilot_icon_flight.show()
            self.ui.c_t_tars_icon_flight.hide()
        if current_state_obj.autonomy_role == "performer":
            # TARS is performer - show TARS icon, hide human icon
            self.ui.c_t_tars_icon_flight.show()
            self.ui.c_t_human_pilot_icon_flight.hide()
        elif current_state_obj.autonomy_role == "supporter":
            # TARS is only supporting - hide both icons
            self.ui.c_t_human_pilot_icon_flight.hide()
            self.ui.c_t_tars_icon_flight.hide()

        # Handle next task autonomy role display (home page)
        if next_state_obj is not None:
            if next_state_obj.autonomy_role != "performer" and next_state_obj.autonomy_role != "supporter":
                home_page.hide_label(self.ui.n_t_prog_widget_2)
                home_page.show_label(self.ui.n_t_pilot_icon)
            elif next_state_obj.autonomy_role == "performer" :
                home_page.show_label(self.ui.n_t_prog_widget_2)
                home_page.hide_label(self.ui.n_t_pilot_icon)
            elif next_state_obj.autonomy_role == "supporter" :
                home_page.hide_label(self.ui.n_t_prog_widget_2)
                home_page.hide_label(self.ui.n_t_pilot_icon)
        else:
            home_page.hide_label(self.ui.n_t_prog_widget_2)
            home_page.hide_label(self.ui.n_t_pilot_icon)
        
        # Handle next task autonomy role display (flight page)
        if next_state_obj is not None:
            if next_state_obj.autonomy_role != "performer" and next_state_obj.autonomy_role != "supporter":
                self.ui.n_t_human_pilot_icon_flight.show()
                self.ui.n_t_tars_icon_flight.hide()
            elif next_state_obj.autonomy_role == "performer":
                self.ui.n_t_tars_icon_flight.show()
                self.ui.n_t_human_pilot_icon_flight.hide()
            elif next_state_obj.autonomy_role == "supporter":
                # TARS is only supporting - hide both icons
                self.ui.n_t_human_pilot_icon_flight.hide()
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
            home_page.show_button(self.ui.int_panel_right_button, "green")
            flight_page.show_button(self.ui.int_panel_right_button_flight, "green")
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
            self.ui.int_panel_right_button.setText("CHECK")
            #self.ui.int_panel_right_button_flight.hide()
            self.ui.int_panel_right_button_flight.setText("CHECK")
            self.ui.int_panel_left_button.hide()
            self.ui.int_panel_left_button_flight.hide()
    
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
        if not isinstance(btn, QPushButton):
            return
        btnName = btn.objectName()

        # SHOW BRIEFING PAGE
        if btnName == "btn_briefing":
            # Use page manager for briefing page
            self.page_manager.navigate_to_page('briefing')
            UIFunctions.resetStyle(self, btnName) # type: ignore
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet())) # type: ignore
        # SHOW HOME PAGE
        if btnName == "btn_home":
            # Use page manager for home page
            self.page_manager.navigate_to_page('home')
            UIFunctions.resetStyle(self, btnName) # type: ignore
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet())) # type: ignore

        # SHOW WIDGETS PAGE
        if btnName == "btn_widgets":
            if widgets is not None:
                widgets.stackedWidget.setCurrentWidget(widgets.widgets)
                UIFunctions.resetStyle(self, btnName) # type: ignore
                btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet())) # type: ignore
        # SHOW NEW PAGE
        if btnName == "btn_flight":
            if widgets is not None:
                widgets.stackedWidget.setCurrentWidget(widgets.flight)
                self.page_manager.navigate_to_page('flight')
                UIFunctions.resetStyle(self, btnName) # type: ignore
                btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet())) # type: ignore
    # //////////////////////////////////////////////////////////////

    # RESIZE EVENTS
    # ///////////////////////////////////////////////////////////////
    def resizeEvent(self, event):
        # Update Size Grips
        UIFunctions.resize_grips(self) # type: ignore

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
            if not self.stt_process or not self.stt_process.stdout:
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
            if not self.tars_process or not self.tars_process.stdout:
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
            if not self.atc_process or not self.atc_process.stdout:
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
    
    def start_tts_subprocess(self):
        """Start the TTS (Text-to-Speech) agent as a subprocess"""
        try:
            # Get path to tts_agent.py
            project_root = Path(__file__).parent
            tts_script = project_root / "tts" / "tts_agent.py"
            
            if not tts_script.exists():
                print(f"⚠️  TTS script not found at {tts_script}")
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
            # TTS agent needs: agent_name, network_device, port
            self.tts_process = subprocess.Popen(
                [str(python_exe), "-u", str(tts_script), "TTS_Agent", "wlp0s20f3", "5670"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout
                text=True,
                encoding='utf-8',
                bufsize=1,
                cwd=str(project_root)
            )
            
            print(f"🔊 TTS subprocess started (PID: {self.tts_process.pid})")
            
            # Start monitoring thread to read output and check if process crashes
            self.start_tts_monitor()
            
        except Exception as e:
            print(f"❌ Failed to start TTS subprocess: {e}")
            import traceback
            traceback.print_exc()
            self.tts_process = None
    
    def start_tts_monitor(self):
        """Start a background thread to monitor TTS subprocess output and health"""
        def monitor_tts():
            if not self.tts_process or not self.tts_process.stdout:
                return
            
            print("📊 TTS monitor thread started")
            try:
                # Read output line by line
                for line in iter(self.tts_process.stdout.readline, ''):
                    if line:
                        print(f"[TTS] {line.rstrip()}")
                    
                    # Check if process is still running
                    if self.tts_process.poll() is not None:
                        break
                
                # Process has exited
                exit_code = self.tts_process.poll()
                if exit_code != 0:
                    print(f"⚠️  TTS subprocess crashed with exit code {exit_code}")
                    # Optionally restart
                    # QtCore.QTimer.singleShot(2000, self.start_tts_subprocess)
                else:
                    print("✅ TTS subprocess exited normally")
                    
            except Exception as e:
                print(f"❌ Error in TTS monitor thread: {e}")
                import traceback
                traceback.print_exc()
        
        # Start monitor in background thread
        monitor_thread = threading.Thread(target=monitor_tts, daemon=True)
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
    
    def stop_tts_subprocess(self):
        """Stop the TTS subprocess gracefully"""
        if self.tts_process:
            try:
                print("🛑 Stopping TTS subprocess...")
                self.tts_process.terminate()  # Send SIGTERM
                try:
                    self.tts_process.wait(timeout=5)  # Wait up to 5 seconds
                    print("✅ TTS subprocess stopped")
                except subprocess.TimeoutExpired:
                    print("⚠️  TTS subprocess didn't stop gracefully, forcing...")
                    self.tts_process.kill()  # Force kill
                    self.tts_process.wait()
                    print("✅ TTS subprocess killed")
            except Exception as e:
                print(f"❌ Error stopping TTS subprocess: {e}")
            finally:
                self.tts_process = None
    
    def closeEvent(self, event):
        """Override close event to cleanup subprocess"""
        print("Closing application...")
        
        # Stop TARS Agent subprocess
        self.stop_tars_subprocess()
        
        # Stop STT subprocess
        self.stop_stt_subprocess()
        
        # Stop ATC subprocess
        self.stop_atc_subprocess()
        
        # Stop TTS subprocess
        self.stop_tts_subprocess()
        
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
