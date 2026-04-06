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

from Core.igs_utils import start_with_device_fallback
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
    _interaction_message_signal = Signal(str, str, object)  # (message, tars_input, button_config)
    _state_changed_signal = Signal(dict)  # State dict from JSON
    _next_state_signal = Signal(dict)  # Next state dict from JSON
    _previous_state_signal = Signal(dict)  # Previous state dict from JSON
    _tts_speak_signal = Signal(str)  # TTS text being spoken
    _tts_finished_signal = Signal(str)  # TTS finished speaking
    _stt_listening_signal = Signal(bool)  # STT listening status
    _action_about_to_fire_signal = Signal(dict)  # Action about to fire (state dict)
    _atc_speech_signal = Signal(str)   # ATC speech_output for the log
    _stt_speech_signal = Signal(str)   # Pilot STT recognized text for the log
    _state_divider_signal = Signal(str) # FSM state transition divider for the log
    _reset_speech_log_signal = Signal()  # Clear log on TARS reset
    _tars_status_signal = Signal(str)  # Status label text update
    _allocation_reloaded_signal = Signal(str)  # CSV filename after TARS reloads allocation
    _external_task_acked_signal = Signal()  # joystick task_acknowledged routed through GUI
    _condition_changed_signal = Signal(str)  # condition input → switch TARS persona images
    
    def __init__(self, main_window: MainWindow, agent_name: str = "Shared Interface", 
                 device: str = "wlp0s20f3", port: int = 5670, no_next_countdown: bool = False):
        super().__init__()
        self.main_window = main_window
        self.agent_name = agent_name
        self.device = device
        self.port = port
        self.no_next_countdown = no_next_countdown

        # Dynamic middle-button tracking (for winds supporter panel)
        self._middle_buttons = []  # list of dynamically inserted QPushButton widgets
        # Cached wind-editor parameters (set when interaction message arrives)
        self._wind_edit_runway_heading = 237
        self._wind_edit_initial_dir    = 0
        self._wind_edit_initial_mag    = 0
        # Set True in _on_state_changed; cleared + dialog opened in _on_interaction_message
        self._pending_wind_dialog_open: bool = False
        self._wind_edit_dlg = None  # Live reference; closed on external state advance
        self._chrono_dlg = None     # Live reference; started/closed on external ack
        # True only when the current state is ENGINE FIRE / Chrono / START
        self._show_chrono_button: bool = False
        self._chrono_autonomy_role: str = ""
        self._chrono_delay_before_action: float = 0
        
        # Connect internal signals to UI update methods
        self._alert_signal.connect(self._on_alert)
        self._clear_alert_signal.connect(self._on_clear_alert)
        self._interaction_message_signal.connect(self._on_interaction_message)
        self._state_changed_signal.connect(self._on_state_changed)
        self._next_state_signal.connect(self._on_next_state_changed)
        self._previous_state_signal.connect(self._on_previous_state_changed)
        self._tts_speak_signal.connect(self.main_window.on_tts_speak)
        self._tts_finished_signal.connect(self.main_window.on_tts_finished)
        self._stt_listening_signal.connect(self.main_window.on_stt_listening)
        self._action_about_to_fire_signal.connect(self._on_action_about_to_fire)
        self._atc_speech_signal.connect(self.main_window.on_atc_speech)
        self._stt_speech_signal.connect(self.main_window.on_pilot_speech)
        self._state_divider_signal.connect(self.main_window.on_state_divider)
        self._reset_speech_log_signal.connect(self.main_window.reset_speech_log)
        self._tars_status_signal.connect(self.main_window.on_tars_status)
        self._allocation_reloaded_signal.connect(self.main_window.on_allocation_reloaded)
        self._condition_changed_signal.connect(main_window.on_condition_changed)
        
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
        igs.input_create("stt_listening", igs.BOOL_T, None)
        igs.input_create("action_about_to_fire", igs.STRING_T, None)
        igs.input_create("checklist_item_complete", igs.STRING_T, None)
        igs.input_create("emergency_procedure_inject", igs.STRING_T, None)
        igs.input_create("interaction_message", igs.STRING_T, None)
        igs.input_create("atc_speech_output", igs.STRING_T, None)  # ATC speech_output feed
        igs.input_create("stt_speech_output", igs.STRING_T, None)   # STT recognized text feed
        igs.input_create("tars_status", igs.STRING_T, None)  # TARS status text for the GUI label
        igs.input_create("allocation_reloaded", igs.STRING_T, None)  # JSON: {csv, states_count} when TARS reloads
        igs.input_create("task_acknowledged", igs.IMPULSION_T, None)  # joystick/external ack routed through GUI
        igs.input_create("condition", igs.STRING_T, None)  # persona selector: TARS | TARP-F | TARP-S | TARC
        
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
        igs.observe_input("stt_listening", self._on_stt_listening_input, None)
        igs.observe_input("action_about_to_fire", self._on_action_about_to_fire_input, None)
        igs.observe_input("checklist_item_complete", self._on_checklist_item_complete_input, None)
        igs.observe_input("emergency_procedure_inject", self._on_emergency_procedure_inject_input, None)
        igs.observe_input("interaction_message", self._on_interaction_message_input, None)
        igs.observe_input("atc_speech_output", self._on_atc_speech_output_input, None)
        igs.observe_input("stt_speech_output", self._on_stt_speech_output_input, None)
        igs.observe_input("tars_status", self._on_tars_status_input, None)
        igs.observe_input("allocation_reloaded", self._on_allocation_reloaded_input, None)
        igs.observe_input("task_acknowledged", self._on_ext_task_acknowledged_input, None)
        igs.observe_input("condition", self._on_condition_input, None)
        self._external_task_acked_signal.connect(self._on_external_task_acknowledged)
        # Map ATC_Agent.speech_output → our atc_speech_output input
        igs.mapping_add("atc_speech_output", "ATC_Agent", "speech_output")
        # Map Speech_to_Text_Agent.speech_output → our stt_speech_output input
        igs.mapping_add("stt_speech_output", "Speech_to_Text_Agent", "speech_output")
        # Map TARS_Agent.tars_status → our tars_status input
        igs.mapping_add("tars_status", "TARS_Agent", "tars_status")
        # Map TARS_Agent outputs → our inputs
        igs.mapping_add("current_state", "TARS_Agent", "current_state")
        igs.mapping_add("next_state", "TARS_Agent", "next_state")
        igs.mapping_add("previous_state", "TARS_Agent", "previous_state")
        igs.mapping_add("countdown_current", "TARS_Agent", "countdown_current")
        igs.mapping_add("countdown_next", "TARS_Agent", "countdown_next")
        igs.mapping_add("countdown_max_current", "TARS_Agent", "countdown_max_current")
        igs.mapping_add("countdown_max_next", "TARS_Agent", "countdown_max_next")
        igs.mapping_add("alert", "TARS_Agent", "alert")
        igs.mapping_add("alert_clear", "TARS_Agent", "alert_clear")
        igs.mapping_add("condition_violated", "TARS_Agent", "condition_violated")
        igs.mapping_add("condition_restored", "TARS_Agent", "condition_restored")
        igs.mapping_add("action_about_to_fire", "TARS_Agent", "action_about_to_fire")
        igs.mapping_add("checklist_item_complete", "TARS_Agent", "checklist_item_complete")
        igs.mapping_add("emergency_procedure_inject", "TARS_Agent", "emergency_procedure_inject")
        igs.mapping_add("allocation_reloaded", "TARS_Agent", "allocation_reloaded")
        # Map Speech_to_Text_Agent.is_listening → our stt_listening input
        igs.mapping_add("stt_listening", "Speech_to_Text_Agent", "is_listening")
        
        # Create outputs (send to TARS)
        igs.output_create("task_approval", igs.BOOL_T, None)
        igs.output_create("task_acknowledged", igs.IMPULSION_T, None)
        igs.output_create("task_cancelled", igs.IMPULSION_T, None)
        igs.output_create("task_override", igs.IMPULSION_T, None)  # Force next state transition
        igs.output_create("start_procedure", igs.IMPULSION_T, None)
        igs.output_create("stop_procedure", igs.IMPULSION_T, None)
        igs.output_create("tts_stop", igs.IMPULSION_T, None)  # Stop TTS playback immediately (also mutes)
        igs.output_create("tts_unmute", igs.IMPULSION_T, None)  # Re-enable TTS after mute
        igs.output_create("emergency_inject", igs.STRING_T, None)
        igs.output_create("force_state_jump", igs.STRING_T, None)
        igs.output_create("countdown_complete", igs.IMPULSION_T, None)
        igs.output_create("update_allocation", igs.STRING_T, None)
        igs.output_create("next_step", igs.IMPULSION_T, None)  # Jump to next state (dev mode)
        igs.output_create("previous_step", igs.IMPULSION_T, None)  # Jump to previous state (dev mode)
        igs.output_create("request_atis", igs.IMPULSION_T, None)  # Request ATIS from automated radio
        igs.output_create("load_csv", igs.STRING_T, None)  # Send CSV filename to TARS for full reload
        igs.output_create("popup_active", igs.BOOL_T, None)  # True while a modal dialog is open (blocks joystick ack in TARS)
        
        print(f"✅ GUI Agent '{self.agent_name}' initialized with Ingescape I/O")
    
    def start(self):
        """Start the GUI agent"""
        print(f"🚀 Starting GUI Agent on port {self.port}")
        start_with_device_fallback(igs, self.port)
        print(f"✅ GUI Agent started successfully")
    
    def stop(self):
        """Stop the GUI agent"""
        igs.stop()
        print(f"🛑 GUI Agent stopped")
    
    # ========================================================================
    # TARS → GUI: Ingescape input callbacks (run in Ingescape thread)
    # ========================================================================
    
    def _on_condition_input(self, io_type, name, value_type, value, my_data):
        """Handle condition string from Ingescape — switch TARS persona images."""
        try:
            if value and isinstance(value, str):
                condition = value.strip()
                if condition in ("TARS", "TARP-F", "TARP-S", "TARC"):
                    self._condition_changed_signal.emit(condition)
                else:
                    print(f"⚠️ Unknown condition value: '{condition}'")
        except Exception as e:
            print(f"Error processing condition: {e}")

    def _on_ext_task_acknowledged_input(self, io_type, name, value_type, value, my_data):
        """Ingescape thread: joystick sent task_acknowledged — route through main thread."""
        self._external_task_acked_signal.emit()

    def _on_external_task_acknowledged(self):
        """Main thread: intercept external task_acknowledged before it reaches TARS.

        Priority:
        1. Wind dialog open  → confirm it (first ack = validate popup)
        2. Chrono dialog open in SET phase → start the countdown
        3. No dialog active  → forward to TARS as normal task_acknowledged
        """
        if self._wind_edit_dlg is not None:
            print("🎮 External ack → confirming wind dialog")
            self._wind_edit_dlg.confirm()
        elif self._chrono_dlg is not None and not self._chrono_dlg.is_running:
            print("🎮 External ack → starting chrono")
            self._chrono_dlg.start_countdown()
        else:
            self._send_task_acknowledged()

    def _on_tars_status_input(self, io_type, name, value_type, value, my_data):
        """Handle tars_status string from TARS agent — update the status label."""
        try:
            if value:
                self._tars_status_signal.emit(str(value))
        except Exception as e:
            print(f"Error processing tars_status: {e}")

    def _on_allocation_reloaded_input(self, io_type, name, value_type, value, my_data):
        """Handle allocation_reloaded notification from TARS — GUI reloads its local stub."""
        try:
            data = json.loads(value)
            csv_filename = data.get("csv", "")
            states_count = data.get("states_count", 0)
            print(f"📊 Allocation reloaded: '{csv_filename}' ({states_count} states)")
            if csv_filename:
                self._allocation_reloaded_signal.emit(csv_filename)
        except Exception as e:
            print(f"Error processing allocation_reloaded: {e}")

    def _on_atc_speech_output_input(self, io_type, name, value_type, value, my_data):
        """Handle ATC speech_output — forward to the chat log (left side)."""
        try:
            if value and isinstance(value, str) and value.strip():
                self._atc_speech_signal.emit(value.strip())
        except Exception as e:
            print(f"Error processing atc_speech_output: {e}")

    def _on_stt_speech_output_input(self, io_type, name, value_type, value, my_data):
        """Handle STT recognized text — forward to the chat log as pilot bubble."""
        try:
            if value and isinstance(value, str) and value.strip():
                print(f"🎤 Pilot speech logged: {value.strip()}")
                self._stt_speech_signal.emit(value.strip())
        except Exception as e:
            print(f"Error processing stt_speech_output: {e}")

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
            if not value or not value.strip():
                return
            msg_data = json.loads(value)
            # None means "don't update" (preserve existing text)
            message = msg_data.get("message", "")
            tars_input = msg_data.get("tars_input", "")
            # Convert None to empty string for signal (Qt doesn't handle None well)
            # But empty string will be treated as "no update" in handler
            message = "" if message is None else message
            tars_input = "" if tars_input is None else tars_input
            
            # Extract button configuration (if present)
            button_config = {}
            if "left_button" in msg_data:
                button_config["left_button"] = msg_data["left_button"]
            if "right_button" in msg_data:
                button_config["right_button"] = msg_data["right_button"]

            # Extract wind-editor metadata and middle_button if present
            if "middle_button" in msg_data:
                button_config["middle_button"] = msg_data["middle_button"]
            for key in ("runway_heading", "initial_wind_dir", "initial_wind_mag"):
                if key in msg_data:
                    button_config[key] = msg_data[key]
                
            self._interaction_message_signal.emit(message, tars_input, button_config)
        except Exception as e:
            print(f"Error processing interaction message: {e}")
    
    def _on_current_state_input(self, io_type, name, value_type, value, my_data):
        """Handle current state update from TARS"""
        try:
            state_data = json.loads(value)
            self._state_changed_signal.emit(state_data)
            # Emit a divider for the speech log (skip IDLE — shown on reset)
            procedure   = state_data.get('procedure', '')
            task_object = state_data.get('task_object', '')
            if procedure and procedure != 'IDLE' and task_object and task_object != 'Idle':
                divider_label = f"{procedure}  ›  {task_object}"
                self._state_divider_signal.emit(divider_label)
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
            if not self.no_next_countdown:
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
    
    def _on_stt_listening_input(self, io_type, name, value_type, value, my_data):
        """Handle STT listening status from STT agent"""
        try:
            is_listening = bool(value)
            print(f"🎤 STT listening: {is_listening}")
            self._stt_listening_signal.emit(is_listening)  # Update visual state
        except Exception as e:
            print(f"Error processing stt_listening: {e}")
    
    def _on_action_about_to_fire_input(self, io_type, name, value_type, value, my_data):
        """Handle action about to fire notification from TARS"""
        try:
            state_data = json.loads(value)
            print(f"⚡ Action about to fire: {state_data.get('task_object')}")
            # Emit signal for UI update (tick mark animation)
            self._action_about_to_fire_signal.emit(state_data)
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
    
    def _on_interaction_message(self, message: str, tars_input: str, button_config: dict):
        """Update interaction panel (main thread)"""
        # Always clean up previous dynamic middle buttons first
        self._cleanup_middle_buttons()

        self.main_window.set_interaction_text(message)
        self.main_window.set_interaction_tars_input(tars_input, show=bool(tars_input))

        if not button_config:
            return

        home_page   = self.main_window.page_manager.get_page('home')
        flight_page = self.main_window.page_manager.get_page('flight')

        left_text  = button_config.get("left_button", "")
        right_text = button_config.get("right_button", "")
        mid_text   = button_config.get("middle_button", "")

        use_approval_mode = left_text in ("APPROVE", "DENY") or right_text in ("APPROVE", "DENY")
        if home_page:
            home_page.connect_int_panel_buttons(default=not use_approval_mode)

        # ---- left button ----
        if "left_button" in button_config:
            lbt = button_config["left_button"]
            if lbt is None:
                for p in (home_page, flight_page):
                    if p: p.int_panel_left_button.hide()
            elif lbt in ("EDIT", "LISTEN TO ATIS"):
                # Cache wind metadata for later use by the dialog / ATIS request
                self._wind_edit_runway_heading = button_config.get("runway_heading", 57)
                self._wind_edit_initial_dir    = button_config.get("initial_wind_dir", 90)
                self._wind_edit_initial_mag    = button_config.get("initial_wind_mag", 4)
                for p in (home_page, flight_page):
                    if p is None:
                        continue
                    p.int_panel_left_button.setText(lbt)
                    p.int_panel_left_button.show()
                    try:
                        p.int_panel_left_button.clicked.disconnect()
                    except Exception:
                        pass
                    if lbt == "EDIT":
                        p.int_panel_left_button.clicked.connect(self._open_wind_edit_dialog)
                    else:  # LISTEN TO ATIS
                        p.int_panel_left_button.clicked.connect(self._send_request_atis)
            elif lbt:
                for p in (home_page, flight_page):
                    if p:
                        p.int_panel_left_button.setText(lbt)
                        p.int_panel_left_button.show()

        # ---- middle button (dynamic) ----
        if mid_text:
            self._wind_edit_runway_heading = button_config.get("runway_heading", 57)
            self._wind_edit_initial_dir    = button_config.get("initial_wind_dir", 90)
            self._wind_edit_initial_mag    = button_config.get("initial_wind_mag", 4)
            if mid_text == "ENTER WIND" and getattr(self, "_pending_wind_dialog_open", False):
                self._pending_wind_dialog_open = False
                self._open_wind_edit_dialog()
            for container_name in ("int_panel_button_container", "int_panel_button_container_flight"):
                container = getattr(self.main_window.ui, container_name, None)
                if container is None:
                    continue
                layout = container.layout()
                if layout is None:
                    continue
                btn = self._make_middle_button(container, mid_text)
                layout.insertWidget(1, btn)   # slot 1 = between left (0) and right (last)
                self._middle_buttons.append(btn)

        # ---- right button ----
        if "right_button" in button_config:
            rbt = button_config["right_button"]
            if rbt is None:
                for p in (home_page, flight_page):
                    if p: p.int_panel_right_button.hide()
            elif rbt:
                for p in (home_page, flight_page):
                    if p:
                        p.int_panel_right_button.setText(rbt)
                        p.int_panel_right_button.show()

        # Re-inject EDIT CHRONO after interaction message cleanup (only for Chrono START state)
        if self._show_chrono_button:
            self._inject_chrono_button()

    # ------------------------------------------------------------------
    # Middle-button helpers
    # ------------------------------------------------------------------
    def _cleanup_middle_buttons(self):
        """Remove any dynamically inserted middle buttons from the layout."""
        for btn in self._middle_buttons:
            try:
                if btn.parent() and btn.parent().layout():
                    btn.parent().layout().removeWidget(btn)
                btn.hide()
                btn.deleteLater()
            except Exception as e:
                print(f"Middle button cleanup error: {e}")
        self._middle_buttons = []

    def _make_middle_button(self, parent, text: str):
        """Create a styled middle button and wire its action."""
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import QSize
        btn = QPushButton(text, parent)
        btn.setMinimumSize(QSize(0, 50))
        btn.setStyleSheet("""
            QPushButton {
                font: 700 12pt 'JetBrains Mono';
                color: #55aaff;
                background-color: rgb(33, 37, 43);
                border: 2px solid #55aaff;
                border-radius: 8px;
                padding: 4px 12px;
            }
            QPushButton:hover  { background-color: rgba(85, 170, 255, 40); }
            QPushButton:pressed { background-color: rgba(85, 170, 255, 80); }
        """)
        if text in ("ENTER WIND", "EDIT"):
            btn.clicked.connect(self._open_wind_edit_dialog)
        elif text == "EDIT CHRONO":
            btn.clicked.connect(self._open_chrono_edit_dialog)
        btn.show()
        return btn

    # ------------------------------------------------------------------
    # Chrono editor
    # ------------------------------------------------------------------
    def _inject_chrono_button(self):
        """Insert an 'EDIT CHRONO' middle button into both interaction panel containers."""
        for container_name in ("int_panel_button_container", "int_panel_button_container_flight"):
            container = getattr(self.main_window.ui, container_name, None)
            if container is None:
                continue
            layout = container.layout()
            if layout is None:
                continue
            btn = self._make_middle_button(container, "EDIT CHRONO")
            layout.insertWidget(1, btn)
            self._middle_buttons.append(btn)

    def _open_chrono_edit_dialog(self, auto_delay_ms: int = 0):
        """Open the self-contained chrono popup. When the countdown ends, send task_acknowledged to TARS."""
        from widgets.chrono_edit_dialog import ChronoEditDialog
        auto_start = (self._chrono_autonomy_role == "performer")
        dlg = ChronoEditDialog(parent=self.main_window, initial_seconds=15,
                               auto_start=auto_start, auto_start_delay_ms=auto_delay_ms)

        def _on_completed():
            # Unblock TARS *before* sending the ack: completed fires while exec() is
            # still blocking (dialog not yet closed), so popup_active would otherwise
            # still be True in TARS and the impulsion would be dropped.
            igs.output_set_bool("popup_active", False)
            self._send_task_acknowledged()

        dlg.completed.connect(_on_completed)
        self._chrono_dlg = dlg
        igs.output_set_bool("popup_active", True)
        dlg.exec()
        igs.output_set_bool("popup_active", False)  # safe no-op if already cleared above
        self._chrono_dlg = None

    # ------------------------------------------------------------------
    # Wind editor / ATIS
    # ------------------------------------------------------------------
    def _send_request_atis(self):
        """Send an ATIS request impulsion to the automated radio agent."""
        igs.output_set_impulsion("request_atis")
        print("📻 Sent request_atis impulsion")

    def _open_wind_edit_dialog(self):
        """Open the wind edit popup (called when user clicks EDIT or ENTER WIND)."""
        from widgets.wind_edit_dialog import WindEditDialog
        runway_hdg  = self._wind_edit_runway_heading
        initial_dir = self._wind_edit_initial_dir
        initial_mag = self._wind_edit_initial_mag

        dlg = WindEditDialog(
            parent=self.main_window,
            runway_heading=runway_hdg,
            initial_dir=initial_dir,
            initial_mag=initial_mag,
        )
        dlg.confirmed.connect(self._on_wind_edit_confirmed)
        self._wind_edit_dlg = dlg
        igs.output_set_bool("popup_active", True)
        dlg.exec()
        igs.output_set_bool("popup_active", False)
        self._wind_edit_dlg = None

    def _on_wind_edit_confirmed(self, direction: int, magnitude: int):
        """Handle confirmed wind values from the editor dialog."""
        from widgets.wind_edit_dialog import WindEditDialog
        runway_hdg = getattr(self, "_wind_edit_runway_heading", 57)

        cw = WindEditDialog.compute_crosswind(direction, magnitude, runway_hdg)
        crosswind   = cw["crosswind"]
        headwind    = cw["headwind"]
        side        = cw["side"]

        headwind_sign = "Headwind" if headwind >= 0 else "Tailwind"

        result_text = (
            f"WIND {direction:03d}° / {magnitude:02d} kt\n"
            f"Crosswind: {crosswind:.1f} kt from the {side}\n"
            f"{headwind_sign} component: {abs(headwind):.1f} kt"
        )

        self.main_window.set_interaction_tars_input(result_text, show=True)
        print(
            f"🌬️  Wind edit confirmed — DIR {direction:03d}° / MAG {magnitude} kt  "
            f"| XWind {crosswind:.1f} kt {side}  "
            f"| {headwind_sign} {abs(headwind):.1f} kt  "
            f"(RWY {runway_hdg}°)"
        )
    
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
            transition_kind=state_data.get('transition_kind', 'waiting'),
        )
        
        # If returning to IDLE, clear the speech log
        if state_data.get('task_object') == 'Idle' and state_data.get('procedure') == 'IDLE':
            self._reset_speech_log_signal.emit()

        is_chrono_start = (
            state.procedure == "ENGINE FIRE"
            and state.task_object == "Chrono"
            and state.value == "START"
        )
        self._show_chrono_button = is_chrono_start
        self._chrono_autonomy_role = state.autonomy_role if is_chrono_start else ""
        self._chrono_delay_before_action = state.delay_before_action if is_chrono_start else 0

        is_wind_check = (
            state.procedure == "LINE-UP AND HOLD"
            and state.task_object == "Winds"
            and state.value == "CHECK"
        )

        # Close wind dialog if a state change arrives while it's open (e.g. joystick ack)
        if self._wind_edit_dlg is not None and not is_wind_check:
            self._wind_edit_dlg.reject()

        # Call MainWindow's update_state method
        self.main_window.update_state(state)

        if is_wind_check and state.autonomy_role == "supporter":
            self._pending_wind_dialog_open = True

        if self._show_chrono_button:
            if self._chrono_autonomy_role == "performer":
                # Open dialog immediately; auto-start fires after delay_before_action
                self._open_chrono_edit_dialog(auto_delay_ms=int(self._chrono_delay_before_action * 1000))
            else:
                # supporter: open dialog but do not auto-start the chrono
                self._open_chrono_edit_dialog(auto_delay_ms=0)
    
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
    
    def _on_action_about_to_fire(self, state_data: dict):
        """Handle action about to fire from TARS (main thread) - show tick mark"""
        try:
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
                transition_kind=state_data.get('transition_kind', 'waiting'),
            )
            
            # Call MainWindow handler to show tick mark animation
            self.main_window.handle_action_about_to_fire(state)
        except Exception as e:
            print(f"Error in _on_action_about_to_fire: {e}")
            import traceback
            traceback.print_exc()
    
    # ========================================================================
    # GUI → TARS: Connect UI actions to Ingescape outputs
    # ========================================================================
    
    def _connect_ui_to_tars(self):
        """Connect MainWindow signals to TARS inputs via Ingescape"""
        # Task completion - HomePage
        home_page = self.main_window.get_home_page()
        if home_page is not None:
            home_page.task_done_signal.connect(self._send_task_acknowledged)
            home_page.task_cancel_signal.connect(self._send_task_cancelled)
            home_page.task_override_signal.connect(self._send_task_override)
            home_page.task_allowed_signal.connect(self._send_task_allowed)
            home_page.task_not_allowed_signal.connect(self._send_task_not_allowed)
            home_page.countdown_zero_signal.connect(self._send_countdown_complete)
            home_page.next_step_signal.connect(self._send_next_step)
            home_page.previous_step_signal.connect(self._send_previous_step)
        
        # Emergency stop button
        if home_page is not None and hasattr(home_page, 'stop_all_signal'):
            home_page.stop_all_signal.connect(self._send_stop_procedure)

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

    def _send_stop_procedure(self):
        """Send emergency stop impulsion to TARS - halts FSM, all background threads and TTS"""
        igs.output_set_impulsion("stop_procedure")
        print("🛑 Sent stop_procedure to TARS (emergency stop)")
        igs.output_set_impulsion("tts_stop")
        print("🛑 Sent tts_stop to TTS agent (halt audio)")

    def send_tts_stop(self):
        """Send tts_stop impulsion to mute TTS persistently (interrupts current + all future sentences)"""
        igs.output_set_impulsion("tts_stop")
        print("🔊 Sent tts_stop to TTS agent (user muted)")

    def send_tts_unmute(self):
        """Send tts_unmute impulsion to re-enable TTS playback after mute"""
        igs.output_set_impulsion("tts_unmute")
        print("🔊 Sent tts_unmute to TTS agent (user unmuted)")
    
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

    def send_allocation_update(self, allocation_data: list):
        """Send a role-allocation update to the TARS subprocess via Ingescape.

        Args:
            allocation_data: list of dicts with keys procedure, task_object,
                             value, human_role, autonomy_role.
        """
        import json
        igs.output_set_string("update_allocation", json.dumps(allocation_data))
        print(f"📤 Sent update_allocation to TARS: {len(allocation_data)} tasks")

    def send_load_csv(self, csv_filename: str):
        """Send a CSV filename to TARS to fully reload task allocation from that file.

        Args:
            csv_filename: Bare filename (e.g. 'HUMAN_PERF_NO_TARS.csv') located in Core/.
        """
        igs.output_set_string("load_csv", csv_filename)
        print(f"📤 Sent load_csv to TARS: '{csv_filename}'")


def create_gui_agent(main_window: MainWindow, 
                     device: str = "wlp0s20f3", 
                     port: int = 5670,
                     no_next_countdown: bool = False) -> GUIAgent:
    """
    Factory function to create and start GUI agent
    
    Args:
        main_window: MainWindow instance to wrap
        device: Network device name
        port: Ingescape port
        no_next_countdown: If True, suppress next countdown logging
        
    Returns:
        Initialized and started GUIAgent
    """
    gui_agent = GUIAgent(main_window, device=device, port=port, no_next_countdown=no_next_countdown)
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
