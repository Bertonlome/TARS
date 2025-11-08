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
from Core.agent import TarsAgent
from Core.tts import shutdown, register_speak_callback, register_finished_callback
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

# FSM Worker
# ///////////////////////////////////////////////////////////////
class FSMWorker(QtCore.QObject):
    state_changed = QtCore.Signal(object)  # Changed from str to object to emit State object
    action_about_to_fire = QtCore.Signal(object)  # Emitted right before action executes (after countdown)
    condition_violated_signal = QtCore.Signal(object, str)  # (state, condition_name) - condition now False
    condition_restored_signal = QtCore.Signal(object, str)  # (state, condition_name) - condition now True
    current_state = None

    def __init__(self, agent: TarsAgent):
        super().__init__()
        self.agent = agent
        # Performance monitoring
        self.performance_metrics = {}
        self.loop_count = 0
        self.last_performance_report = time.perf_counter()
        # Action inhibition flag
        self.skip_current_action = False
        
        # Active condition monitoring registry
        # Dict: state_key -> monitoring_info
        self.active_monitored_conditions = {}
        self.current_procedure = None  # Track current procedure for scope management

    def start_performance_timer(self, action_name):
        """Start timing for a specific action"""
        return time.perf_counter()

    def stop_performance_timer(self, action_name, start_time):
        """Stop timing and record the result"""
        elapsed = time.perf_counter() - start_time
        if action_name not in self.performance_metrics:
            self.performance_metrics[action_name] = []
        self.performance_metrics[action_name].append(elapsed)
        return elapsed

    def print_performance_report(self):
        """Print performance report every 10 seconds"""
        print(f"\n=== FSM Performance Report (Loops: {self.loop_count}) ===")
        for action, times in self.performance_metrics.items():
            if times:
                avg_time = sum(times) / len(times)
                print(f"{action}: avg={avg_time*1000:.2f}ms, count={len(times)}, min={min(times)*1000:.2f}ms, max={max(times)*1000:.2f}ms")
        
        # Reset counters
        self.performance_metrics.clear()
        self.loop_count = 0
    
    @QtCore.Slot()
    def cancel_current_action(self):
        """Slot to cancel/skip the current action execution"""
        self.skip_current_action = True
        print(f"Current action inhibited - user reclaimed task")
    
    def add_to_monitoring(self, state):
        """Add state to continuous condition monitoring"""
        # Only monitor states with 'continuous' condition type
        if state.condition_type != 'continuous' or not state.condition_function:
            return
        
        state_key = (state.procedure, state.task_object, state.value)
        
        # Get condition function by name from agent
        try:
            condition_func = getattr(self.agent, state.condition_function)
        except AttributeError:
            print(f"Warning: Condition function '{state.condition_function}' not found in agent")
            return
        
        # Evaluate initial value
        try:
            initial_value = condition_func()
        except Exception as e:
            print(f"Error evaluating initial condition {state.condition_function}: {e}")
            initial_value = None
        
        # Set state.condition to initial value
        state.condition = initial_value
        
        self.active_monitored_conditions[state_key] = {
            'state': state,
            'condition_func_name': state.condition_function,
            'condition_func': condition_func,
            'last_value': initial_value,
            'monitor_scope': state.monitor_scope,
            'procedure': state.procedure
        }
        
        print(f"📊 Monitoring: {state.procedure} - {state.task_object} - {state.condition_function} = {initial_value}")
    
    def remove_from_monitoring(self, state_key):
        """Stop monitoring a condition"""
        if state_key in self.active_monitored_conditions:
            monitor_info = self.active_monitored_conditions[state_key]
            print(f"🛑 Stop monitoring: {monitor_info['procedure']} - {monitor_info['state'].task_object}")
            del self.active_monitored_conditions[state_key]
    
    def cleanup_monitoring_for_scope(self, scope_type, current_state):
        """Remove conditions from monitoring based on scope"""
        to_remove = []
        
        for state_key, monitor_info in self.active_monitored_conditions.items():
            monitor_scope = monitor_info['monitor_scope']
            
            if scope_type == 'next_task' and monitor_scope == 'next_task':
                # Remove conditions that should only be monitored until next task
                to_remove.append(state_key)
            
            elif scope_type == 'procedure_change':
                # Remove conditions when procedure changes
                if monitor_scope == 'end_of_procedure' and monitor_info['procedure'] != current_state.procedure:
                    to_remove.append(state_key)
        
        for state_key in to_remove:
            self.remove_from_monitoring(state_key)

    @QtCore.Slot()
    def run(self):
        fsm = self.agent.fsm
        loop_start_time = time.perf_counter()
        
        while not self.agent.is_interrupted:
            # Performance monitoring
            self.loop_count += 1
            current_time = time.perf_counter()
            
            # Print performance report every 10 seconds
            if current_time - self.last_performance_report >= 10.0:
                #self.print_performance_report()
                self.last_performance_report = current_time

            # Check transitions with performance timing
            transition_start = self.start_performance_timer("transition_check")
            transition_found = False
            
            for t in fsm.transitions:
                if t.from_state == fsm.current_state:
                    # Time the condition check
                    condition_start = self.start_performance_timer("condition_check")
                    condition_result = t.condition()
                    condition_time = self.stop_performance_timer("condition_check", condition_start)
                    
                    # Log slow conditions
                    if condition_time > 0.1:  # 100ms threshold
                        print(f"WARNING: Slow condition check for {t.from_state.procedure} {t.from_state.task_object} {t.from_state.value} -> {t.to_state.procedure} {t.to_state.task_object} {t.to_state.value}: {condition_time*1000:.2f}ms")
                    
                    if condition_result:
                        # State transition
                        transition_time = self.stop_performance_timer("transition_check", transition_start)
                        print(f"State transition: {fsm.current_state.procedure} {fsm.current_state.task_object} {fsm.current_state.value} -> {t.to_state.procedure} {t.to_state.task_object} {t.to_state.value} (check took {transition_time*1000:.2f}ms)")
                        
                        # CONDITION MONITORING: Cleanup for 'next_task' scope
                        self.cleanup_monitoring_for_scope('next_task', t.to_state)
                        
                        # CONDITION MONITORING: Check if procedure changed
                        if self.current_procedure and self.current_procedure != t.to_state.procedure:
                            self.cleanup_monitoring_for_scope('procedure_change', t.to_state)
                        
                        self.current_procedure = t.to_state.procedure
                        
                        fsm.current_state = t.to_state
                        self.state_changed.emit(fsm.current_state)  # Emit the State object instead of just procedure
                        self.current_state = fsm.current_state
                        
                        # CONDITION MONITORING: Add new state to monitoring if it has continuous condition
                        self.add_to_monitoring(fsm.current_state)
                        
                        # wait before action - wait for countdown timer to reach 0
                        delay = self.get_delay_before_action(fsm.current_state)
                        if delay > 0:
                            # Clear the event before waiting
                            self.agent.main_window.countdown_completion_event.clear()
                            #print(f"⏳ Waiting for countdown to reach 0...")
                            # Wait for the countdown timer to signal completion
                            self.agent.main_window.countdown_completion_event.wait(timeout=delay + 2)  # +2s safety margin
                        
                        # Only emit signal if action is not being skipped
                        if not self.skip_current_action:
                            # Emit signal right before action fires (after countdown completes)
                            self.action_about_to_fire.emit(fsm.current_state)
                        
                        if t.action:
                            # Check if action should be skipped (user cancelled)
                            if self.skip_current_action:
                                print(f"⏭️ Skipping action for {fsm.current_state.task_object} - user reclaimed task")
                                self.skip_current_action = False  # Reset flag
                                action_result = False  # No TTS to wait for
                            else:
                                action_start = self.start_performance_timer("action_execution")
                                action_result = t.action()
                                action_time = self.stop_performance_timer("action_execution", action_start)
                                print(f"Action execution took: {action_time*1000:.2f}ms")
                            
                            # If it was a speech action, wait for TTS to complete
                            if action_result is True and self.agent.tts_completion_event:
                                # Give TTS worker a moment to pick up the queued text and clear the event
                                #QtCore.QThread.msleep(50)  # Small delay for queue processing
                                
                                #print(f"⏳ Waiting for TTS to complete (event is_set={self.agent.tts_completion_event.is_set()})...")
                                wait_start = time.time()
                                self.agent.tts_completion_event.wait(timeout=30)  # Block until TTS finishes (30s max)
                                wait_time = time.time() - wait_start
                                #print(f"✅ TTS completed after {wait_time:.2f}s, continuing FSM")
                        
                        # wait after action
                        delay = self.get_delay_after_action(fsm.current_state)
                        if delay and delay > 0:
                            QtCore.QThread.msleep(float((delay + 0.2) * 1000)) # + 0.2 delay for UI
                        
                        transition_found = True
                        break
            
            if not transition_found:
                self.stop_performance_timer("transition_check", transition_start)
            
            # CRITICAL FIX: Add a small sleep to prevent tight loop
            # This allows other threads (like network updates) to run
            QtCore.QThread.msleep(50)  # 50ms sleep = 20 checks per second instead of thousands
            
            # Alternative: Use processEvents to allow other operations
            # QtCore.QCoreApplication.processEvents()
            
    def get_delay_before_action(self, state):
        delay = getattr(state, "delay_before_action", 0)
        if delay is None:
            delay = 0
        elif isinstance(delay, str):
            if delay.lower() == 'is_acked':
                # Acknowledgment-based waiting - return 0, will be handled by UI
                #print(f"State ({state.procedure}, {state.task_object}, {state.value}) requires acknowledgment before action")
                delay = 0
            else:
                try:
                    delay = float(delay)
                except ValueError:
                    delay = 0
        if delay and delay > 0:
            print(f"waiting for {delay} seconds before executing action for state ({state.procedure}, {state.task_object}, {state.value})")
        return delay
    
    def get_delay_after_action(self, state):
        delay = getattr(state, "delay_after_action", 0)
        if delay is None:
            delay = 0
        elif isinstance(delay, str):
            if delay.lower() == 'is_acked':
                # Acknowledgment-based waiting - return 0, will be handled by UI
                #print(f"State ({state.procedure}, {state.task_object}, {state.value}) requires acknowledgment after action")
                delay = 0
            else:
                try:
                    delay = float(delay)
                except ValueError:
                    delay = 0
        if delay and delay > 0:
            print(f"waiting for {delay} seconds after executing action for state ({state.procedure}, {state.task_object}, {state.value})")
        return delay
            
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
        
        self.agent = TarsAgent()
        signal.signal(signal.SIGINT, self.agent.signal_handler)
        self.ui.tars_status_label.setText(f"{self.agent.agent_name} RUNNING")
        
        # Give agent reference to main window for countdown synchronization
        self.agent.main_window = self
        
        # Start the agent in a separate thread
        self.agent_thread = AgentThread(self.agent)
        self.agent_thread.start()
        
        
        # FSM Worker in a thread
        self.fsm_thread = QtCore.QThread()
        self.fsm_worker = FSMWorker(self.agent)
        self.fsm_worker.moveToThread(self.fsm_thread)
        self.fsm_worker.state_changed.connect(self.update_state)
        self.fsm_worker.action_about_to_fire.connect(self.handle_action_about_to_fire)
        self.fsm_worker.condition_violated_signal.connect(self.handle_condition_violation)
        self.fsm_worker.condition_restored_signal.connect(self.handle_condition_restoration)
        self.fsm_thread.started.connect(self.fsm_worker.run)
        self.fsm_thread.start()
        self.current_state = None
        self.previous_state = None
        self.next_state = None

        # TTS completion tracking - shared between agent and main window
        self.tts_completion_event = threading.Event()
        self.tts_completion_event.set()  # Initially set (ready - no speech in progress)
        # The event will be cleared when TTS starts speaking, set when it finishes
        self.agent.set_tts_completion_event(self.tts_completion_event)

        # Countdown completion tracking - for synchronizing FSM with countdown timer
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
            
            # Connect agent alert signals to home page
            if hasattr(self, 'agent') and self.agent:
                self.agent.alertRequested.connect(home_page.displayAlert)
    
    def handle_task_done(self):
        """
        Handle task done signal from HomePage
        """
        # This is where MainWindow handles the task completion
        # Update agent state
        self.agent.task_done_human[0] = True
        print("Task marked as done\n\n")
    
    def handle_task_cancel(self):
        """
        Handle task cancel signal from HomePage  
        """
        # Signal FSM worker to skip the current action
        print("⚠️ Task cancelled by user - inhibiting action")
        self.fsm_worker.cancel_current_action()
        # Signal FSM to continue (don't wait for countdown)
        self.countdown_completion_event.set()

    def handle_task_allowed(self):
        """
        Handle task allowed signal from HomePage  
        """
        self.agent.is_allowed_to_comm_atc[0] = True
        self.agent.is_requesting_vectors[0] = True
    
    def handle_task_not_allowed(self):
        """
        Handle task not allowed signal from HomePage  
        """
        self.agent.is_allowed_to_comm_atc[0] = False
        self.agent.is_requesting_vectors[0] = False
    
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
        print(f"🚨 CONDITION VIOLATION: {state_obj.procedure} - {state_obj.task_object} - {condition_name}")
        
        # Get home page
        home_page = self.get_home_page()
        if not home_page:
            return
        
        # Update timeline to show violation
        timeline_widget = home_page.task_timeline_widgets.get(state_obj.procedure)
        if timeline_widget:
            state_key = (state_obj.procedure, state_obj.task_object, state_obj.value)
            # TODO: Add method to timeline widget to mark task as violated
            # timeline_widget.mark_task_violated(state_key)
            print(f"  → Would mark task violated in timeline for procedure {state_obj.procedure}")
        
        # TODO: Show warning banner or notification
        # home_page.show_warning_banner(f"⚠️ {state_obj.task_object} - condition violated!")
    
    @QtCore.Slot(object, str)
    def handle_condition_restoration(self, state_obj, condition_name):
        """Handle condition restoration signal from FSM worker
        
        Args:
            state_obj: State object with restored condition
            condition_name: Name of the condition function that was restored
        """
        print(f"✅ CONDITION RESTORED: {state_obj.procedure} - {state_obj.task_object} - {condition_name}")
        
        # Get home page
        home_page = self.get_home_page()
        if not home_page:
            return
        
        # Update timeline to show restoration
        timeline_widget = home_page.task_timeline_widgets.get(state_obj.procedure)
        if timeline_widget:
            state_key = (state_obj.procedure, state_obj.task_object, state_obj.value)
            # TODO: Add method to timeline widget to mark task as restored
            # timeline_widget.mark_task_restored(state_key)
            print(f"  → Would mark task restored in timeline for procedure {state_obj.procedure}")
        
        # TODO: Clear warning banner or show restoration notification
        # home_page.clear_warning_banner()
    
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
        home_page.current_countdown_timer.stop()
        home_page.next_countdown_timer.stop()
        home_page.set_checklist_label_passed(previous_state_obj.procedure, previous_state_obj.task_object, previous_state_obj.value) if previous_state_obj else None

        home_page.reset_radio_button(self.ui.check_radio_button)
        home_page.connect_int_panel_buttons()
        self.ui.c_t_s_unit_2.hide()
        self.ui.c_t_s_value_2.hide()

        self.ui.interaction_panel_tars_input.hide()
        
        # For current task counter (uses delay_before_action)
        if current_state_obj.autonomy_role != "performer":
            # Human task - hide the circular countdown but keep timeline animations
            if home_page.current_circular_countdown:
                home_page.current_circular_countdown.hide()
            # Handle human task (immediate completion of animations, no countdown)
            home_page.handle_human_task()
            # Update UI text for human tasks
            self.ui.c_t_s_value_2.setText("Human")
        else:
            # TARS task - show the circular countdown and start countdown
            if home_page.current_circular_countdown:
                home_page.current_circular_countdown.show()
            try:
                seconds = int(current_state_obj.delay_before_action) if current_state_obj.delay_before_action else 0
                print(f"\nDelay_before_action for task {current_state_obj.task_object}: {seconds} seconds")
                self.ui.c_t_s_value_2.setText(str(seconds))
                if seconds > 0:
                    home_page.start_current_countdown(seconds)  # Use the proper method
                else:
                    # For 0-second TARS tasks, initialize and immediately complete the animation
                    home_page.current_countdown_value = 0
                    home_page.current_countdown_max = 1  # Set a default for progress calculation
                    if home_page.current_circular_countdown:
                        home_page.current_circular_countdown.set_value(0, 0)
                    
                    # Initialize task border animation and immediately complete it
                    timeline_widget = home_page.get_current_timeline_widget()
                    if timeline_widget:
                        # Directly set both target and current progress to 1.0 (no animation)
                        timeline_widget._target_task_progress = 1.0
                        timeline_widget._current_task_progress = 1.0
                        # Force a repaint to show the blue border immediately
                        timeline_widget.update()
                        # Mark task as complete and prepare connection animation
                        timeline_widget.complete_current_task()
                        # The connection animation progress will be driven by next_countdown timer
                        # Calculate current connection progress based on how much next_countdown has elapsed
                        if home_page.next_countdown_max > 0 and home_page.next_countdown_value < home_page.next_countdown_max:
                            elapsed_progress = 1.0 - (home_page.next_countdown_value / home_page.next_countdown_max)
                            timeline_widget.set_connection_progress(elapsed_progress)
                        else:
                            # Next countdown hasn't started yet or just started
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
                        home_page.start_next_countdown(total_seconds)  # Use the proper method
                    else:
                        home_page.next_countdown_value = 0
            else:
                self.ui.n_t_s_value_2.setText("N/A")
        except (ValueError, TypeError, AttributeError) as e:
            print(f"Error calculating next task countdown: {e}")
            home_page.next_countdown_timer.stop()
            self.ui.n_t_s_value_2.setText("N/A")

        # Update UI labels
        self.ui.p_g_2.setText(previous_procedure_text)
        self.ui.p_t_2.setText(previous_task_text)
        self.ui.c_g_2.setText(current_procedure_text)
        self.ui.c_t_2.setText(current_task_text)
        self.ui.n_g_label_2.setText(next_procedure_text)
        self.ui.n_t_label_2.setText(next_task_text)
        self.ui.alert_label_2.setText(f"{current_procedure_text}")
        
        # Handle previous task autonomy role display
        if previous_state_obj is not None:
            if previous_state_obj.autonomy_role != "performer":
                self.get_home_page().hide_label(self.ui.p_t_prog_widget_2)
            else:
                self.get_home_page().show_label(self.ui.p_t_prog_widget_2)
        else:
            self.ui.p_t_prog_widget_2.hide()
        
        self.remove_glow(self.ui.current_task_container_3)
        

        # Handle current task autonomy role display and buttons
        if current_state_obj.autonomy_role != "performer":
            self.get_home_page().hide_label(self.ui.c_t_prog_widget_2)
            self.remove_glow(self.ui.current_task_container_3)
            self.ui.cancel_task_button_2.hide()
        else:
            self.get_home_page().show_label(self.ui.c_t_prog_widget_2)
            # Only reset button style if it's currently hidden (new task starting)
            if not self.ui.cancel_task_button_2.isVisible():
                self.get_home_page().show_button(self.ui.cancel_task_button_2, "red")

        # Handle next task autonomy role display
        if next_state_obj is not None:
            if next_state_obj.autonomy_role != "performer":
                self.get_home_page().hide_label(self.ui.n_t_prog_widget_2)
            else:
                self.get_home_page().show_label(self.ui.n_t_prog_widget_2)
        else:
            self.ui.n_t_prog_widget_2.hide()
        
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
            self.ui.interaction_panel_text.setText(self.format_checklist_line(current_state_obj.task_object, current_state_obj.value))
            #if not self.ui.int_panel_right_button.isVisible() :
            self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
            if current_state_obj.autonomy_role == "performer":
                self.ui.int_panel_right_button.setText("CROSSCHECK")
            else:
                self.ui.int_panel_right_button.setText("CHECK")
            self.ui.int_panel_left_button.hide()
        else :
            self.ui.interaction_panel_text.setText(current_state_obj.task_object)
            self.ui.int_panel_right_button.hide()
            self.ui.int_panel_left_button.hide()
    
        # Handle interaction panel based on current state's interaction attribute
        if current_state_obj.interaction is not None and current_state_obj.interaction != "":
            #self.ui.int_panel_right_button.hide()
            #self.ui.int_panel_left_button.hide()
            match current_state_obj.interaction:
                case "engine_anti_ice_requirement":
                    self.ui.interaction_panel_tars_input.show()            
                    self.ui.interaction_panel_tars_input.setText("NO ICE CONDITIONS DETECTED")
                case "windshield_anti_ice_requirement":
                    self.ui.interaction_panel_tars_input.show()
                    self.ui.interaction_panel_tars_input.setText("NO ICE CONDITIONS DETECTED")
                case "anti_ice_systems_as_required":
                    self.ui.interaction_panel_tars_input.show()
                    self.ui.interaction_panel_text.setText(f"Anti-ice systems :\nEngine anti-ice - current value = {self.agent.engine_anti_ice_status}\nWindshield anti-ice - current value = {self.agent.windshield_anti_ice_status}")
                    self.ui.interaction_panel_tars_input.setText("NO ICE CONDITIONS DETECTED")
                case "landing_light_as_required":
                    self.ui.interaction_panel_tars_input.show()
                    self.ui.interaction_panel_tars_input.setText("On an active runway, to enhance visibility: LANDING LIGHTS ON")
                case "radar_requirement":
                    self.ui.interaction_panel_tars_input.show()
                    self.ui.interaction_panel_tars_input.setText("NO SPECIAL WEATHER CONDITIONS AS PER LAST METAR")
                case "display_winds_and_ack":
                    self.ui.interaction_panel_text.setText("Winds: \nWind calm\nWind 026° at 3 knots")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_right_button.setText("CROSSCHECK")
                case "failure_detected":
                    home_page.displayAlert(f"Failure detected: {self.agent.engine_failed_side} ENGINE FIRE", "red")
                case "end_emer":
                    self.ui.alert_container_3.setStyleSheet("QWidget#alert_container_3 {\n    border: 2px solid rgba(255, 174, 0, 255);\n    border-radius: 5px;\n    background-color: rgba(33, 37, 43, 255);\n}")
                    self.ui.alert_label_2.setText("")
                case "prompt_start_checklist":
                    self.ui.interaction_panel_text.setText(f"{current_state_obj.callout}?")
                    self.ui.int_panel_right_button.setText("START")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_left_button.setText("CANCEL")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                case "prompt_next_checklist":
                    self.ui.interaction_panel_text.setText(f"{current_state_obj.value}?")
                    self.ui.int_panel_right_button.setText("NEXT")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_left_button.setText("CANCEL")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                case "allow_comm":
                    home_page.connect_int_panel_buttons(default=False)
                    self.ui.interaction_panel_text.setText("Allow TARS to communicate with ATC?")
                    self.ui.interaction_panel_tars_input.setText(current_state_obj.callout)
                    self.ui.interaction_panel_tars_input.show()
                    self.ui.int_panel_right_button.setText("ALLOW")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_left_button.setText("DENY")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                case "add_request_vectors":
                    self.ui.interaction_panel_text.setText(f"Add request for vectors to return runway {self.agent.runway if self.agent.runway else 'unknown'}?")
                    self.ui.int_panel_right_button.setText("ALLOW")
                    self.ui.interaction_panel_tars_input.setText(previous_state_obj.callout + " " + current_state_obj.callout)
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_left_button.setText("DENY")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                case "display_trim_rudder":
                    self.ui.interaction_panel_text.setText(f"Current trim : {self.agent.trim_rudder} %")
                case "display_alarm":
                    self.ui.interaction_panel_text.setText("Alarm: Engine Fire")
                case "display_ATC_msg_and_buttons_mayday":
                    self.ui.interaction_panel_text.setText("ATC Message: Mayday, Mayday, Mayday, Montreal Tower, from Papa Oscar Lima Yankee, engine fire after takeoff due to bird strike")
                    if not self.ui.int_panel_right_button.isVisible(): self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_left_button.hide()
                    self.ui.int_panel_right_button.setText("Allow TARS to send Mayday message to ATC")
                case "display_engage_autopilot":
                    self.ui.interaction_panel_text.setText("Engage Autopilot: ")
                    if not self.ui.int_panel_right_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    if not self.ui.int_panel_left_button.isVisible() : self.get_home_page().show_button(self.ui.int_panel_left_button, "red")
                    self.ui.int_panel_right_button.setText("Engage")
                    self.ui.int_panel_left_button.setText("CANCEL")
                case "immediate_action_item":
                    self.ui.interaction_panel_text.setText(f"Immediate action item : \n1. Throttle {self.agent.engine_failed_side} engine throttle IDLE\n- IF LIGHT REMAINS ON (15 SECONDS)\nIlluminated ENGINE FIRE Switch LIFT COVER AND PUSH")
                case "display_checklist_emer_eng_fire_continue":
                    self.ui.interaction_panel_text.setText("Emergency Fire Checklist: ")
                    if not self.ui.int_panel_right_button.isVisible(): self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_right_button.setText("Continue")
                case "display_ATC_msg_and_buttons_panpan":
                    self.ui.interaction_panel_text.setText("ATC Message: PanpanPan-Pan, Pan-Pan, Pan-Pan, Montreal Tower, from Papa Oscar Lima Yankee, request vectors to return for landing with one engine.")
                    if not self.ui.int_panel_right_button.isVisible(): self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_left_button.hide()
                    self.ui.int_panel_right_button.setText("Allow TARS to send Panpan message to ATC")
                case "display_checklist_aft_takeoff_continue":
                    self.ui.interaction_panel_text.setText("After takeoff Checklist: ")
                    if not self.ui.int_panel_right_button.isVisible(): self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_right_button.setText("Continue")
                case "display_checklist_aft_takeoff":
                    self.ui.interaction_panel_text.setText("After takeoff Checklist: ")
                case "yaw_damper_as_desired":
                    self.ui.interaction_panel_tars_input.show()
                    if self.agent.engine_failed_side is not "None":
                        self.ui.interaction_panel_tars_input.setText("OFF for full rudder authority during single-engine operations")
                    else:
                        self.ui.interaction_panel_tars_input.setText("ON for comfort during normal operations")
                case "pax_safety_switch_as_required":
                    self.ui.interaction_panel_tars_input.show()
                    self.ui.interaction_panel_tars_input.setText("ABNORMAL SITUATION: PAX SAFETY Switch SET TO SEATBELT")
                case "display_alti_set_std":
                    self.ui.interaction_panel_text.setText("Setting altimeter to STD")
                case "display_checklist_eng_fail_proc_continue":
                    self.ui.interaction_panel_text.setText("Engine Failure Procedure")
                    if not self.ui.int_panel_right_button.isVisible(): self.get_home_page().show_button(self.ui.int_panel_right_button, "green")
                    self.ui.int_panel_right_button.setText("Continue")
                case "display_checklist_eng_fail_proc":
                    self.ui.interaction_panel_text.setText("Engine Failure Procedure")
                case "caution_text_readout":
                    self.ui.interaction_panel_text.setText("Caution: \nIf possible, the engines should remain at idle for a minimum of two minutes prior to shutdown to allow the engine inter-turbine temperature to stabilize and avoid turbine blade rub.\nIf the engine windmills for more than 15 minutes without a positive indication of oil pressure, a notation is required in the engine logbook and the engine must be inspected in accordance with the Pratt & Whitney engine maintenance manual.\nIf the engine windmills for more than 30 minutes with the firewall shutoff closed or the boost pump turned off, the engine fuel pump must be inspected in accordance with the Pratt & Whitney engine maintenance manual.")
                case "display_checklist_sing_eng_app":
                    self.ui.interaction_panel_text.setText("Single Engine Approach and Landing Checklist")
    
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
        if btnName == "btn_new":
            widgets.stackedWidget.setCurrentWidget(widgets.new_page) # SET PAGE
            UIFunctions.resetStyle(self, btnName) # RESET ANOTHERS BUTTONS SELECTED
            btn.setStyleSheet(UIFunctions.selectMenu(btn.styleSheet())) # SELECT MENU
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
        dash_count = max(2, total_width - len(left) - len(right))
        return f"{left}{dash_char * dash_count}{right}"


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
