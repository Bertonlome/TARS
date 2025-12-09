"""
GUI Agent - Ingescape wrapper for MainWindow
Bridges TARS Agent outputs to Qt UI updates and user actions to TARS inputs
"""

import sys
import json
from typing import Optional
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication

try:
    import ingescape as igs
except ImportError:
    print("ERROR: ingescape module not found")
    sys.exit(1)

from Core.message_protocol import decode_json_to_dict
from main import MainWindow


class GUIAgent(QObject):
    """
    GUI Agent - Ingescape agent that wraps MainWindow
    Subscribes to TARS outputs and translates them to UI updates
    Publishes user actions as TARS inputs
    """
    
    # Internal signals for thread-safe UI updates (Ingescape callbacks run in different thread)
    _alert_signal = Signal(str, str)  # (message, color)
    _clear_alert_signal = Signal()
    _interaction_message_signal = Signal(str, str)  # (message, tars_input)
    _state_changed_signal = Signal(dict)  # State dict from JSON
    _next_state_signal = Signal(dict)  # Next state dict from JSON
    _previous_state_signal = Signal(dict)  # Previous state dict from JSON
    _tts_speak_signal = Signal(str)  # TTS text being spoken
    _tts_finished_signal = Signal(str)  # TTS finished speaking
    
    def __init__(self, main_window: MainWindow, agent_name: str = "Shared Interface", 
                 device: str = "wlp0s20f3", port: int = 5670):
        super().__init__()
        self.main_window = main_window
        self.agent_name = agent_name
        self.device = device
        self.port = port
        
        # Connect internal signals to UI update methods
        self._alert_signal.connect(self._on_alert)
        self._clear_alert_signal.connect(self._on_clear_alert)
        self._interaction_message_signal.connect(self._on_interaction_message)
        self._state_changed_signal.connect(self._on_state_changed)
        self._next_state_signal.connect(self._on_next_state_changed)
        self._previous_state_signal.connect(self._on_previous_state_changed)
        self._tts_speak_signal.connect(self.main_window.on_tts_speak)
        self._tts_finished_signal.connect(self.main_window.on_tts_finished)
        
        # Connect MainWindow user action signals to TARS inputs
        self._connect_ui_to_tars()
        
        # Initialize Ingescape agent
        self._init_ingescape()
    
    def _init_ingescape(self):
        """Initialize Ingescape agent with inputs/outputs"""
        igs.agent_set_name(self.agent_name)
        igs.definition_set_version("1.0")
        igs.log_set_console(True)
        igs.log_set_file(True, None)
        igs.set_command_line(sys.executable + " " + " ".join(sys.argv))
        
        # Create inputs (subscribe to TARS outputs)
        igs.input_create("current_state", igs.STRING_T, None)
        igs.input_create("next_state", igs.STRING_T, None)
        igs.input_create("previous_state", igs.STRING_T, None)
        igs.input_create("countdown_current", igs.INTEGER_T, None)
        igs.input_create("countdown_next", igs.INTEGER_T, None)
        igs.input_create("countdown_max_current", igs.INTEGER_T, None)
        igs.input_create("countdown_max_next", igs.INTEGER_T, None)
        igs.input_create("alert", igs.STRING_T, None)
        igs.input_create("alert_clear", igs.IMPULSION_T, None)
        igs.input_create("condition_violated", igs.STRING_T, None)
        igs.input_create("condition_restored", igs.STRING_T, None)
        igs.input_create("tts_speaking", igs.BOOL_T, None)
        igs.input_create("tts_text", igs.STRING_T, None)
        igs.input_create("action_about_to_fire", igs.STRING_T, None)
        igs.input_create("checklist_item_complete", igs.STRING_T, None)
        igs.input_create("emergency_procedure_inject", igs.STRING_T, None)
        igs.input_create("interaction_message", igs.STRING_T, None)
        
        # Observe inputs
        igs.observe_input("current_state", self._on_current_state_input, None)
        igs.observe_input("next_state", self._on_next_state_input, None)
        igs.observe_input("previous_state", self._on_previous_state_input, None)
        igs.observe_input("countdown_current", self._on_countdown_current_input, None)
        igs.observe_input("countdown_next", self._on_countdown_next_input, None)
        igs.observe_input("countdown_max_current", self._on_countdown_max_current_input, None)
        igs.observe_input("countdown_max_next", self._on_countdown_max_next_input, None)
        igs.observe_input("alert", self._on_alert_input, None)
        igs.observe_input("alert_clear", self._on_alert_clear_input, None)
        igs.observe_input("condition_violated", self._on_condition_violated_input, None)
        igs.observe_input("condition_restored", self._on_condition_restored_input, None)
        igs.observe_input("tts_speaking", self._on_tts_speaking_input, None)
        igs.observe_input("tts_text", self._on_tts_text_input, None)
        igs.observe_input("action_about_to_fire", self._on_action_about_to_fire_input, None)
        igs.observe_input("checklist_item_complete", self._on_checklist_item_complete_input, None)
        igs.observe_input("emergency_procedure_inject", self._on_emergency_procedure_inject_input, None)
        igs.observe_input("interaction_message", self._on_interaction_message_input, None)
        
        # Create outputs (send to TARS)
        igs.output_create("task_approval", igs.BOOL_T, None)
        igs.output_create("task_acknowledged", igs.IMPULSION_T, None)
        igs.output_create("task_cancelled", igs.IMPULSION_T, None)
        igs.output_create("task_override", igs.IMPULSION_T, None)  # Force next state transition
        igs.output_create("start_procedure", igs.IMPULSION_T, None)
        igs.output_create("stop_procedure", igs.IMPULSION_T, None)
        igs.output_create("emergency_inject", igs.STRING_T, None)
        igs.output_create("force_state_jump", igs.STRING_T, None)
        igs.output_create("countdown_complete", igs.IMPULSION_T, None)
        igs.output_create("next_step", igs.IMPULSION_T, None)  # Jump to next state (dev mode)
        igs.output_create("previous_step", igs.IMPULSION_T, None)  # Jump to previous state (dev mode)
        
        print(f"✅ GUI Agent '{self.agent_name}' initialized with Ingescape I/O")
    
    def start(self):
        """Start the GUI agent"""
        print(f"🚀 Starting GUI Agent on {self.device}:{self.port}")
        igs.start_with_device(self.device, self.port)
        print(f"✅ GUI Agent started successfully")
    
    def stop(self):
        """Stop the GUI agent"""
        igs.stop()
        print(f"🛑 GUI Agent stopped")
    
    # ========================================================================
    # TARS → GUI: Ingescape input callbacks (run in Ingescape thread)
    # ========================================================================
    
    def _on_alert_input(self, io_type, name, value_type, value, my_data):
        """Handle alert message from TARS"""
        try:
            alert_data = json.loads(value)
            message = alert_data.get("message", "")
            color = alert_data.get("color", "red")
            # Emit signal for thread-safe UI update
            self._alert_signal.emit(message, color)
        except Exception as e:
            print(f"Error processing alert: {e}")
    
    def _on_alert_clear_input(self, io_type, name, value_type, value, my_data):
        """Handle alert clear from TARS"""
        self._clear_alert_signal.emit()
    
    def _on_interaction_message_input(self, io_type, name, value_type, value, my_data):
        """Handle interaction panel message from TARS"""
        try:
            msg_data = json.loads(value)
            # None means "don't update" (preserve existing text)
            message = msg_data.get("message", "")
            tars_input = msg_data.get("tars_input", "")
            # Convert None to empty string for signal (Qt doesn't handle None well)
            # But empty string will be treated as "no update" in handler
            message = "" if message is None else message
            tars_input = "" if tars_input is None else tars_input
            self._interaction_message_signal.emit(message, tars_input)
        except Exception as e:
            print(f"Error processing interaction message: {e}")
    
    def _on_current_state_input(self, io_type, name, value_type, value, my_data):
        """Handle current state update from TARS"""
        try:
            state_data = json.loads(value)
            self._state_changed_signal.emit(state_data)
        except Exception as e:
            print(f"Error processing current state: {e}")
    
    def _on_next_state_input(self, io_type, name, value_type, value, my_data):
        """Handle next state update from TARS"""
        try:
            state_data = json.loads(value)
            self._next_state_signal.emit(state_data)
        except Exception as e:
            print(f"Error processing next state: {e}")
    
    def _on_previous_state_input(self, io_type, name, value_type, value, my_data):
        """Handle previous state update from TARS"""
        try:
            state_data = json.loads(value)
            self._previous_state_signal.emit(state_data)
        except Exception as e:
            print(f"Error processing previous state: {e}")
    
    def _on_countdown_current_input(self, io_type, name, value_type, value, my_data):
        """Handle countdown_current update from TARS"""
        try:
            # Value is already an integer from Ingescape
            print(f"📊 Countdown current: {value}s")
            # Could update a countdown display here if needed
        except Exception as e:
            print(f"Error processing countdown_current: {e}")
    
    def _on_countdown_next_input(self, io_type, name, value_type, value, my_data):
        """Handle countdown_next update from TARS"""
        try:
            print(f"📊 Countdown next: {value}s")
            # Could update next task countdown display here if needed
        except Exception as e:
            print(f"Error processing countdown_next: {e}")
    
    def _on_countdown_max_current_input(self, io_type, name, value_type, value, my_data):
        """Handle countdown_max_current update from TARS"""
        try:
            # Used for progress calculation
            pass
        except Exception as e:
            print(f"Error processing countdown_max_current: {e}")
    
    def _on_countdown_max_next_input(self, io_type, name, value_type, value, my_data):
        """Handle countdown_max_next update from TARS"""
        try:
            # Used for progress calculation
            pass
        except Exception as e:
            print(f"Error processing countdown_max_next: {e}")
    
    def _on_condition_violated_input(self, io_type, name, value_type, value, my_data):
        """Handle condition violated notification from TARS"""
        try:
            condition_data = json.loads(value)
            print(f"⚠️ Condition violated: {condition_data.get('condition_name')} for {condition_data.get('task_object')}")
            # Could display warning in UI
        except Exception as e:
            print(f"Error processing condition_violated: {e}")
    
    def _on_condition_restored_input(self, io_type, name, value_type, value, my_data):
        """Handle condition restored notification from TARS"""
        try:
            condition_data = json.loads(value)
            print(f"✅ Condition restored: {condition_data.get('condition_name')} for {condition_data.get('task_object')}")
            # Could clear warning in UI
        except Exception as e:
            print(f"Error processing condition_restored: {e}")
    
    def _on_tts_speaking_input(self, io_type, name, value_type, value, my_data):
        """Handle TTS speaking status from TARS"""
        try:
            is_speaking = bool(value)
            print(f"🔊 TTS speaking: {is_speaking}")
            # State is tracked but visual update happens via tts_text
        except Exception as e:
            print(f"Error processing tts_speaking: {e}")
    
    def _on_tts_text_input(self, io_type, name, value_type, value, my_data):
        """Handle TTS text from TARS"""
        try:
            if value:  # TTS started with text
                print(f"🔊 TTS text: {value[:50]}...")
                self._tts_speak_signal.emit(value)  # Show speaking animation + text
            else:  # TTS finished (empty text)
                self._tts_finished_signal.emit("")  # Hide speaking animation
        except Exception as e:
            print(f"Error processing tts_text: {e}")
    
    def _on_action_about_to_fire_input(self, io_type, name, value_type, value, my_data):
        """Handle action about to fire notification from TARS"""
        try:
            state_data = json.loads(value)
            print(f"⚡ Action about to fire: {state_data.get('task_object')}")
            # Could show pre-action indicator in UI
        except Exception as e:
            print(f"Error processing action_about_to_fire: {e}")
    
    def _on_checklist_item_complete_input(self, io_type, name, value_type, value, my_data):
        """Handle checklist item completion from TARS"""
        try:
            item_data = json.loads(value)
            print(f"✅ Checklist item complete: {item_data.get('task_object')}")
            # Could mark checklist item as complete in UI
        except Exception as e:
            print(f"Error processing checklist_item_complete: {e}")
    
    def _on_emergency_procedure_inject_input(self, io_type, name, value_type, value, my_data):
        """Handle emergency procedure injection from TARS"""
        try:
            procedure_name = value
            print(f"🚨 Emergency procedure inject: {procedure_name}")
            # Could inject emergency procedure into timeline
        except Exception as e:
            print(f"Error processing emergency_procedure_inject: {e}")
    
    # ========================================================================
    # GUI Updates: Qt signal handlers (run in main thread)
    # ========================================================================
    
    def _on_alert(self, message: str, color: str):
        """Update UI with alert (main thread)"""
        home_page = self.main_window.page_manager.get_page('home')
        if home_page:
            home_page.displayAlert(message, color)
        
        flight_page = self.main_window.page_manager.get_page('flight')
        if flight_page:
            flight_page.displayAlert(message, color)
    
    def _on_clear_alert(self):
        """Clear alert in UI (main thread)"""
        home_page = self.main_window.page_manager.get_page('home')
        if home_page:
            home_page.clearAlert()
        
        flight_page = self.main_window.page_manager.get_page('flight')
        if flight_page:
            flight_page.clearAlert()
    
    def _on_interaction_message(self, message: str, tars_input: str):
        """Update interaction panel (main thread)"""
        # Update both home and flight pages using helper methods
        self.main_window.set_interaction_text(message)
        self.main_window.set_interaction_tars_input(tars_input, show=bool(tars_input))
    
    def _on_state_changed(self, state_data: dict):
        """Handle state change from TARS (main thread)"""
        print(f"📊 State update received: {state_data.get('procedure')} - {state_data.get('task_object')}")
        
        # Reconstruct State object from JSON data
        from Core.fsm import State
        state = State(
            procedure=state_data.get('procedure', ''),
            classification=state_data.get('classification', ''),
            type=state_data.get('type', ''),
            category=state_data.get('category', ''),
            task_object=state_data.get('task_object', ''),
            value=state_data.get('value', ''),
            human_role=state_data.get('human_role', ''),
            autonomy_role=state_data.get('autonomy_role', ''),
            information_requirement=state_data.get('information_requirement', ''),
            interaction=state_data.get('interaction', ''),
            delay_before_action=state_data.get('delay_before_action', 0),
            delay_after_action=state_data.get('delay_after_action', 0),
            callout=state_data.get('callout', ''),
            condition=state_data.get('condition'),
            condition_type=state_data.get('condition_type'),
            condition_function=state_data.get('condition_function'),
            monitor_scope=state_data.get('monitor_scope'),
        )
        
        # Call MainWindow's update_state method
        self.main_window.update_state(state)
    
    def _on_next_state_changed(self, state_data: dict):
        """Handle next state update from TARS (main thread)"""
        print(f"📊 Next state received: {state_data.get('procedure')} - {state_data.get('task_object')}")
        
        # Update next state labels in UI (home page)
        next_procedure_text = state_data.get('procedure', '')
        next_task_text = f"{state_data.get('task_object', '')}     {state_data.get('value', '')}"
        
        self.main_window.ui.n_g_label_2.setText(next_procedure_text)
        self.main_window.ui.n_t_label_2.setText(next_task_text)
        
        # Update flight page labels
        self.main_window.ui.n_g_label_flight.setText(next_procedure_text)
        self.main_window.ui.n_t_label_flight.setText(next_task_text)
        
        # Store for later use (timeline, etc.)
        self.main_window.next_state = state_data
    
    def _on_previous_state_changed(self, state_data: dict):
        """Handle previous state update from TARS (main thread)"""
        print(f"📊 Previous state received: {state_data.get('procedure')} - {state_data.get('task_object')}")
        
        # Update previous state labels in UI (home page)
        previous_procedure_text = state_data.get('procedure', '')
        previous_task_text = f"{state_data.get('task_object', '')}     {state_data.get('value', '')}"
        
        self.main_window.ui.p_g_2.setText(previous_procedure_text)
        self.main_window.ui.p_t_2.setText(previous_task_text)
        
        # Update flight page labels
        self.main_window.ui.p_g_flight.setText(previous_procedure_text)
        self.main_window.ui.p_t_flight.setText(previous_task_text)
        
        # Store for later use
        self.main_window.previous_state = state_data
    
    # ========================================================================
    # GUI → TARS: Connect UI actions to Ingescape outputs
    # ========================================================================
    
    def _connect_ui_to_tars(self):
        """Connect MainWindow signals to TARS inputs via Ingescape"""
        # Task completion - HomePage
        self.main_window.get_home_page().task_done_signal.connect(self._send_task_acknowledged)
        self.main_window.get_home_page().task_cancel_signal.connect(self._send_task_cancelled)
        self.main_window.get_home_page().task_override_signal.connect(self._send_task_override)
        self.main_window.get_home_page().task_allowed_signal.connect(self._send_task_allowed)
        self.main_window.get_home_page().task_not_allowed_signal.connect(self._send_task_not_allowed)
        self.main_window.get_home_page().countdown_zero_signal.connect(self._send_countdown_complete)
        self.main_window.get_home_page().next_step_signal.connect(self._send_next_step)
        self.main_window.get_home_page().previous_step_signal.connect(self._send_previous_step)
        
        # Task completion - FlightPage (same signals)
        flight_page = self.main_window.page_manager.get_page('flight')
        if flight_page:
            flight_page.task_done_signal.connect(self._send_task_acknowledged)
            flight_page.task_cancel_signal.connect(self._send_task_cancelled)
            flight_page.task_override_signal.connect(self._send_task_override)
            flight_page.task_allowed_signal.connect(self._send_task_allowed)
            flight_page.task_not_allowed_signal.connect(self._send_task_not_allowed)
            flight_page.countdown_zero_signal.connect(self._send_countdown_complete)
            flight_page.next_step_signal.connect(self._send_next_step)
            flight_page.previous_step_signal.connect(self._send_previous_step)
    
    def _send_task_acknowledged(self):
        """Send task acknowledgment to TARS"""
        igs.output_set_impulsion("task_acknowledged")
        print("📤 Sent task_acknowledged to TARS")
    
    def _send_task_cancelled(self):
        """Send task cancellation to TARS"""
        igs.output_set_impulsion("task_cancelled")
        print("📤 Sent task_cancelled to TARS")
    
    def _send_task_override(self):
        """Send task override (force next state) to TARS"""
        igs.output_set_impulsion("task_override")
        print("⚡ Sent task_override to TARS (force next state)")
    
    def _send_task_override(self):
        """Send task override (force next state) to TARS"""
        igs.output_set_impulsion("task_override")
        print("⚡ Sent task_override to TARS (force next state)")
    
    def _send_task_allowed(self):
        """Send task approval to TARS"""
        igs.output_set_bool("task_approval", True)
        print("📤 Sent task_approval=TRUE to TARS")
    
    def _send_task_not_allowed(self):
        """Send task denial to TARS"""
        igs.output_set_bool("task_approval", False)
        print("📤 Sent task_approval=FALSE to TARS")
    
    def _send_countdown_complete(self):
        """Send countdown completion to TARS"""
        igs.output_set_impulsion("countdown_complete")
        print("📤 Sent countdown_complete to TARS")
    
    def _send_next_step(self):
        """Send next_step impulsion to TARS (dev mode navigation)"""
        igs.output_set_impulsion("next_step")
        print("⏭️ Sent next_step to TARS (jump to next state)")
    
    def _send_previous_step(self):
        """Send previous_step impulsion to TARS (dev mode navigation)"""
        igs.output_set_impulsion("previous_step")
        print("⏮️ Sent previous_step to TARS (jump to previous state)")
    
    def send_force_state_jump(self, procedure: str, task_object: str, value: str):
        """Force TARS FSM to jump to specific state (from UI clicks)"""
        import json
        state_json = json.dumps({
            "procedure": procedure,
            "task_object": task_object,
            "value": value
        })
        igs.output_set_string("force_state_jump", state_json)
        print(f"🎯 Sent force_state_jump to TARS: {procedure} - {task_object} - {value}")


def create_gui_agent(main_window: MainWindow, 
                     device: str = "wlp0s20f3", 
                     port: int = 5670) -> GUIAgent:
    """
    Factory function to create and start GUI agent
    
    Args:
        main_window: MainWindow instance to wrap
        device: Network device name
        port: Ingescape port
        
    Returns:
        Initialized and started GUIAgent
    """
    gui_agent = GUIAgent(main_window, device=device, port=port)
    gui_agent.start()
    return gui_agent


if __name__ == "__main__":
    """
    Standalone test - can run GUI Agent independently
    """
    print("GUI Agent standalone mode - creating minimal window")
    app = QApplication(sys.argv)
    
    # Import and create MainWindow
    from main import MainWindow
    window = MainWindow()
    
    # Create and start GUI agent
    gui_agent = create_gui_agent(window)
    
    # Run Qt event loop
    exit_code = app.exec()
    
    # Cleanup
    gui_agent.stop()
    sys.exit(exit_code)
