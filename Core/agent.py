import threading
import time
import signal
import math
import traceback
import os
from pathlib import Path
from Core.echo import *
from Core.fsm import FiniteStateMachine, State, Transition
from Core.speech_commands import match_all_commands
from Core.message_protocol import encode_state_to_json, create_alert_message, create_interaction_message
from Core.igs_utils import start_with_device_fallback
import csv
import re
import soundfile as sf
import sounddevice as sd

# Direct import for better IDE support
try:
    import ingescape as igs
except ImportError:
    # Fallback if already imported via echo
    pass

# Platform detection for default network device
import platform

# Choose sensible default network device name depending on host OS.
# Linux typically uses interface names like 'wlp0s20f3'; Windows GUI name is 'Wi-Fi'.
if platform.system() == "Linux":
    DEFAULT_DEVICE = "wlp0s20f3"
elif platform.system() == "Windows":
    DEFAULT_DEVICE = "Wi-Fi"
else:
    DEFAULT_DEVICE = "wlps"

CURRENT_BRIEFING_EXPORT_LOADED = "TARS_PERF_AND_SUPPORT_DELAYS.csv"
#CURRENT_BRIEFING_EXPORT_LOADED = "briefing_export_FULL_TARS_PERF.csv"
### PARAMETERS ###
ALLOW_PARALLEL_ATC = True  # Enable/disable parallel ATC thread execution
TARS_RELIABLE = True
TO_PITCH = 10  # Takeoff pitch target in degrees
SAFE_ALTITUDE = 1500  # Safe altitude to climb to after engine failure
V_ONE = 90  # Takeoff decision speed
V_ROTATE = 90  # Rotation speed
V_TWO = 97  # Climb speed
V_ENR = 120 # single engine climb speed
AIRSPEED_ALIVE_THRESHOLD = 40  # Minimum airspeed to consider "alive"
SEVENTY_KTS = 70  # 70 knots speed
RUNWAY_HEADING = 237 # Runway heading for alignment
TOWER_FREQUENCY = 119.9  # ATC frequency for communication
DEPARTURE_FREQUENCY = 118.9  # ATC frequency for communication after takeoff
#RUNWAY_NUMBER = "Zero-Six Left"  # Runway number for display
RUNWAY_NUMBER = "Two-Four Right"  # Runway number for display
TRANSITION_ALTITUDE = 18000  # Transition altitude in feet
PITCH_ANGLE_THRESHOLD = 1  # Minimum pitch angle to consider "maintained"
PITCH_TEN_DEGREES = 5  # Minimum pitch angle to consider "maintained" 10 +- 2 degrees
SLIP_SKID_THRESHOLD = 2  # Maximum slip/skid value to consider "maintained"
POSITIVE_RATE_THRESHOLD = 500  # Minimum vertical speed to consider "positive rate"
AUTOPILOT_ALTITUDE_THRESHOLD = 700  # Minimum altitude to engage autopilot
ONE_THOUSAND_FIVE_HUNDRED_FEET = 1500  # 1500 feet altitude threshold
CYUL_06L_LATITUDE = 45.461222  # CYUL 06L Latitude
CYUL_24R_LATITUDE = 45.483156  # CYUL 24R Latitude
CYUL_06L_LONGITUDE = -73.76474  # CYUL 06L Longitude
CYUL_24R_LONGITUDE = -73.73607  # CYUL 24R Longitude
CLEARED_ALTITUDE = 5000  # Cleared altitude for preset
VECTOR_HEADING = 330  # Vector heading for ATC instructions
FALSE_VECTOR_HEADING = 30  # False vector heading for ATC instructions (used in unreliable mode)
VECTOR_ALTITUDE = 3000  # Vector altitude for ATC instructions
AIRPORT_NAME = "Montreal Trudeau"  # Airport name for position reporting
### ENUMS ###
class ApprovalStatus:
    NOT_ANSWERED = 0
    APPROVED = 1
    DENIED = 2

# Agent Class
class TarsAgent:
    """
    TARS Agent - Pure Python implementation with no Qt dependencies
    Communicates via Ingescape bus using message protocol
    """
    
    def __init__(self, agent_name="TARS Agent", device=DEFAULT_DEVICE, port=5670, verbose=False):
        self.agent_name = agent_name
        self.device = device
        self.port = port
        self.verbose = verbose
        self.is_interrupted = False
        self.impulsion_count = 0

        # Speed reference parameters (for TTS interpolation)
        self.V_ONE = V_ONE
        self.V_ROTATE = V_ROTATE
        self.V_TWO = V_TWO
        self.V_ENR = V_ENR
        self.SEVENTY_KTS = SEVENTY_KTS
        self.RUNWAY_HEADING = RUNWAY_HEADING  # Will be set from clearance
        self.RUNWAY_NUMBER = RUNWAY_NUMBER  # Will be set from clearance
        self.TOWER_FREQUENCY = TOWER_FREQUENCY
        self.DEPARTURE_FREQUENCY = DEPARTURE_FREQUENCY
        self.TARS_RELIABLE: bool = TARS_RELIABLE  # Can be toggled at runtime via Ingescape
        self.popup_active: bool = False  # True while GUI has a modal dialog open; blocks joystick task_acknowledged
        # Editable wind values (updated by the wind-edit dialog in the GUI)
        self._wind_dir: int = 290 if not self.TARS_RELIABLE else 190   # degrees
        self._wind_mag: int = 4 if not self.TARS_RELIABLE else 8       # knots
        self.TO_PITCH = TO_PITCH # Takeoff pitch target
        self.SAFE_ALTITUDE = SAFE_ALTITUDE # Safe altitude to climb to after engine failure
        self.TRANSITION_ALTITUDE = TRANSITION_ALTITUDE  # Transition altitude in feet
        self.CLEARED_ALTITUDE = CLEARED_ALTITUDE  # Cleared altitude for preset
        #self.INITIAL_LATITUDE = CYUL_06L_LATITUDE  # To be set at start
        self.INITIAL_LATITUDE = CYUL_24R_LATITUDE  # To be set at start
        #self.INITIAL_LONGITUDE = CYUL_06L_LONGITUDE  # To be set at start
        self.INITIAL_LONGITUDE = CYUL_24R_LONGITUDE  # To be set at start
        self.AIRPORT_NAME = AIRPORT_NAME  # Airport name for position reporting
        self.PITCH_ANGLE_THRESHOLD = PITCH_ANGLE_THRESHOLD  # Minimum pitch angle to consider "maintained"
        self.PITCH_TEN_DEGREES = PITCH_TEN_DEGREES  # Minimum pitch angle to consider "maintained" 10 +- 2 degrees
        self.SLIP_SKID_THRESHOLD = SLIP_SKID_THRESHOLD  # Maximum slip/skid value to consider "maintained"
        self.POSITIVE_RATE_THRESHOLD = POSITIVE_RATE_THRESHOLD  # Minimum vertical speed to consider "positive rate"
        self.AUTOPILOT_ALTITUDE_THRESHOLD = AUTOPILOT_ALTITUDE_THRESHOLD  # Minimum altitude to engage autopilot
        self.VECTOR_HEADING = VECTOR_HEADING  # Vector heading for ATC instructions
        self.FALSE_VECTOR_HEADING = FALSE_VECTOR_HEADING  # False vector heading for ATC instructions (used in unreliable mode)
        self.VECTOR_ALTITUDE = VECTOR_ALTITUDE  # Vector altitude for ATC instructions
        self.ONE_THOUSAND_FIVE_HUNDRED_FEET = ONE_THOUSAND_FIVE_HUNDRED_FEET  # 1500 feet altitude threshold
        self.CURRENT_BRIEFING_EXPORT_LOADED = CURRENT_BRIEFING_EXPORT_LOADED

        # FSM setup
        self.task_acked = [False]
        #conditions
        self.is_on_off = [False]
        # Single approval state for current pending task
        self.task_approval_status = [ApprovalStatus.NOT_ANSWERED]  # 0 = not answered, 1 = approved, 2 = denied
        self.follow_vectors_status = [ApprovalStatus.NOT_ANSWERED]  # 0 = not answered, 1 = approved, 2 = denied
        self.engine_failed_side = "None"

        # Alert state tracking to prevent spam
        self.engine_spool_alert_sent = False
        
        # TTS completion event - will be set by external coordinator
        self.tts_completion_event = None
        
        # Thread management for continuous actions
        self.trim_thread = None
        self.trim_stop_event = threading.Event()
        
        # ATC thread management for parallel communication
        self.atc_thread = None
        self.atc_stop_event = threading.Event()
        
        # Countdown completion event - will be set by external coordinator
        self.countdown_completion_event = None
        
        # TTS speaking state tracking
        self.tts_speaking_before = False
        
        # Input-to-condition mapping for event-driven monitoring
        # Maps input names to condition function names that depend on them
        self.input_to_conditions = {
            'control_throttle': ['is_thrust_toga', 'is_throttle_clb'],
            'control_gear': ['is_gear_up'],
            'control_flaps': ['is_flaps_retracted', 'is_flaps_takeoff_pos'],
            'airspeed': ['is_airspeed_alive', 'is_seventy_kts', 'is_v_one', 'is_v_rotate', 'is_airspeed_v_two', 'is_v2_plus_10', 'is_v2_plus_12'],
            'altitude': ['is_400_ft_no_alarm', 'is_ap_altitude', 'is_v2_plus_12'],
            'master_warning': ['is_alarm', 'is_400_ft_no_alarm', 'is_master_warning_reset'],
            'e1_n1_percent': ['is_engine_spool_even', 'is_n1_percent_above_90', 'is_failed', 'is_not_failed'],
            'e2_n1_percent': ['is_engine_spool_even', 'is_n1_percent_above_90', 'is_failed', 'is_not_failed'],
            'vertical_speed': ['is_positive_rate'],
            'pitch': ['is_pitch_maintained'],
            'park_brake': ['is_brake_released'],
            'n1_match_bug': ['is_fadec_bug_to'],
            'l_throttle': ['is_throttle_idle', 'is_throttle_cutoff'],
            'r_throttle': ['is_throttle_idle', 'is_throttle_cutoff'],
            'fuel_boost_l': ['is_fuel_boost_off', 'is_fuel_boost_norm'],
            'fuel_boost_r': ['is_fuel_boost_off', 'is_fuel_boost_norm'],
            'test_knob': ['is_test_knob_turned'],
            'l_gen_switch': ['is_gen_switch_off'],
            'r_gen_switch': ['is_gen_switch_off'],
            'l_ign_switch': ['is_ignition_switch_norm'],
            'r_ign_switch': ['is_ignition_switch_norm'],
            'slip': ['is_slip_skid_centered'],
        }

        # Load task definitions with role allocations
        allocation_csv_path = Path(__file__).parent / self.CURRENT_BRIEFING_EXPORT_LOADED        
        # Create states from allocation CSV
        self.states = self.create_states_from_csv(allocation_csv_path)
        self.checklists = self.create_checklists_from_states(self.states)
        idle_key = ("IDLE", "Idle", "WAITING")
        finished_key = ("FINISHED", "Finished", "COMPLETED")
        self.fsm = FiniteStateMachine(self.states[(idle_key)])

        ###----------------------------------------------------------------------------------------------------------------###
        #------------------------------------------ CREW BRIEFING  ----------------------------------------------------------#
        ###----------------------------------------------------------------------------------------------------------------###
        # CREW BRIEFING Procedure (WANRAM Departure Memo)
        self.fsm.add_transition(Transition(
            self.states[("IDLE", "Idle", "WAITING")],
            self.states[("CREW BRIEFING", "START", "BRIEFING")],
            self.is_started,
            self.dummy_action))

        self.fsm.add_transition(Transition(
            self.states[("CREW BRIEFING", "START", "BRIEFING")],
            self.states[("CREW BRIEFING", "Weather", "BRIEF")],
            self.is_acked,
            action=lambda: self.crew_briefing_action("weather") if self.states[("CREW BRIEFING", "Weather", "BRIEF")].autonomy_role in ("performer", "supporter") else self.dummy_action()))

        self.fsm.add_transition(Transition(
            self.states[("CREW BRIEFING", "Weather", "BRIEF")], 
            self.states[("CREW BRIEFING", "Aircraft", "BRIEF")], 
            self.is_acked, 
            action=lambda: self.crew_briefing_action("aircraft") if self.states[("CREW BRIEFING", "Aircraft", "BRIEF")].autonomy_role in ("performer", "supporter") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("CREW BRIEFING", "Aircraft", "BRIEF")], 
            self.states[("CREW BRIEFING", "NOTAMs", "BRIEF")], 
            self.is_acked, 
            action=lambda: self.crew_briefing_action("notams") if self.states[("CREW BRIEFING", "NOTAMs", "BRIEF")].autonomy_role in ("performer", "supporter") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("CREW BRIEFING", "NOTAMs", "BRIEF")], 
            self.states[("CREW BRIEFING", "Routing", "BRIEF")], 
            self.is_acked, 
            action=lambda: self.crew_briefing_action("routing") if self.states[("CREW BRIEFING", "Routing", "BRIEF")].autonomy_role in ("performer", "supporter") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("CREW BRIEFING", "Routing", "BRIEF")], 
            self.states[("CREW BRIEFING", "Automation", "BRIEF")], 
            self.is_acked, 
            action=lambda: self.crew_briefing_action("automation") if self.states[("CREW BRIEFING", "Automation", "BRIEF")].autonomy_role in ("performer", "supporter") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("CREW BRIEFING", "Automation", "BRIEF")], 
            self.states[("CREW BRIEFING", "Miscellaneous", "BRIEF")], 
            self.is_acked, 
            action=lambda: self.crew_briefing_action("miscellaneous") if self.states[("CREW BRIEFING", "Miscellaneous", "BRIEF")].autonomy_role in ("performer", "supporter") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("CREW BRIEFING", "Miscellaneous", "BRIEF")], 
            self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")], 
            self.is_acked, 
            action=lambda: self.request_takeoff_clearance_action() if self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")].autonomy_role in ("performer", "supporter") else self.dummy_action(),
            transition_action = lambda: self.on_speak_action(f"I will now request takeoff clearance to montreal tower on {self.TOWER_FREQUENCY}, runway {self.RUNWAY_NUMBER} for straight out departure.") if self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")].autonomy_role == "performer" else self.dummy_action()))
        
        ###----------------------------------------------------------------------------------------------------------------###
        #------------------------------------------ BEFORE TAKEOFF  ---------------------------------------------------------#
        ###----------------------------------------------------------------------------------------------------------------###
        # BEFORE TAKEOFF Procedure
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")], 
            self.states[("BEFORE TAKEOFF", "FLAPS", "SET FOR TAKEOFF")], 
            lambda: self.allow_transition() if self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")].autonomy_role == "performer" else self.is_acked(),
            action=lambda: self.set_flaps_takeoff_send_signal() if self.states[("BEFORE TAKEOFF", "FLAPS", "SET FOR TAKEOFF")].autonomy_role == "performer" else self._run_check_with_live_updates(self.check_flaps_send_signals, ("BEFORE TAKEOFF", "FLAPS", "SET FOR TAKEOFF")),
            transition_action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_FLAPS_TAKEOFF, "")) if self.states[("BEFORE TAKEOFF", "FLAPS", "SET FOR TAKEOFF")].autonomy_role in ("supporter", "performer") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "FLAPS", "SET FOR TAKEOFF")], 
            self.states[("BEFORE TAKEOFF", "Pitot-Static Switch", "PITOT-STATIC")], 
            lambda: self.is_flaps_takeoff_pos() if self.states[("BEFORE TAKEOFF", "FLAPS", "SET FOR TAKEOFF")].autonomy_role == "performer" else self.is_acked(),
            action=lambda: self._run_check_with_live_updates(self.check_pitot_heat_send_signals, ("BEFORE TAKEOFF", "Pitot-Static Switch", "PITOT-STATIC")),
            transition_action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_PITOT_STATIC_SWITCH, "")) if self.states[("BEFORE TAKEOFF", "Pitot-Static Switch", "PITOT-STATIC")].autonomy_role == "supporter" else self.dummy_action()))

        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "Pitot-Static Switch", "PITOT-STATIC")], 
            self.states[("BEFORE TAKEOFF", "ENGINE ANTI-ICE Switches", "AS REQUIRED")], 
            lambda: self.is_pitot_heat_on() if self.states[("BEFORE TAKEOFF", "Pitot-Static Switch", "PITOT-STATIC")].autonomy_role == "performer" else self.is_acked(),
            action= lambda: igs.output_set_string("interaction_message", create_interaction_message("", self.INTERACTION_ENGINE_ANTI_ICE)) if self.states[("BEFORE TAKEOFF", "ENGINE ANTI-ICE Switches", "AS REQUIRED")].autonomy_role == "supporter" else self.dummy_action(),
            transition_action= lambda: self.on_speak_action("check") if self.states[("BEFORE TAKEOFF", "ENGINE ANTI-ICE Switches", "AS REQUIRED")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "ENGINE ANTI-ICE Switches", "AS REQUIRED")], 
            self.states[("BEFORE TAKEOFF", "WINDSHIELD ANTI-ICE Switches", "AS REQUIRED")], 
            self.is_acked, 
            action= lambda: igs.output_set_string("interaction_message", create_interaction_message("", self.INTERACTION_WINDSHIELD_ANTI_ICE)) if self.states[("BEFORE TAKEOFF", "WINDSHIELD ANTI-ICE Switches", "AS REQUIRED")].autonomy_role == "supporter" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "WINDSHIELD ANTI-ICE Switches", "AS REQUIRED")], 
            self.states[("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY")], 
            self.is_acked, 
            action= lambda: self._run_check_with_live_updates(self.check_pax_safety_send_signal, ("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY"))))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY")], 
            self.states[("BEFORE TAKEOFF", "LANDING Light Switch", "AS DESIRED")], 
            lambda: self.is_pax_safety_on() if self.states[("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY")].autonomy_role == "performer" else self.is_acked(),
            action= lambda: igs.output_set_string("interaction_message", create_interaction_message("", self.INTERACTION_LANDING_LIGHT_RUNWAY)) if self.states[("BEFORE TAKEOFF", "LANDING Light Switch", "AS DESIRED")].autonomy_role == "supporter" else self.dummy_action(),
            transition_action= lambda: self.on_speak_action("check") if self.states[("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "LANDING Light Switch", "AS DESIRED")], 
            self.states[("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON")], 
            self.is_acked, 
            action= lambda: self._run_check_with_live_updates(self.check_anti_coll_lights_send_signal, ("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON"))))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON")], 
            self.states[("BEFORE TAKEOFF", "EICAS", "CHECKED")], 
            lambda: self.is_anti_coll_lights_on() if self.states[("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON")].autonomy_role == "performer" else self.is_acked(), 
            action= lambda: self.dummy_action(),
            transition_action= lambda: self.on_speak_action("check") if self.states[("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON")].autonomy_role == "performer" else self.dummy_action()
            ))

        ###----------------------------------------------------------------------------------------------------------------###
        #------------------------------------------------- LINE-UP AND HOLD  ------------------------------------------------#
        ###----------------------------------------------------------------------------------------------------------------###
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "EICAS", "CHECKED")], 
            self.states[("LINE-UP AND HOLD", "Winds", "CHECK")], 
            self.is_acked, 
            action= lambda: self.check_winds_send_signal() if self.states[("LINE-UP AND HOLD", "Winds", "CHECK")].autonomy_role in ("supporter", "performer") else self.dummy_action(),
            transition_action= lambda: self.on_speak_action("Generating wind report") if self.states[("LINE-UP AND HOLD", "Winds", "CHECK")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("LINE-UP AND HOLD", "Winds", "CHECK")], 
            self.states[("LINE-UP AND HOLD", "Select Altitude", "PRESET AS CLEARED")], 
            self.is_acked, 
            action= lambda: self.select_altitude_action() if self.states[("LINE-UP AND HOLD", "Select Altitude", "PRESET AS CLEARED")].autonomy_role in ("performer", "supporter") else self.dummy_action()))

        self.fsm.add_transition(Transition(
            self.states[("LINE-UP AND HOLD", "Select Altitude", "PRESET AS CLEARED")], 
            self.states[("TAKEOFF", "CAS", "CHECK CLEAR")], 
            lambda: self.allow_transition() if self.states[("LINE-UP AND HOLD", "Select Altitude", "PRESET AS CLEARED")].autonomy_role == "performer" else self.is_acked(),
            action= lambda: self.send_reset_signal()))
        
        
        ###----------------------------------------------------------------------------------------------------------------###
        #------------------------------------------ TAKEOFF  ----------------------------------------------------------------#
        ###----------------------------------------------------------------------------------------------------------------###
        # TAKEOFF Procedure
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "CAS", "CHECK CLEAR")],
            self.states[("TAKEOFF", "THROTTLES", "TO Detent")],
            self.is_acked,
            action= lambda: self.recap_takeoff_speeds() if self.states[("TAKEOFF", "THROTTLES", "TO Detent")].autonomy_role in ("supporter", "performer") else self.dummy_action(),
            transition_action= self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "THROTTLES", "TO Detent")], 
            self.states[("TAKEOFF", "FADEC bug", "CHECK TO")], 
            lambda: self.is_thrust_toga() if self.states[("TAKEOFF", "THROTTLES", "TO Detent")].autonomy_role == "supporter" else self.is_acked(),
            action=lambda: self.check_fadec_bug_to_send_signal() if self.states[("TAKEOFF", "FADEC bug", "CHECK TO")].autonomy_role in ("performer", "supporter") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "FADEC bug", "CHECK TO")], 
            self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")], 
            lambda: self.is_fadec_bug_to() if self.states[("TAKEOFF", "FADEC bug", "CHECK TO")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action=lambda: self.check_engine_spool_send_signal() if self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")].autonomy_role in ("performer", "supporter") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")], 
            self.states[("TAKEOFF", "\"Airspeed's alive\"", "ANNOUNCE")], 
            lambda: self.is_engine_spool_even() if self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action= lambda: self.check_airspeed_alive_send_signal() if self.states[("TAKEOFF", "\"Airspeed's alive\"", "ANNOUNCE")].autonomy_role in ("performer", "supporter") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Airspeed's alive\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")], 
            lambda: self.is_airspeed_alive() if self.states[("TAKEOFF", "\"Airspeed's alive\"", "ANNOUNCE")].autonomy_role in ("performer", "supporter") else self.is_acked(),
            action= lambda: self.check_seventy_kts_send_signal() if self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")].autonomy_role in ("performer", "supporter") else self.dummy_action(),
            transition_action=lambda: self.on_speak_action(self.states[("TAKEOFF", "\"Airspeed's alive\"", "ANNOUNCE")].callout) if self.states[("TAKEOFF", "\"Airspeed's alive\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")], 
            lambda: self.is_seventy_kts() if self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")].autonomy_role in ("performer", "supporter") else self.is_acked(),
            action=lambda: self.check_v_one_send_signal() if self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")].autonomy_role in ("performer", "supporter") else self.dummy_action(),
            transition_action=lambda: self.on_speak_action(self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")].callout) if self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")], 
            lambda: self.is_v_one() if self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action=self.dummy_action,
            transition_action=lambda: self.on_speak_action(self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")].callout) if self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            lambda: self.is_v_rotate() and not self.is_alarm() if self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")].autonomy_role in ("performer", "supporter") else self.is_acked(),
            action=lambda: self.check_pitch_send_signal() if self.states[("TAKEOFF", "Pitch", "MAINTAIN 10°")].autonomy_role == "supporter" else self.dummy_action(),
            transition_action=lambda: self.on_speak_action(self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")].callout) if self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))

        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            self.states[("TAKEOFF", "Climb rate", "CHECK POSITIVE")], 
            lambda: self.is_pitch_above_threshold() and not self.is_alarm() if self.states[("TAKEOFF", "Pitch", "MAINTAIN 10°")].autonomy_role == "supporter" else self.is_acked(),
            action = lambda: self.check_positive_rate_send_signal() if self.states[("TAKEOFF", "Climb rate", "CHECK POSITIVE")].autonomy_role == "supporter" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Climb rate", "CHECK POSITIVE")], 
            self.states[("TAKEOFF", "LANDING GEAR", "UP")], 
            lambda: self.is_positive_rate() and not self.is_alarm() if self.states[("TAKEOFF", "Climb rate", "CHECK POSITIVE")].autonomy_role in ("performer", "supporter") else self.is_acked(),
            transition_action=lambda: self.on_speak_action("Positive rate, gear up") if self.states[("TAKEOFF", "LANDING GEAR", "UP")].autonomy_role == "supporter" else self.dummy_action()))
        
        # Branch: Normal path to AFTER TAKEOFF
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "LANDING GEAR", "UP")], 
            self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")], 
            lambda: self.is_safe_altitude_reached() if self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].autonomy_role in ("supporter","performer") else self.is_acked(),
            transition_action=lambda: self.on_speak_action(self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].callout) if self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].autonomy_role == "performer" else self.dummy_action(),
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_START_AFT_TO_CHECKLIST, "")) if self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].autonomy_role in ("supporter","performer") else self.dummy_action()))

        # Branch: Emergency path - ENGINE FAILURE DURING TAKEOFF AFTER V1 added transitions for EACH state after V1
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")],
            self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")],
            lambda: self.is_engine_failed() or self.is_alarm() if self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action=lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].autonomy_role in ("supporter", "performer") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")],
            self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")],
            lambda: self.is_engine_failed() or self.is_alarm() if self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action=lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].autonomy_role in ("supporter", "performer") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")], 
            lambda: self.is_engine_failed() or self.is_alarm() if self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action=lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].autonomy_role == "supporter" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Climb rate", "CHECK POSITIVE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")], 
            lambda : self.is_engine_failed() or self.is_alarm() if self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action=lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].autonomy_role == "supporter" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "LANDING GEAR", "UP")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")], 
            lambda: self.is_engine_failed() or self.is_alarm() if self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action=lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].autonomy_role == "supporter" else self.dummy_action()))

        ###----------------------------------------------------------------------------------------------------------------###
        #--------------------------------------- ENGINE FAILURE DURING TAKEOFF ----------------------------------------------#
        ###----------------------------------------------------------------------------------------------------------------###
        # ENG FAILURE DURING TAKEOFF transitions
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")],
            lambda: self.allow_transition() if self.states[("ENG FAILURE DURING TAKEOFF", "Climb", "TO A SAFE ALTITUDE")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            lambda: self.set_fd_to_mode() if self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")].autonomy_role == "performer" else self.dummy_action(),
            transition_action=lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")].autonomy_role == "performer" else self.dummy_action()))

        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            lambda: self.is_flight_director_on() if self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")].autonomy_role == "performer" else self.allow_transition(), 
            action=lambda: self.check_pitch_send_signal() if self.states[("ENG FAILURE DURING TAKEOFF", "Pitch", "MAINTAIN 10°")].autonomy_role == "supporter" else self.dummy_action()))

        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "LANDING GEAR", "UP")], 
            lambda: self.is_pitch_above_threshold() if self.states[("ENG FAILURE DURING TAKEOFF", "Pitch", "MAINTAIN 10°")].autonomy_role == "supporter" else self.is_acked(),
            action=lambda: self.check_gear_up_send_signal() if self.states[("ENG FAILURE DURING TAKEOFF", "LANDING GEAR", "UP")].autonomy_role == "supporter" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "LANDING GEAR", "UP")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2")], 
            lambda: self.is_gear_up() if self.states[("ENG FAILURE DURING TAKEOFF", "LANDING GEAR", "UP")].autonomy_role == "supporter" else self.is_acked(),
            action=lambda: self.check_v2_send_signal() if self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2")].autonomy_role in ("supporter", "performer") else self.dummy_action()))

        #Rudder TRIM transition with autonomy roles
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "TRIM")], 
            lambda: self.is_airspeed_above_v_two() if self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            transition_action=lambda: self.trim_action() if self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "TRIM")].autonomy_role == "performer" else self.dummy_action(),
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message("", "", left_button="DENY", right_button="APPROVE")) if self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "TRIM")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "TRIM")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")], 
            lambda: self.is_above_800_ft() if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_SET_SPD_MODE, "")) if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")].autonomy_role == "supporter" else self.dummy_action(),
            transition_action= lambda:  self.arm_speed_mode_send_signal()) if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")].autonomy_role in ("performer", "supporter") else self.dummy_action()) 

        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")], 
            lambda: self.is_speed_mode_on() or self.is_acked() if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")].autonomy_role in ("performer", "supporter") else self.is_acked(),
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_SET_HDG_MODE, "")) if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")].autonomy_role == "supporter" else self.dummy_action(),
            transition_action= lambda: self.arm_heading_mode_send_signal()) if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")].autonomy_role in ("performer", "supporter") else self.dummy_action()) 

        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")], 
            lambda: self.is_heading_mode_on() or self.is_acked() if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action=lambda: self.engage_autopilot_action() if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")].autonomy_role in ("performer", "supporter") else self.dummy_action(),
            transition_action= lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")].autonomy_role == "performer" else self.dummy_action()))

        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Alarm", "ANNOUNCE")], 
            lambda: self.is_slip_skid_centered() or self.task_approval_status[0] == ApprovalStatus.DENIED or self.flight_director_mode == 2 or self.is_acked(),
            action=lambda: igs.output_set_string("alert", create_alert_message(self.get_alert_engine_fire(), "red")) if self.states[("ENG FAILURE DURING TAKEOFF", "Alarm", "ANNOUNCE")].autonomy_role in ("supporter", "performer") else self.dummy_action(),
            transition_action=lambda: (self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Alarm", "ANNOUNCE")].callout), igs.output_set_string("interaction_message", create_interaction_message("", self.get_alarm_callout()))) if self.states[("ENG FAILURE DURING TAKEOFF", "Alarm", "ANNOUNCE")].autonomy_role in ("performer", "supporter") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Alarm", "ANNOUNCE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Check", "SAFE ALTITUDE REACHED")], 
            lambda: not self.is_master_warning_on() or self.is_acked() if self.states[("ENG FAILURE DURING TAKEOFF", "Alarm", "ANNOUNCE")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action= lambda: igs.output_set_string("interaction_message", create_interaction_message("", self.INTERACTION_SAFE_ALTITUDE_REACHED)) if self.states[("ENG FAILURE DURING TAKEOFF", "Check", "SAFE ALTITUDE REACHED")].autonomy_role in ("supporter", "performer") else self.dummy_action()))
        
        ###----------------------------------------------------------------------------------------------------------------###
        #------------------------------------- ENGINE FIRE Transitions ------------------------------------------------------#
        ###----------------------------------------------------------------------------------------------------------------###
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Check", "SAFE ALTITUDE REACHED")], 
            self.states[("ENGINE FIRE", "Throttle (affected engine)", "IDLE")],
            lambda: self.is_safe_altitude_reached() if self.states[("ENGINE FIRE", "Throttle (affected engine)", "IDLE")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action=lambda: self.throttle_idle_action() if self.states[("ENGINE FIRE", "Throttle (affected engine)", "IDLE")].autonomy_role == "supporter" else self.dummy_action(),
            transition_action=lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Check", "SAFE ALTITUDE REACHED")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "Check", "SAFE ALTITUDE REACHED")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Throttle (affected engine)", "IDLE")], 
            self.states[("ENGINE FIRE", "Chrono", "START")],
            lambda: self.is_throttle_idle() if self.states[("ENGINE FIRE", "Throttle (affected engine)", "IDLE")].autonomy_role == "supporter" else self.is_acked(),
            action=lambda: self.start_chrono_action() if self.states[("ENGINE FIRE", "Chrono", "START")].autonomy_role in ("performer", "supporter") else self.dummy_action(),
            transition_action= lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Chrono", "START")].callout) if self.states[("ENGINE FIRE", "Chrono", "START")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Chrono", "START")], 
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 15s")],
            lambda: self.is_acked(),
            action=lambda: self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 15s")], 
            self.states[("ENGINE FIRE", "Illuminated ENGINE FIRE Switch", "LIFT COVER AND PUSH")],
            lambda: self.allow_transition() if self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 15s")].autonomy_role == "supporter" else self.is_acked(),
            self.dummy_action,
            transition_action=lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 15s")].callout) if self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 15s")].autonomy_role == "supporter" else self.dummy_action()))
        
        # Autopilot engagement transitions
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Illuminated ENGINE FIRE Switch", "LIFT COVER AND PUSH")],
            self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 1500ft AGL")],
            lambda: self.is_acked() if self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 1500ft AGL")].autonomy_role == "supporter" else self.is_acked(),
            action=lambda: self._run_check_with_live_updates(self.check_1500_ft_send_signal, ("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 1500ft AGL"))))

        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 1500ft AGL")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2+10")],
            lambda: self.is_above_1500_ft() if self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 1500ft AGL")].autonomy_role == "performer" else self.is_acked(),
            action= lambda: self._run_check_with_live_updates(self.check_v2_plus_10_send_signal, ("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2+10")),
            transition_action= lambda: self.on_speak_action("altitude 1500 feet check") if self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 1500ft AGL")].autonomy_role == "performer" else self.dummy_action()))
            
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2+10")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Obstacles", "CHECK Clear")],
            lambda: self.is_above_v2_plus_10() if self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2+10")].autonomy_role == "performer" else self.is_acked(),
            action= lambda: self.dummy_action(),
            transition_action= lambda: self.on_speak_action("airspeed V2+10 check") if self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2+10")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Obstacles", "CHECK Clear")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "FLAP Handle", "UP")],
            self.is_acked,
            action=lambda: self.retract_flaps_send_signal() if self.states[("ENG FAILURE DURING TAKEOFF", "FLAP Handle", "UP")].autonomy_role == "performer" else self._run_check_with_live_updates(self.check_flaps_retracted_send_signal, ("ENG FAILURE DURING TAKEOFF", "FLAP Handle", "UP")),
            transition_action=lambda: (self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "FLAP Handle", "UP")].callout), igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_FLAPS_UP, ""))) if self.states[("ENG FAILURE DURING TAKEOFF", "FLAP Handle", "UP")].autonomy_role == "supporter" and not self.is_flaps_retracted() else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "FLAP Handle", "UP")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")], 
            lambda: self.is_flaps_retracted() if self.states[("ENG FAILURE DURING TAKEOFF", "FLAP Handle", "UP")].autonomy_role == "performer" else self.is_acked(),
            action=lambda: self.create_interaction_atc("mayday") if self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")].autonomy_role in ("performer", "supporter") else self.dummy_action(),
            transition_action= lambda: (setattr(self, 'task_approval_status', [ApprovalStatus.NOT_ANSWERED]), self.on_speak_action(f"Do you want me to announce emergency to Montreal departure on {self.DEPARTURE_FREQUENCY}? Approve or Deny")) if self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")], 
            self.states[("ENGINE FIRE", "Checklist", "ORDER START")], 
            lambda: self.is_allowed() and self.states[("ENGINE FIRE", "Checklist", "ORDER START")].autonomy_role == "performer" or self.is_acked() and self.states[("ENGINE FIRE", "Checklist", "ORDER START")].autonomy_role == "supporter" or self.is_acked() and self.states[("ENGINE FIRE", "Checklist", "ORDER START")].autonomy_role == None,
            action=lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Checklist", "ORDER START")].callout) if self.states[("ENGINE FIRE", "Checklist", "ORDER START")].autonomy_role == "performer" else self.dummy_action(),
            transition_action=lambda: (self.contact_atc_action("mayday"), setattr(self, "task_approval_status", [ApprovalStatus.NOT_ANSWERED])) if self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")].autonomy_role == "performer" else self.dummy_action()))
        
        # If not allowed to communicate, skip directly to checklist
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")], 
            self.states[("ENGINE FIRE", "Checklist", "ORDER START")], 
            self.is_denied, 
            action=lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Checklist", "ORDER START")].callout) if self.states[("ENGINE FIRE", "Checklist", "ORDER START")].autonomy_role == "performer" else self.dummy_action(),
            transition_action=lambda: (self.on_speak_action("Action denied"), setattr(self, 'task_approval_status', [ApprovalStatus.NOT_ANSWERED]))))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "READBACK")], 
            self.states[("ENGINE FIRE", "Checklist", "ORDER START")], 
            lambda: self.allow_transition() if self.states[("ENGINE FIRE", "Checklist", "ORDER START")].autonomy_role == "performer" else self.is_acked(), 
            action=lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Checklist", "ORDER START")].callout) if self.states[("ENGINE FIRE", "Checklist", "ORDER START")].autonomy_role == "performer" else self.dummy_action(),
            transition_action=lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Checklist", "ORDER START")].callout) if self.states[("ENGINE FIRE", "Checklist", "ORDER START")].autonomy_role == "performer" else self.dummy_action()))
        
        # to ENGINE FIRE procedure
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Checklist", "ORDER START")], 
            self.states[("ENGINE FIRE", "Immediate Action Item", "CHECK DONE")], 
            lambda: self.allow_transition() if self.states[("ENGINE FIRE", "Checklist", "ORDER START")].autonomy_role == "performer" else self.is_acked(), 
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message("", self.get_immediate_action_items(), "")) if self.states[("ENGINE FIRE", "Immediate Action Item", "CHECK DONE")].autonomy_role == "supporter" else self.dummy_action(),
            transition_action=lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Immediate Action Item", "CHECK DONE")].callout) if self.states[("ENGINE FIRE", "Immediate Action Item", "CHECK DONE")].autonomy_role == "supporter" else self.dummy_action()))
        
        # ENGINE FIRE transitions
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Immediate Action Item", "CHECK DONE")], 
            self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "OFF")], 
            self.is_acked, 
            action=lambda: self._run_check_with_live_updates(self.check_fuel_boost_off_send_signal, ("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "OFF")),
            transition_action=lambda: self.on_speak_action(self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "OFF")].callout) if self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "OFF")].autonomy_role == "supporter" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "OFF")], 
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 30s")], 
            lambda: self.is_fuel_boost_off() if self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "OFF")].autonomy_role == "performer" else self.is_acked(), 
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.get_interaction_check_engine_fire_light(), "")) if self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 30s")].autonomy_role in ("performer","supporter") else self.dummy_action(),
            transition_action=lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 30s")].callout) if self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 30s")].autonomy_role in ("performer","supporter") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 30s")], 
            self.states[("ENGINE FIRE", "Illuminated BOTTLE ARMED Switch", "PUSH")], 
            lambda: self.allow_transition() if self.states[("ENGINE FIRE", "Illuminated BOTTLE ARMED Switch", "PUSH")].autonomy_role in ("performer", "supporter") else self.is_acked(),
            action= lambda: self._run_check_with_live_updates(self.check_bottle_pushed_send_signals, ("ENGINE FIRE", "Illuminated BOTTLE ARMED Switch", "PUSH")) if self.states[("ENGINE FIRE", "Illuminated BOTTLE ARMED Switch", "PUSH")].autonomy_role == "supporter" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Illuminated BOTTLE ARMED Switch", "PUSH")], 
            self.states[("ENGINE FIRE", "Test", "FIRE WARN")], 
            lambda: self.is_bottle_pushed() if self.states[("ENGINE FIRE", "Illuminated BOTTLE ARMED Switch", "PUSH")].autonomy_role == "performer" else self.is_acked(), 
            action=lambda: self._run_check_with_live_updates(self.check_fire_warn_test_send_signals, ("ENGINE FIRE", "Test", "FIRE WARN")) if self.states[("ENGINE FIRE", "Test", "FIRE WARN")].autonomy_role == "supporter" else self.dummy_action(),
            transition_action=lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Test", "FIRE WARN")].callout) if self.states[("ENGINE FIRE", "Test", "FIRE WARN")].autonomy_role in ("supporter", "performer") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Test", "FIRE WARN")], 
            self.states[("ENGINE FIRE", "Engine fire lights", "Check both illuminate")], 
            lambda: self.is_test_knob_turned() if self.states[("ENGINE FIRE", "Test", "FIRE WARN")].autonomy_role == "performer" else self.is_acked(),
            self.dummy_action,
            transition_action=lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Engine fire lights", "Check both illuminate")].callout) if self.states[("ENGINE FIRE", "Engine fire lights", "Check both illuminate")].autonomy_role in ("supporter", "performer") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Engine fire lights", "Check both illuminate")], 
            self.states[("ENGINE FIRE", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")], 
            self.is_acked, 
            self.dummy_action,
            transition_action=lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")].callout) if self.states[("ENGINE FIRE", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")].autonomy_role in ("supporter", "performer") else self.dummy_action()))

        ###----------------------------------------------------------------------------------------------------------------###
        #------------------------------------------- PANPAN Transitions -----------------------------------------------------#
        ###----------------------------------------------------------------------------------------------------------------###
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")], 
            self.states[("DECLARE PANPAN", "ATC", "ANNOUNCE PANPAN AND REQUEST VECTOR")], 
            lambda: self.allow_transition() if self.states[("ENGINE FIRE", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")].autonomy_role == "performer" else self.is_acked(), 
            action=lambda: self.create_interaction_atc("panpan") if self.states[("DECLARE PANPAN", "ATC", "ANNOUNCE PANPAN AND REQUEST VECTOR")].autonomy_role in ("supporter", "performer") else self.dummy_action(),
            transition_action= lambda: (setattr(self, 'task_approval_status', [ApprovalStatus.NOT_ANSWERED]), self.on_speak_action(f"Do you want me to announce PANPAN to Montreal Departure on {self.DEPARTURE_FREQUENCY}? Approve or Deny")) if self.states[("DECLARE PANPAN", "ATC", "ANNOUNCE PANPAN AND REQUEST VECTOR")].autonomy_role == "performer" else self.dummy_action()))
        
        # if PANPAN not accepted, skip to AFTER TAKEOFF
        self.fsm.add_transition(Transition(
            self.states[("DECLARE PANPAN", "ATC", "ANNOUNCE PANPAN AND REQUEST VECTOR")],
            self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")],
            lambda: self.is_denied() and self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].autonomy_role == "performer" or self.is_acked() and self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].autonomy_role == "supporter" or self.is_acked() and self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].autonomy_role == None,
            self.dummy_action,
            transition_action=lambda: ((self.on_speak_action("Action denied"), setattr(self, 'task_approval_status', [ApprovalStatus.NOT_ANSWERED]))[0] if self.states[("DECLARE PANPAN", "ATC", "ANNOUNCE PANPAN AND REQUEST VECTOR")].autonomy_role == "performer" else self.dummy_action())))
        
        # If TARS allowed
        self.fsm.add_transition(Transition(
            self.states[("DECLARE PANPAN", "ATC", "ANNOUNCE PANPAN AND REQUEST VECTOR")], 
            self.states[("DECLARE PANPAN", "ATC", "READBACK")],
            self.is_allowed,
            lambda: self.send_vector_signals(),
            transition_action=lambda: self.contact_atc_action("panpan") if self.states[("DECLARE PANPAN", "ATC", "ANNOUNCE PANPAN AND REQUEST VECTOR")].autonomy_role in ("supporter", "performer") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("DECLARE PANPAN", "ATC", "READBACK")], 
            self.states[("DECLARE PANPAN", "Heading", "SET ACCORDINGLY")], 
            lambda: self.is_denied(),
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.get_interaction_set_heading(), "")),
            transition_action=lambda: (self.on_speak_action("Action denied"), setattr(self, 'follow_vectors_status', [ApprovalStatus.DENIED])) if self.states[("DECLARE PANPAN", "Heading", "SET ACCORDINGLY")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("DECLARE PANPAN", "ATC", "READBACK")], 
            self.states[("DECLARE PANPAN", "Heading", "SET ACCORDINGLY")], 
            lambda: self.is_allowed(),
            action=lambda: self.set_heading_action() if self.states[("DECLARE PANPAN", "Heading", "SET ACCORDINGLY")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("DECLARE PANPAN", "Heading", "SET ACCORDINGLY")], 
            self.states[("DECLARE PANPAN", "Altitude", "SET ACCORDINGLY")], 
            lambda: self.is_heading_set() if self.states[("DECLARE PANPAN", "Heading", "SET ACCORDINGLY")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_SET_ALTITUDE, "")) if self.states[("DECLARE PANPAN", "Altitude", "SET ACCORDINGLY")].autonomy_role in ("supporter", "performer") else self.dummy_action(),
            transition_action=lambda: self.set_altitude_action() if self.states[("DECLARE PANPAN", "Altitude", "SET ACCORDINGLY")].autonomy_role == "performer" and getattr(self, 'task_approval_status', [ApprovalStatus.APPROVED]) else self.dummy_action()))
        
        ###----------------------------------------------------------------------------------------------------------------###
        #------------------------------------------- AFTER TAKEOFF Transitions ----------------------------------------------#
        ###----------------------------------------------------------------------------------------------------------------###
        # Continue to AFTER TAKEOFF from DECLARE PANPAN
        self.fsm.add_transition(Transition(
            self.states[("DECLARE PANPAN", "Altitude", "SET ACCORDINGLY")], 
            self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")], 
            lambda: self.is_altitude_set() if self.states[("DECLARE PANPAN", "Altitude", "SET ACCORDINGLY")].autonomy_role in ("supporter", "performer") else self.is_acked(),
            action= lambda: setattr(self, 'task_approval_status', [ApprovalStatus.NOT_ANSWERED]),
            transition_action=lambda: self.on_speak_action(self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].callout) if self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].autonomy_role == "performer" else self.dummy_action()))
        
        # AFTER TAKEOFF transitions (normal path)
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")], 
            self.states[("AFTER TAKEOFF", "LANDING GEAR Handle", "UP")], 
            lambda: self.allow_transition() if self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].autonomy_role == "performer" else self.is_acked(),
            self.dummy_action,
            self.check_gear_up_send_signal,))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "LANDING GEAR Handle", "UP")], 
            self.states[("AFTER TAKEOFF", "Airspeed", "CHECK V2 + 10")], 
            lambda: self.is_gear_up() if self.states[("AFTER TAKEOFF", "LANDING GEAR Handle", "UP")].autonomy_role == "performer" else self.is_acked(),
            action= lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_CHECK_V2_PLUS_10, self.get_interaction_current_airspeed())) if self.states[("AFTER TAKEOFF", "Airspeed", "CHECK V2 + 10")].autonomy_role == "supporter" else self.dummy_action(),
            transition_action=lambda: self.check_v2_plus_10_send_signal() if self.states[("AFTER TAKEOFF", "Airspeed", "CHECK V2 + 10")].autonomy_role == "supporter" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Airspeed", "CHECK V2 + 10")], 
            self.states[("AFTER TAKEOFF", "Obstacles", "CHECK CLEAR")], 
            lambda: self.is_above_v2_plus_10() if self.states[("AFTER TAKEOFF", "Airspeed", "CHECK V2 + 10")].autonomy_role == "performer" else self.is_acked(), 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Obstacles", "CHECK CLEAR")], 
            self.states[("AFTER TAKEOFF", "FLAP Handle", "UP")], 
            self.is_acked,
            action=lambda: self.retract_flaps_send_signal() if self.states[("AFTER TAKEOFF", "FLAP Handle", "UP")].autonomy_role == "performer" else self.dummy_action(),
            transition_action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_FLAPS_UP, "")) if self.states[("AFTER TAKEOFF", "FLAP Handle", "UP")].autonomy_role in ("supporter", "performer") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "FLAP Handle", "UP")], 
            self.states[("AFTER TAKEOFF", "THROTTLES", "CLB Detent")], 
            lambda: self.is_flaps_retracted() if self.states[("AFTER TAKEOFF", "FLAP Handle", "UP")].autonomy_role == "performer" else self.is_acked(),
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "THROTTLES", "CLB Detent")], 
            self.states[("AFTER TAKEOFF", "Yaw Damper", "AS DESIRED")], 
            lambda: self.is_throttle_clb() if self.states[("AFTER TAKEOFF", "THROTTLES", "CLB Detent")].autonomy_role == "supporter" else self.is_acked(), 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Yaw Damper", "AS DESIRED")], 
            self.states[("AFTER TAKEOFF", "Anti-Ice/Deice Systems", "AS REQUIRED")], 
            self.is_acked, 
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.get_interaction_engage_yaw_damper(), "")) if self.states[("AFTER TAKEOFF", "Yaw Damper", "AS DESIRED")].autonomy_role in ("supporter","performer") else self.dummy_action(),
            transition_action=lambda: self.engage_yaw_damper_action() if self.states[("AFTER TAKEOFF", "Yaw Damper", "AS DESIRED")].autonomy_role == "performer"  else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Anti-Ice/Deice Systems", "AS REQUIRED")], 
            self.states[("AFTER TAKEOFF", "PAX SAFETY Switch", "AS REQUIRED")], 
            self.is_acked, 
            action= lambda: igs.output_set_string("interaction_message", create_interaction_message(self.get_interaction_pax_safety_switch(), "")) if self.states[("BEFORE TAKEOFF", "WINDSHIELD ANTI-ICE Switches", "AS REQUIRED")].autonomy_role == "supporter" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "PAX SAFETY Switch", "AS REQUIRED")], 
            self.states[("AFTER TAKEOFF", "LANDING Light Switch", "AS REQUIRED")], 
            self.is_acked, 
            action= lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_LANDING_LIGHT_AFTER_TAKEOFF, "")) if self.states[("AFTER TAKEOFF", "LANDING Light Switch", "AS REQUIRED")].autonomy_role == "supporter" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "LANDING Light Switch", "AS REQUIRED")], 
            self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")], 
            self.is_acked, 
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_PRESSURIZATION_CHECK, "")) if self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")].autonomy_role in ("supporter","performer") else self.dummy_action(),
            transition_action=lambda: (self.on_speak_action(self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")].callout), self.check_cab_alt_send_signal()) if self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")], 
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")], 
            lambda: self.is_cab_alt_ok() if self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")].autonomy_role in ("performer","supporter") else self.is_acked(),
            self.dummy_action,
            transition_action=lambda: self.on_speak_action(self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")].callout) if self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")].autonomy_role == "performer" else self.dummy_action()))
        
        #will be skipped for now because transition altitude is likely not reached during the test flight
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")], 
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "CROSSCHECK")], 
            lambda: self.is_transition_altitude_reached() if self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")].autonomy_role == "performer" else self.is_acked(),
            lambda: (igs.output_set_double("altimeter_setting", 29.92), self.on_speak_action("Setting altimeter to standard pressure")) if self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")], 
            self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")], 
            lambda: self.allow_transition() if self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")].autonomy_role == "performer" else self.is_acked(),
            self.dummy_action,
            transition_action=lambda: self.on_speak_action(self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")].callout) if self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "CROSSCHECK")], 
            self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")], 
            self.is_acked, 
            self.dummy_action,
            transition_action=lambda: self.on_speak_action(self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")].callout) if self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")].autonomy_role == "performer" else self.dummy_action()))
        
        # Branch: Normal completion 
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")], 
            self.states[finished_key], 
            self.is_engine_not_failed, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")], 
            self.states[("AFTER TAKEOFF", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")], 
            lambda: self.is_engine_failed() if self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")].autonomy_role == "performer" else self.is_acked(),
            self.dummy_action,
            lambda: self.on_speak_action(self.states[("AFTER TAKEOFF", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")].callout) if self.states[("AFTER TAKEOFF", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")].autonomy_role == "performer" else self.dummy_action()))
        
        ###----------------------------------------------------------------------------------------------------------------###
        #--------------------------- ENGINE FAILURE/PRECAUTIONARY SHUTDOWN Transitions --------------------------------------#
        ###----------------------------------------------------------------------------------------------------------------###
        # ENGINE FAILURE/PRECAUTIONARY SHUTDOWN transitions
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Checklist", "ORDER START")], 
            lambda: self.allow_transition() if self.states[("AFTER TAKEOFF", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")].autonomy_role == "performer" else self.is_acked(),
            self.dummy_action,
            lambda: self.on_speak_action(self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Checklist", "ORDER START")].callout) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Checklist", "ORDER START")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Checklist", "ORDER START")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Throttle (affected engine)", "CUTOFF")], 
            lambda: self.allow_transition() if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Checklist", "ORDER START")].autonomy_role == "performer" else self.is_acked(), 
            action= lambda: igs.output_set_string("interaction_message", create_interaction_message(self.get_interaction_throttle_cutoff(), "")) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Throttle (affected engine)", "CUTOFF")].autonomy_role in ("supporter","performer") else self.dummy_action(),
            transition_action=lambda: self.check_engine_cutoff() if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Throttle (affected engine)", "CUTOFF")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Throttle (affected engine)", "CUTOFF")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "CAUTION text", "READ")], 
            lambda: self.is_throttle_idle() if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Throttle (affected engine)", "CUTOFF")].autonomy_role == "supporter" else self.is_acked(),
            action= lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_CAUTION_TEXT_READOUT, "")) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "CAUTION text", "READ")].autonomy_role in ("supporter","performer") else self.dummy_action(),
            transition_action=lambda: self.on_speak_action(self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "CAUTION text", "READ")].callout) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "CAUTION text", "READ")].autonomy_role == "performer" else self.dummy_action())) 
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "CAUTION text", "READ")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "GEN Switch (affected side)", "OFF")], 
            lambda: self.allow_transition() if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "CAUTION text", "READ")].autonomy_role in ("supporter","performer") else self.is_acked(),
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.get_interaction_gen_switch_off(), "")) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "GEN Switch (affected side)", "OFF")].autonomy_role in ("supporter","performer") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "GEN Switch (affected side)", "OFF")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "IGNITION switch (affected side)", "NORM")], 
            lambda: self.is_gen_switch_off() if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "GEN Switch (affected side)", "OFF")].autonomy_role == "supporter" else self.is_acked(),
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.get_interaction_ignition_switch_norm(), "")) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "IGNITION switch (affected side)", "NORM")].autonomy_role in ("supporter","performer") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "IGNITION switch (affected side)", "NORM")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Electrical Load", "REDUCE as required (<= 300A)")], 
            lambda: self.is_ignition_switch_norm() if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "IGNITION switch (affected side)", "NORM")].autonomy_role == "supporter" else self.is_acked(),
            transition_action=lambda: self.check_electrical_load_action() if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Electrical Load", "REDUCE as required (<= 300A)")].autonomy_role == "performer" else self.dummy_action(),
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_REDUCE_ELECTRICAL_LOAD, "")) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Electrical Load", "REDUCE as required (<= 300A)")].autonomy_role in ("supporter","performer") else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Electrical Load", "REDUCE as required (<= 300A)")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Fuel TRANSFER Knob", "AS REQUIRED")], 
            lambda: self.is_electrical_load_under_limit() if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Electrical Load", "REDUCE as required (<= 300A)")].autonomy_role in ("supporter","performer") else self.is_acked(),
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_FUEL_TRANSFER_KNOB, "")) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Fuel TRANSFER Knob", "AS REQUIRED")].autonomy_role in ("supporter","performer") else self.dummy_action(),
            transition_action=lambda: self.on_transfer_fuel_action() if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Fuel TRANSFER Knob", "AS REQUIRED")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Fuel TRANSFER Knob", "AS REQUIRED")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Verify ENGINE FIRE Switch (affected side)", "Is pushed")], 
            lambda: self.allow_transition() if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Verify ENGINE FIRE Switch (affected side)", "Is pushed")].autonomy_role in ("supporter","performer") else self.is_acked(), 
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_VERIFY_ENGINE_FIRE_SWITCH, "")) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Verify ENGINE FIRE Switch (affected side)", "Is pushed")].autonomy_role == "supporter" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Verify ENGINE FIRE Switch (affected side)", "Is pushed")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Next checklist", "SINGLE-ENGINE APPROACH AND LANDING")], 
            self.is_acked, 
            action=lambda: igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_NEXT_CHECKLIST_SINGLE_ENGINE_APPROACH, "")) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Next checklist", "SINGLE-ENGINE APPROACH AND LANDING")].autonomy_role in ("supporter","performer") else self.dummy_action(),
            transition_action=lambda: self.on_speak_action(self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Next checklist", "SINGLE-ENGINE APPROACH AND LANDING")].callout) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Next checklist", "SINGLE-ENGINE APPROACH AND LANDING")].autonomy_role == "performer" else self.dummy_action()))

        # Final transition to FINISHED
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Next checklist", "SINGLE-ENGINE APPROACH AND LANDING")], 
            self.states[finished_key], 
            self.allow_transition, 
            self.dummy_action))
        
        # Normal completion path (no failure)
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")], 
            self.states[finished_key], 
            lambda: self.is_engine_not_failed() if self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")].autonomy_role == "performer" else self.is_acked(), 
            self.dummy_action))

        self.agent = Echo()
        
    # END INITIALIZATION OF FSM AND STATES

    # ===================================================================
    # PROPERTIES - Dynamic computed values for TTS interpolation
    # These properties always return the current value from self.agent
    # ===================================================================
    @property
    def altitude(self):
        """Current altitude (dynamically fetched)"""
        return int(self.agent.altitude_i) if self.agent.altitude_i is not None else 0
    
    @property
    def airspeed(self):
        """Current airspeed (dynamically fetched)"""
        return int(self.agent.airspeed_i) if self.agent.airspeed_i is not None else 0
    
    @property
    def heading(self):
        """Current heading (dynamically fetched)"""
        return int(self.agent.heading_i) if self.agent.heading_i is not None else 0
    
    @property
    def vertical_speed(self):
        """Current vertical speed (dynamically fetched)"""
        return int(self.agent.vertical_speed_i) if self.agent.vertical_speed_i is not None else 0
    
    @property
    def pitch(self):
        """Current pitch (dynamically fetched)"""
        return self.agent.pitch_i if self.agent.pitch_i is not None else 0
    
    @property
    def e1_n1_percent(self):
        """Left engine N1 percentage (dynamically fetched)"""
        return int(self.agent.e1_n1_percent_i) if self.agent.e1_n1_percent_i is not None else 0
    
    @property
    def e2_n1_percent(self):
        """Right engine N1 percentage (dynamically fetched)"""
        return int(self.agent.e2_n1_percent_i) if self.agent.e2_n1_percent_i is not None else 0
    
    @property
    def cabin_altitude(self):
        """Cabin altitude (dynamically fetched)"""
        return int(self.agent.cabin_altitude_i) if self.agent.cabin_altitude_i is not None else 0
    
    @property
    def flight_director_mode(self):
        """Flight director mode (dynamically fetched)"""
        return self.agent.flight_director_i if self.agent.flight_director_i is not None else "N/A"
    
    @property
    def speed_mode(self):
        """Speed mode (dynamically fetched)"""
        return self.agent.speed_mode_i if self.agent.speed_mode_i is not None else "N/A"
    
    @property
    def heading_mode(self):
        """Heading mode (dynamically fetched)"""
        return self.agent.heading_mode_i if self.agent.heading_mode_i is not None else "N/A"

    @property
    def altitude_rounded(self):
        """Current altitude rounded to nearest 100 feet for cleaner TTS output"""
        if self.agent.altitude_i is not None:
            return int(round(self.agent.altitude_i / 100.0) * 100)
        else:
            return 0
    
    @property
    def position_compared_to_initial(self):
        """Calculate position relative to initial coordinates (e.g., '5nm north of Montreal Trudeau')"""
        if self.agent.latitude_i is None or self.agent.longitude_i is None:
            return f"position unknown from {self.AIRPORT_NAME}"
        
        lat1, lon1 = math.radians(self.INITIAL_LATITUDE), math.radians(self.INITIAL_LONGITUDE)
        lat2, lon2 = math.radians(self.agent.latitude_i), math.radians(self.agent.longitude_i)
        
        # Haversine formula for distance in nautical miles
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        distance_nm = 3440.065 * c  # Earth radius in nautical miles
        
        # Calculate bearing
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        bearing = math.degrees(math.atan2(y, x))
        bearing = (bearing + 360) % 360  # Normalize to 0-360
        
        # Convert bearing to cardinal direction
        directions = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]
        idx = round(bearing / 45) % 8
        direction = directions[idx]
        
        # Format output
        if distance_nm < 0.5:
            return f"overhead {self.AIRPORT_NAME}"
        else:
            return f"{distance_nm:.1f} nautical miles {direction} of {self.AIRPORT_NAME}"
    
    # ===================================================================
    # END PROPERTIES
    # ===================================================================

    def create_states_from_csv(self, csv_path):
        """Create states from allocation CSV with task definitions and role assignments
        
        Args:
            csv_path: Path to briefing_export_MRP.csv with complete task data and role allocations
        """
        states = {}
        
        # Create an IDLE state with composite key
        idle_state = State(
            procedure="IDLE",
            classification="NORM",
            type="Other",
            category="System State",
            task_object="Idle",
            value="WAITING",
            human_role="Performer",
            autonomy_role=None,
            information_requirement=None,
            interaction="Start Button",
            delay_before_action=0,
            delay_after_action=0,
            callout=None
        )
        # Use tuple as composite key: (procedure, classification, task_object, value)
        idle_key = (idle_state.procedure, idle_state.task_object, idle_state.value)
        states[idle_key] = idle_state
        
        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Extract fields for composite key
                procedure = row.get('Procedure', '').strip()
                task_object = row.get('Task Object', '').strip()
                value = row.get('Value', '').strip()
                
                # Skip empty rows
                if not procedure or not task_object:
                    continue
                
                # Create composite key as tuple
                state_key = (procedure, task_object, value)
                
                # Only add if key doesn't already exist (prevents duplicates)
                if state_key not in states:
                    # Extract all fields directly from the allocation CSV
                    classification = row.get('Classification', '').strip()
                    task_type = row.get('Type', '').strip()
                    category = row.get('Category', '').strip()
                    human_role = row.get('Human Role', '').strip()
                    autonomy_role = row.get('Autonomy Role', '').strip()
                    information_requirement = row.get('Information Requirement', '').strip()
                    interaction = row.get('interaction', '').strip()
                    
                    # Parse delay_before_action - handle 'is_acked' special case
                    delay_before_str = str(row.get('Time to Initiate Action', 0) or 0).strip().lower()
                    if delay_before_str == 'is_acked':
                        delay_before_action = 'is_acked'
                    else:
                        try:
                            delay_before_action = float(delay_before_str)
                        except ValueError:
                            delay_before_action = 0
                    
                    # Parse delay_after_action - handle 'is_acked' special case
                    delay_after_str = str(row.get('Time after Ending Action', 0) or 0).strip().lower()
                    if delay_after_str == 'is_acked':
                        delay_after_action = 'is_acked'
                    else:
                        try:
                            delay_after_action = float(delay_after_str)
                        except ValueError:
                            delay_after_action = 0
                    
                    callout = row.get('Callout', '').strip()
                    
                    # Parse condition monitoring fields
                    condition_type = row.get('Condition Type', '').strip().lower()
                    if not condition_type:
                        condition_type = None
                    
                    condition_function = row.get('Condition Function', '').strip()
                    if not condition_function:
                        condition_function = None
                    
                    monitor_scope = row.get('Monitor Scope', '').strip().lower()
                    if not monitor_scope:
                        monitor_scope = None
                    
                    # Create State object
                    state = State(
                        procedure=procedure,
                        classification=classification,
                        type=task_type,
                        category=category,
                        task_object=task_object,
                        value=value,
                        human_role=human_role,
                        autonomy_role=autonomy_role,
                        information_requirement=information_requirement,
                        interaction=interaction,
                        delay_before_action=delay_before_action,
                        delay_after_action=delay_after_action,
                        callout=callout,
                        condition=None,  # Initialize as None (will be set to True/False during monitoring)
                        condition_type=condition_type,
                        condition_function=condition_function,
                        monitor_scope=monitor_scope
                    )
                    states[state_key] = state
                else:
                    # Key already exists, handle accordingly (e.g., log a warning)
                    print(f"State {state_key} already exists. Skipping.")
        end_state = State(
            procedure="FINISHED",
            classification="NORM",
            type="Other",
            category="System State",
            task_object="Finished",
            value="COMPLETED",
            human_role="Performer",
            autonomy_role=None,
            information_requirement=None,
            interaction="End State",
            delay_before_action=0,
            delay_after_action=0,
            callout=None
        )
        end_key = (end_state.procedure, end_state.task_object, end_state.value)
        states[end_key] = end_state
        return states
    
    def create_checklists_from_states(self, states):
        checklists = {}
        for state in states.values():
            if state.type is not None and state.type == "Checklist":
                checklist_item = {
                    "procedure": state.procedure,
                    "task_object": state.task_object,
                    "value": state.value,
                }
                if state.procedure not in checklists:
                    checklists[state.procedure] = []
                    checklists[state.procedure].append(checklist_item)
                else:
                    checklists[state.procedure].append(checklist_item)
        return checklists

    def is_started(self):
        if self.is_on_off[0]:
            return True
        return False
    
    def allow_transition(self):
        """Always returns True - timing is managed by main.py using delay_before_action and delay_after_action"""
        return True

    def is_allowed(self):
        """Check if current task is approved"""
        return self.task_approval_status[0] == ApprovalStatus.APPROVED
    
    def is_denied(self):
        """Check if current task is denied"""
        return self.task_approval_status[0] == ApprovalStatus.DENIED
    
    def is_acked(self):
        # Don't reset the flag here - it should persist until state changes
        # The flag will be reset by the FSM after successful transition
        return self.task_acked[0]
    
    def is_heading_set(self):
        if self.agent.heading_sel_i is not None and abs(self.agent.heading_sel_i - self.VECTOR_HEADING) <= 2:
            return True
        return False
    
    def is_altitude_set(self):
        if self.agent.alt_sel_i is not None and abs(self.agent.alt_sel_i - self.VECTOR_ALTITUDE) <= 100:
            return True
        return False
    
    def is_pax_safety_on(self):
        if self.agent.pax_safety_i is not None and self.agent.pax_safety_i:
            return True
        return False
    
    def is_anti_coll_lights_on(self):
        if self.agent.anti_coll_lights_i is not None and self.agent.anti_coll_lights_i:
            return True
        return False
    
    def is_cab_alt_ok(self):
        if self.agent.cabin_altitude_i is not None and self.agent.cabin_altitude_i < 8000:
            # Send cabin altitude info to UI
            return True
        elif self.agent.cabin_altitude_i is not None:
            return False
        return False
    
    def _run_check_with_live_updates(self, display_func, state_key, interval=0.5):
        """
        Execute a check/display function. In supporter mode, keep re-running
        it until the task is acknowledged, so the display stays in sync with
        live sim values (e.g. switch flipped from OFF → ON).
        In performer mode, run once (the FSM condition check handles auto-advancing).
        """
        role = self.states[state_key].autonomy_role
        if role == "supporter":
            display_func()
            while not self.task_acked[0] and not self.is_interrupted:
                time.sleep(interval)
                display_func()
        elif role == "performer":
            display_func()

    def check_cab_alt_send_signal(self):
        if self.agent.cabin_altitude_i is not None:
            message = f"Cabin Altitude: {self.agent.cabin_altitude_i:.0f} ft"
            tars_input = f"Cabin Altitude above 8000 ft!" if self.agent.cabin_altitude_i >= 8000 else f"Cabin Altitude is within normal limits. (OK - below 8000 ft)"
            igs.output_set_string("interaction_message", create_interaction_message(message, tars_input))
    
    def check_1500_ft_send_signal(self):
        if self.agent.altitude_i is not None:
            message = f"Altitude: {self.agent.altitude_i:.0f} ft"
            tars_input = f"Altitude above 1500 ft." if self.agent.altitude_i >= 1500 else f"Altitude below 1500 ft."
            igs.output_set_string("interaction_message", create_interaction_message(message, tars_input))
    
    def check_v2_plus_10_send_signal(self):
        global V_TWO
        v2_plus_10 = V_TWO + 10
        if self.agent.airspeed_i is not None:
            message = f"Airspeed: {self.agent.airspeed_i:.0f} kts"
            tars_input = f"Airspeed above V2 + 10 kts ({v2_plus_10} kts)." if self.agent.airspeed_i >= v2_plus_10 else f"Airspeed below V2 + 10 kts ({v2_plus_10} kts)."
            igs.output_set_string("interaction_message", create_interaction_message(message, tars_input))
    
    def check_v2_send_signal(self):
        global V_TWO
        if self.agent.airspeed_i is not None:
            message = f"Airspeed: {self.agent.airspeed_i:.0f} kts"
            tars_input = f"Airspeed above V2 ({V_TWO} kts)." if self.agent.airspeed_i >= V_TWO else f"Airspeed below V2 ({V_TWO} kts)."
            igs.output_set_string("interaction_message", create_interaction_message(message, tars_input))
            if self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2")].autonomy_role == "performer" and self.agent.airspeed_i < V_TWO:
                self.on_speak_action(f"Aim for {V_TWO} knots")
    
    def check_gear_up_send_signal(self):
        if self.agent.control_gear_i is not None:
            if self.agent.control_gear_i == 1: # Gear Extended
                self.on_speak_action("Landing gear is extended")
                tars_input = f"Landing gear is extended."
                igs.output_set_string("interaction_message", create_interaction_message("", tars_input))
    
    def set_flaps_takeoff_send_signal(self):
        """Set flaps to takeoff position (15°). If performer, announce and actuate;
        if supporter, display reminder."""
        state = self.states[("BEFORE TAKEOFF", "FLAPS", "SET FOR TAKEOFF")]
        if state.autonomy_role == "performer":
            self.on_speak_action("Setting flaps for takeoff, fifteen degrees")
            
            #TARS RELIABLE / UNRELIABLE BLOCK
            #if self.TARS_RELIABLE:
                #igs.output_set_double("flaps", 0.5)  # 0.5 = flaps 15° (takeoff position)
            #elif not self.TARS_RELIABLE:
                #self.agent.control_flaps_i = 0.5  # Simulate TARS failure
            #TARS RELIABLE / UNRELIABLE BLOCK

            igs.output_set_double("flaps", 0.5)  # 0.5 = flaps 15° (takeoff position)

            time.sleep(1.0)
            self.on_speak_action("Flaps set")
            interaction_json = create_interaction_message(
                self.INTERACTION_FLAPS_TAKEOFF,
                "Flaps set to takeoff position: 15°"
            )
            igs.output_set_string("interaction_message", interaction_json)

    def check_flaps_retracted_send_signal(self):
        if self.agent.control_flaps_i is not None:
            message = self.INTERACTION_FLAPS_UP
            if self.agent.control_flaps_i is not None and self.agent.control_flaps_i == 0.0:
                tars_input = f"Flaps are retracted to UP position."
            elif self.agent.control_flaps_i is not None and self.agent.control_flaps_i == 0.5:
                tars_input = f"Flaps are set to takeoff position (15°)."
            elif self.agent.control_flaps_i is not None and self.agent.control_flaps_i == 1.0:
                tars_input = f"Flaps are set to landing position (30°)."
            igs.output_set_string("interaction_message", create_interaction_message(message, tars_input))

    def retract_flaps_send_signal(self):
        """Retract flaps to UP position (performer action). Announces and actuates."""
        self.on_speak_action("I will retract flaps")

        #TARS RELIABLE / UNRELIABLE BLOCK
        #if self.TARS_RELIABLE:
            #igs.output_set_double("flaps", 0.0)  # 0.0 = flaps UP
        #elif not self.TARS_RELIABLE:
            #self.agent.control_flaps_i = 0.0  # Simulate TARS failure
        #TARS RELIABLE / UNRELIABLE BLOCK
        time.sleep(1.0)

        igs.output_set_double("flaps", 0.0)  # 0.0 = flaps UP
        time.sleep(1.0)
        self.on_speak_action("Flaps retracted")
        interaction_json = create_interaction_message(
            self.INTERACTION_FLAPS_UP,
            "Flaps retracted"
        )
        igs.output_set_string("interaction_message", interaction_json)

    def is_electrical_load_under_limit(self):
        if self.engine_failed_side == "Left":
            if self.agent.l_gen_load_i is not None and int(self.agent.l_gen_load_i) <= 300:
                return True
        if self.engine_failed_side == "Right":
            if self.agent.r_gen_load_i is not None and int(self.agent.r_gen_load_i) <= 300:
                return True
        return False

    def is_thrust_toga(self):
        if self.agent.control_throttle_i is not None and self.agent.control_throttle_i == 1:
            self.RUNWAY_HEADING = self.agent.heading_i # Store runway heading at TOGA selection
            return True
        return False
    
    def is_pitot_heat_on(self):
        if self.agent.pitot_heat_i is not None and self.agent.pitot_heat_i:
            return True
        return False

    def is_engine_spool_even(self):
        if self.agent.e1_n1_percent_i is not None and self.agent.e2_n1_percent_i is not None:
            if self.agent.e1_n1_percent_i > 30 and self.agent.e2_n1_percent_i > 30:  # Both engines above idle
                diff = abs(self.agent.e1_n1_percent_i - self.agent.e2_n1_percent_i)
                if diff <= 5:  # Assuming a threshold of 5% for even spool
                    self.engine_spool_alert_sent = False
                    igs.output_set_impulsion("alert_clear")
                    return True
                else:
                    if not self.engine_spool_alert_sent:
                        igs.output_set_string("alert", create_alert_message("Engine N1 mismatch detected!", "red", "warning"))
                        self.engine_spool_alert_sent = True
            else:
                if not self.engine_spool_alert_sent:
                    igs.output_set_string("alert", create_alert_message("Engines thrust is low!", "red", "warning"))
                    self.engine_spool_alert_sent = True
        return False
    
    def check_pitch_send_signal(self):
        if self.agent.pitch_i is not None and self.agent.pitch_i <= self.PITCH_TEN_DEGREES:
            message = f"Pitch Angle: {self.agent.pitch_i:.1f}°"
            tars_input = f"Pitch angle below {self.PITCH_TEN_DEGREES}°."
            igs.output_set_string("interaction_message", create_interaction_message(message, tars_input))
            #self.on_speak_action(f"Pitch angle low")
    
    def check_positive_rate_send_signal(self):
        if self.agent.vertical_speed_i is not None and self.agent.vertical_speed_i > self.POSITIVE_RATE_THRESHOLD:
            message = f"Vertical Speed: {self.agent.vertical_speed_i:.1f} ft/min"
            tars_input = f"Positive climb rate established." if self.agent.vertical_speed_i > self.POSITIVE_RATE_THRESHOLD else f"Climb rate below positive threshold."
            igs.output_set_string("interaction_message", create_interaction_message(message, tars_input))
            if self.states[("TAKEOFF", "Positive climb rate", "CHECK")].autonomy_role == "performer":
                self.on_speak_action("Positive climb rate")
            
    
    def check_flaps_send_signals(self):
        if self.agent.control_flaps_i is not None:
            tars_input = self.get_interaction_flaps()
            igs.output_set_string("interaction_message", create_interaction_message("", tars_input))

    def check_pitot_heat_send_signals(self):
        if self.agent.pitot_heat_i is not None:
            if self.agent.pitot_heat_i:
                #if self.TARS_RELIABLE:
                    msg = create_interaction_message("CAUTION\n\nLIMIT GROUND OPERATION OF PITOT-STATIC HEAT TO TWO MINUTES TO PRECLUDE DAMAGE TO THE PITOT-STATIC AND STALL WARNING HEATERS.", "Pitot heat is ON.")
                    igs.output_set_string("interaction_message", msg)
                    if self.states[("BEFORE TAKEOFF", "Pitot-Static Switch", "PITOT-STATIC")].autonomy_role == "performer":
                        self.on_speak_action("Pitot heat is ON, check")
                #else:
                    #msg = create_interaction_message("CAUTION\n\nLIMIT GROUND OPERATION OF PITOT-STATIC HEAT TO TWO MINUTES TO PRECLUDE DAMAGE TO THE PITOT-STATIC AND STALL WARNING HEATERS.", "Pitot heat is OFF.")
                    #igs.output_set_string("interaction_message", msg)
            elif not self.agent.pitot_heat_i:
                #if self.TARS_RELIABLE:
                    msg = create_interaction_message("CAUTION\n\nLIMIT GROUND OPERATION OF PITOT-STATIC HEAT TO TWO MINUTES TO PRECLUDE DAMAGE TO THE PITOT-STATIC AND STALL WARNING HEATERS.", "Pitot heat is OFF.")
                    igs.output_set_string("interaction_message", msg)
                    if self.states[("BEFORE TAKEOFF", "Pitot-Static Switch", "PITOT-STATIC")].autonomy_role == "performer":
                        self.on_speak_action("Pitot heat is OFF")
                #else:
                    #msg = create_interaction_message("CAUTION\n\nLIMIT GROUND OPERATION OF PITOT-STATIC HEAT TO TWO MINUTES TO PRECLUDE DAMAGE TO THE PITOT-STATIC AND STALL WARNING HEATERS.", "Pitot heat is ON.")
                    #igs.output_set_string("interaction_message", msg)
        else:
            msg = create_interaction_message("CAUTION\n\nLIMIT GROUND OPERATION OF PITOT-STATIC HEAT TO TWO MINUTES TO PRECLUDE DAMAGE TO THE PITOT-STATIC AND STALL WARNING HEATERS.", "Pitot heat status unknown.")
            igs.output_set_string("interaction_message", msg)
    
    def check_airspeed_alive_send_signal(self):
                msg = create_interaction_message(f"Airspeed: {self.agent.airspeed_i:.1f} kts", "")
                igs.output_set_string("interaction_message", msg)
    
    def check_seventy_kts_send_signal(self):
                msg = create_interaction_message(f"Airspeed: {self.agent.airspeed_i:.1f} kts", "")
                igs.output_set_string("interaction_message", msg)
    
    def check_v_one_send_signal(self):
                msg = create_interaction_message(f"Airspeed: {self.agent.airspeed_i:.1f} kts", f"V1 = {V_ONE} kts.")
                igs.output_set_string("interaction_message", msg)
    
    def check_positive_climb_rate_send_signal(self):
        if self.agent.vertical_speed_i is not None:
            while self.agent.vertical_speed_i <= self.POSITIVE_RATE_THRESHOLD and self.task_acked[0] == False:
                time.sleep(0.1)  # Wait and recheck
            if self.task_acked[0] == False:
                msg = create_interaction_message(f"Vertical Speed: {self.agent.vertical_speed_i:.1f} ft/min", "Positive rate, gear up.")
                igs.output_set_string("interaction_message", msg)
                if self.states[("TAKEOFF", "Positive climb rate", "CHECK")].autonomy_role == "performer":
                    self.on_speak_action("Positive rate")

    def recap_takeoff_speeds(self):
        global V_ONE, V_TWO, V_ROTATE
        # Determine which speed callouts TARS will perform
        callout_parts = []
        if self.states[("TAKEOFF", "\"Airspeed's alive\"", "ANNOUNCE")].autonomy_role == "performer":
            callout_parts.append("Airspeed's alive")
        if self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")].autonomy_role == "performer":
            callout_parts.append("70 knots")
        if self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")].autonomy_role == "performer":
            callout_parts.append("V1")
        if self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")].autonomy_role == "performer":
            callout_parts.append("and Rotate")

        tars_info = f"TAKEOFF SPEEDS: V1: {V_ONE} kts VR: {V_ROTATE} kts. Single engine climb speed (V_ENR): {V_ENR} kts."

        msg = create_interaction_message("", tars_info)
        igs.output_set_string("interaction_message", msg)

        if callout_parts:
            announce_list = ", ".join(callout_parts)
            self.on_speak_action(f"TARS ready for takeoff. I will announce {announce_list}")
        else:
            self.on_speak_action(f"Takeoff speeds recap, V1 {V_ONE} knots. Rotation {V_ROTATE} knots. Single engine climb speed {V_ENR} knots.")
    
    def check_engine_spool_send_signal(self):
        if self.agent.e1_n1_percent_i is not None and self.agent.e2_n1_percent_i is not None:
            diff = abs(self.agent.e1_n1_percent_i - self.agent.e2_n1_percent_i)
            if self.agent.e1_n1_percent_i < 60 or self.agent.e2_n1_percent_i < 60:
                msg = create_interaction_message(f"Engine 1 N1: {self.agent.e1_n1_percent_i:.1f}%\nEngine 2 N1: {self.agent.e2_n1_percent_i:.1f}%", f"Engines thrust is low!")
                igs.output_set_string("interaction_message", msg)
                if self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")].autonomy_role == "performer":
                    self.on_speak_action("Engines thrust is low")
                if not self.engine_spool_alert_sent:
                    alert = create_alert_message("Engines thrust is low!", "red", "warning")
                    igs.output_set_string("alert", alert)
                self.engine_spool_alert_sent = True
            else:
                if diff > 5 and not self.engine_spool_alert_sent:
                    msg = create_interaction_message(f"Engine 1 N1: {self.agent.e1_n1_percent_i:.1f}%\nEngine 2 N1: {self.agent.e2_n1_percent_i:.1f}%\nN1 Difference: {diff:.1f}%", f"Engine N1 mismatch detected!")
                    igs.output_set_string("interaction_message", msg)
                    if self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")].autonomy_role == "performer":
                        self.on_speak_action("Engine spool mismatch")
                    alert = create_alert_message("Engine N1 mismatch detected!", "red", "critical")
                    igs.output_set_string("alert", alert)
                elif diff <= 5:
                    msg = create_interaction_message(f"Engine 1 N1: {self.agent.e1_n1_percent_i:.1f}%\nEngine 2 N1: {self.agent.e2_n1_percent_i:.1f}%\nN1 Difference: {diff:.1f}%", f"Engine N1 values are within normal limits.")
                    igs.output_set_string("interaction_message", msg)
                    if self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")].autonomy_role == "performer":
                        self.on_speak_action("Engine spool normal")
    
    def is_n1_percent_above_90(self):
        if self.agent.e1_n1_percent_i is not None and self.agent.e2_n1_percent_i is not None:
            if self.agent.e1_n1_percent_i >= 60 and self.agent.e2_n1_percent_i >= 60:
                return True
        return False
    
    def is_fadec_bug_to(self):
        if self.agent.n1_match_bug_i is not None and self.agent.n1_match_bug_i:
            return True
        return False

    def is_airspeed_alive(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i > AIRSPEED_ALIVE_THRESHOLD:
            return True
        return False

    def is_seventy_kts(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= SEVENTY_KTS:
            return True
        return False

    def is_v_one(self):
        global V_ONE
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= V_ONE:
            return True
        return False

    def is_v_rotate(self):
        global V_ROTATE
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= V_ROTATE:
            return True
        return False
    
    def is_pitch_above_threshold(self):
        if self.agent.pitch_i is not None and self.agent.pitch_i >= PITCH_ANGLE_THRESHOLD:
            return True
        return False

    def is_slip_skid_centered(self):
        """Check if slip/skid indicator is centered (within tolerance)"""
        if self.agent.slip_i is not None and abs(self.agent.slip_i) < SLIP_SKID_THRESHOLD:
            return True
        return False

    def is_positive_rate(self):
        if self.agent.vertical_speed_i is not None and self.agent.vertical_speed_i > POSITIVE_RATE_THRESHOLD:
            return True
        return False
    
    def is_safe_altitude_reached(self):
        if self.agent.altitude_i is not None and self.agent.altitude_i >= SAFE_ALTITUDE:
            return True
        return False
    
    def is_transition_altitude_reached(self):
        if self.agent.altitude_i is not None and self.agent.altitude_i >= TRANSITION_ALTITUDE:
            return True
        return False

    def is_gear_up(self):
        if self.agent.control_gear_i is not None and self.agent.control_gear_i == 0:
            return True
        return False
    
    def is_master_warning_on(self):
        if self.agent.master_warning_i is not None and self.agent.master_warning_i == 1:
            return True
        return False
    
    def is_master_caution_on(self):
        if self.agent.master_caution_i is not None and self.agent.master_caution_i == 1:
            return True
        return False

    def is_alarm(self):
        if self.agent.master_warning_i == 1 or self.agent.engine_fire_l_i == True or self.agent.engine_fire_r_i == True:
            return True
        return False
    
    def is_engine_failed(self):
        if self.agent.e1_n1_percent_i is not None and self.agent.e1_n1_percent_i < 50 and (self.agent.e2_n1_percent_i is not None and self.agent.e2_n1_percent_i > 50):
            self.engine_failed_side = "Left"
            return True
        if self.agent.e2_n1_percent_i is not None and self.agent.e2_n1_percent_i < 50 and (self.agent.e1_n1_percent_i is not None and self.agent.e1_n1_percent_i > 50):
            self.engine_failed_side = "Right"
            return True
        return False
    
    def is_flight_director_on(self):
        if self.agent.flight_director_i is not None and (self.agent.flight_director_i == 1 or self.agent.flight_director_i == 2):
            return True
        return False
    
    def is_speed_mode_on(self):
        if self.agent.speed_mode_i is not None and self.agent.speed_mode_i == 2:
            return True
        return False
    
    def is_heading_mode_on(self):
        if self.agent.heading_mode_i is not None and self.agent.heading_mode_i == 2:
            return True
        return False

    def is_engine_not_failed(self):
        if self.agent.e1_n1_percent_i is not None and self.agent.e1_n1_percent_i >= 50:
            if self.agent.e2_n1_percent_i is not None and self.agent.e2_n1_percent_i >= 50:
                return True
        return False
    
    def is_above_800_ft(self):
        if self.agent.altitude_i is not None and self.agent.altitude_i >= 800:
            return True
        return False
    
    def is_airspeed_above_v_two(self):
        global V_TWO
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= V_TWO:
            return True
        return False
    
    def is_above_ap_altitude(self):
        if self.agent.altitude_i is not None and self.agent.altitude_i >= AUTOPILOT_ALTITUDE_THRESHOLD:
            return True
        return False

    def is_engine_fire_pushed(self):
        if self.engine_failed_side == "Left":
            if self.agent.engine_fire_l_button_i == True:
                return True
            elif self.agent.engine_fire_r_button_i == True:
                msg = create_interaction_message("", "ALERT: Right engine fire switch pushed instead of Left!")
                igs.output_set_string("interaction_message", msg)
        elif self.engine_failed_side == "Right":
            if self.agent.engine_fire_r_button_i == True:
                return True
            elif self.agent.engine_fire_l_button_i == True:
                msg = create_interaction_message("", "ALERT: Left engine fire switch pushed instead of Right!")
                igs.output_set_string("interaction_message", msg)
        elif self.agent.engine_fire_l_button_i == True or self.agent.engine_fire_r_button_i == True:
            return True
        return False

    def is_above_1500_ft(self):
        if self.agent.altitude_i is not None and self.agent.altitude_i >= ONE_THOUSAND_FIVE_HUNDRED_FEET:
            return True
        return False
    
    def is_above_v2_plus_10(self):
        global V_TWO
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= V_TWO + 10:
            return True
        return False

    def is_above_v_enr(self):
        global V_ENR
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= V_ENR:
            return True
        return False
    
    def is_flaps_retracted(self):
        if self.agent.control_flaps_i is not None and self.agent.control_flaps_i == 0:
            return True
        return False
    
    def is_flaps_takeoff_pos(self):
        """Return True when flaps are at takeoff position (0.5 = 15°)."""
        if self.agent.control_flaps_i is not None and self.agent.control_flaps_i >= 0.5:
            return True
        return False
    
    def is_bottle_pushed(self):
        if self.engine_failed_side == "Left":
            if self.agent.l_bottle_arm_i == 1:
                return True
            elif self.agent.r_bottle_arm_i == 1:
                msg = create_interaction_message("", "ALERT: Right fire bottle activated instead of Left!")
                igs.output_set_string("interaction_message", msg)
        elif self.engine_failed_side == "Right":
            if self.agent.r_bottle_arm_i == 1:
                return True
            elif self.agent.l_bottle_arm_i == 1:
                msg = create_interaction_message("", "ALERT: Left fire bottle activated instead of Right!")
                igs.output_set_string("interaction_message", msg)
        elif self.agent.l_bottle_arm_i == 1 or self.agent.r_bottle_arm_i == 1:
            return True
        return False
    
    def is_throttle_cutoff(self):
        if self.engine_failed_side == "Left":
            if self.agent.l_throttle_i == -1:
                return True
            elif self.agent.r_throttle_i == -1:
                msg = create_interaction_message("", "ALERT: Right throttle lever moved to cutoff instead of Left!")
                igs.output_set_string("interaction_message", msg)
        elif self.engine_failed_side == "Right":
            if self.agent.r_throttle_i == -1:
                return True
            elif self.agent.l_throttle_i == -1:
                msg = create_interaction_message("", "ALERT: Left throttle lever moved to cutoff instead of Right!")
                igs.output_set_string("interaction_message", msg)
        elif self.agent.r_throttle_i == -1 or self.agent.l_throttle_i == -1:
            msg = create_interaction_message("", "ALERT: Engine failed side not determined!")
            igs.output_set_string("interaction_message", msg)
            return True
        return False
    
    def is_fuel_boost_off(self):
        if self.engine_failed_side == "Left":
            if self.agent.fuel_boost_l_i == 1:
                return True
            elif self.agent.fuel_boost_r_i == 1:
                msg = create_interaction_message("", "ALERT: Right fuel boost pump activated instead of Left!")
                igs.output_set_string("interaction_message", msg)
        elif self.engine_failed_side == "Right":
            if self.agent.fuel_boost_r_i == 1:
                return True
            elif self.agent.fuel_boost_l_i == 1:
                msg = create_interaction_message("", "ALERT: Left fuel boost pump activated instead of Right!")
                igs.output_set_string("interaction_message", msg)
        elif self.agent.fuel_boost_l_i == 1 or self.agent.fuel_boost_r_i == 1:
            msg = create_interaction_message("", "ALERT: Engine failed side not determined!")
            igs.output_set_string("interaction_message", msg)
            return True
        return False

    def is_fuel_boost_norm(self):
        if self.engine_failed_side == "Left":
            if self.agent.fuel_boost_l_i == 0:
                return True
            elif self.agent.fuel_boost_r_i == 0:
                msg = create_interaction_message("", "ALERT: Right fuel boost pump deactivated instead of Left!")
                igs.output_set_string("interaction_message", msg)
        elif self.engine_failed_side == "Right":
            if self.agent.fuel_boost_r_i == 0:
                return True
            elif self.agent.fuel_boost_l_i == 0:
                msg = create_interaction_message("", "ALERT: Left fuel boost pump deactivated instead of Right!")
                igs.output_set_string("interaction_message", msg)
        elif self.agent.fuel_boost_l_i == 0 and self.agent.fuel_boost_r_i == 0:
            return True
        return False
    
    def is_test_knob_turned(self):
        if self.agent.test_knob_i is not None and self.agent.test_knob_i == 1:
            return True
        return False
    
    def is_throttle_clb(self):
        l = self.agent.l_throttle_i
        r = self.agent.r_throttle_i
        if (l is not None and 0.75 < l < 0.9) or (r is not None and 0.75 < r < 0.9):
            return True
        return False
    
    
    def is_throttle_idle(self):
        if self.engine_failed_side == "Left":
            if self.agent.l_throttle_i is not None and self.agent.l_throttle_i == 0:
                return True
            elif self.agent.r_throttle_i is not None and self.agent.r_throttle_i == 0:
                msg = create_interaction_message("", "ALERT: Right throttle lever moved to idle instead of Left!")
                igs.output_set_string("interaction_message", msg)
        elif self.engine_failed_side == "Right":
            if self.agent.r_throttle_i is not None and self.agent.r_throttle_i == 0:
                return True
            elif self.agent.l_throttle_i is not None and self.agent.l_throttle_i == 0:
                msg = create_interaction_message("", "ALERT: Left throttle lever moved to idle instead of Right!")
                igs.output_set_string("interaction_message", msg)
        elif self.agent.l_throttle_i is not None and self.agent.l_throttle_i == 0 or self.agent.r_throttle_i == 0:
            return True
        return False
    
    def is_gen_switch_off(self):
        if self.engine_failed_side == "Left":
            if self.agent.l_gen_switch_i == 1:
                return True
            elif self.agent.r_gen_switch_i == 1:
                msg = create_interaction_message("", "ALERT: Right generator switch turned off instead of Left!")
                igs.output_set_string("interaction_message", msg)
        elif self.engine_failed_side == "Right":
            if self.agent.r_gen_switch_i == 1:
                return True
            elif self.agent.l_gen_switch_i == 1:
                msg = create_interaction_message("", "ALERT: Left generator switch turned off instead of Right!")
                igs.output_set_string("interaction_message", msg)
        elif self.agent.l_gen_switch_i == 1 or self.agent.r_gen_switch_i == 1:
            return True
        return False
    
    def is_ignition_switch_norm(self):
        if self.agent.l_ign_switch_i == 0.0 and self.agent.r_ign_switch_i == 0.0:
            return True
        return False
    
    def is_rudder_control_release(self):
        """Check if rudder control is released (within tolerance)"""
        #print(f"Rudder Control Input: {self.agent.control_rudder_i}")
        if self.agent.control_rudder_i is not None and abs(self.agent.control_rudder_i) < 0.15:
            return True
        return False
    
    def is_brake_released(self):
        """Check if parking brake is released"""
        if self.agent.park_brakes_i is not None and self.agent.park_brakes_i == 0:
            return True
        return False
    
    def check_affected_conditions(self, input_name, new_value, affected_condition_names):
        """
        Event-driven condition monitoring - called when an input changes
        
        Args:
            input_name: Name of the input that changed (e.g., 'control_gear')
            new_value: New value of the input
            affected_condition_names: List of condition function names that depend on this input
        """
        # Condition monitoring is now handled by FSMWorker
        # This method is kept for backward compatibility but does nothing
        # The FSMWorker independently monitors conditions
        pass

    def on_start(self):
        print("Action: Starting FSM...")
        time.sleep(3)  # Simulate some startup delay

    # Ingescape callbacks
    def signal_handler(self, signal_received, frame):
        # Use platform-safe signal description
        try:
            if hasattr(signal, 'strsignal'):
                sig_desc = signal.strsignal(signal_received)
            else:
                sig_desc = f"Signal {signal_received}"
        except (AttributeError, ValueError):
            sig_desc = f"Signal {signal_received}"
        print("\n", sig_desc, sep="")
        self.is_interrupted = True

    def _play_sound_async(self, sound_filename):
        """Play a sound effect asynchronously (non-blocking)"""
        def _play():
            try:
                project_root = Path(__file__).parent.parent
                sound_path = os.path.join(project_root, "sounds", sound_filename)
                if os.path.exists(sound_path):
                    data, samplerate = sf.read(sound_path)
                    sd.play(data, samplerate)
            except Exception:
                pass  # Silently ignore audio errors
        
        threading.Thread(target=_play, daemon=True).start()
    
    def on_agent_event_callback(self, event, uuid, name, event_data, my_data):
        agent_object = my_data
        assert isinstance(agent_object, Echo)
        # Add event handling logic here if needed

    def on_freeze_callback(self, is_frozen, my_data):
        agent_object = my_data
        assert isinstance(agent_object, Echo)
        # Add freeze handling logic here if needed

    # Input callbacks
    def impulsion_input_callback(self, io_type, name, value_type, value, my_data):
        agent_object = my_data
        assert isinstance(agent_object, Echo)
        
        # Reset impulsion - reset FSM and agent state
        if name == "Reset":
            print("🔄 RESET impulsion received - resetting agent to IDLE state")
            self.reset_agent()
            return
        
        # GUI Agent → TARS Agent inputs (Phase 6)
        if name == "task_acknowledged":
            if self.popup_active:
                print("🚫 task_acknowledged blocked — popup is active")
                return
            print("✅ Task acknowledged from GUI")
            self.task_acked[0] = True
            #self._play_sound_async("doubletick_sfx.mp3")
            
        elif name == "task_cancelled":
            print("❌ Task cancelled by user - reclaiming authority")
            # Task cancellation is handled by the FSM execution loop
            # No action needed here - the cancellation signal itself is sufficient
            
        elif name == "start_procedure":
            print("▶️  Start procedure requested from GUI")
            self.is_on_off[0] = True
            
        elif name == "stop_procedure":
            print("🛑  Emergency stop requested from GUI")
            self.is_on_off[0] = False

            # Unblock any waiting events so threads can exit cleanly
            if self.countdown_completion_event:
                self.countdown_completion_event.set()
            if self.tts_completion_event:
                self.tts_completion_event.set()

            # Stop trim thread
            if self.trim_thread and self.trim_thread.is_alive():
                self.trim_stop_event.set()
                print("  ✓ Trim stop event sent")

            # Stop ATC thread
            if self.atc_thread and self.atc_thread.is_alive():
                self.atc_stop_event.set()
                print("  ✓ ATC stop event sent")

            # Stop FSM worker loop and skip any in-progress action
            if hasattr(self, 'fsm_worker') and self.fsm_worker is not None:
                self.fsm_worker.should_stop = True
                self.fsm_worker.skip_current_action = True
                print("  ✓ FSM worker stop requested")

            # Reset agent state to IDLE
            self.reset_agent()
            print("  ✓ Emergency stop complete - agent reset to IDLE")
            
        elif name == "countdown_complete":
            print("⏱️  Countdown complete signal received from GUI")
            if self.countdown_completion_event:
                self.countdown_completion_event.set()
        
        # Dev mode inputs
        elif name == "next_step":
            print("🔧 DEV MODE: Next step impulsion received")
            # Force FSM to next state
            if self.fsm:
                success = self.fsm.force_next_state()
                if success:
                    # Publish state change via Ingescape (GUIAgent will receive it)
                    try:
                        state_data = encode_state_to_json(self.fsm.current_state)
                        igs.output_set_string("current_state", state_data)
                        print(f"  → State change published via Ingescape")
                    except Exception as e:
                        print(f"ERROR publishing state change: {e}")
                else:
                    print("⚠️  No next state available (end of FSM or no transitions from current state)")
            else:
                print("⚠️  FSM not initialized")
        
        elif name == "previous_step":
            print("🔙 DEV MODE: Previous step impulsion received")
            # Go back to previous state
            if self.fsm:
                success = self.fsm.force_previous_state()
                if success:
                    # Publish state change via Ingescape (GUIAgent will receive it)
                    try:
                        state_data = encode_state_to_json(self.fsm.current_state)
                        igs.output_set_string("current_state", state_data)
                        print(f"  → State change published via Ingescape")
                    except Exception as e:
                        print(f"ERROR publishing state change: {e}")
                else:
                    print("⚠️  No previous state available (at beginning)")
            else:
                print("⚠️  FSM not initialized")

    def bool_input_callback(self, io_type, name, value_type, value, my_data):
        agent_object = my_data
        assert isinstance(agent_object, Echo)
        
        # GUI Agent → TARS Agent inputs (Phase 6)
        if name == "task_approval":
            approval_status = ApprovalStatus.APPROVED if value else ApprovalStatus.DENIED
            self.task_approval_status[0] = approval_status
            print(f"{'✅ Task APPROVED' if value else '❌ Task DENIED'} by user")
            if value:  # Only play sound on approval (True)
                self._play_sound_async("accept_sfx.mp3")
        elif name == "tars_reliable":
            self.TARS_RELIABLE = value
            self._wind_dir = 190 if value else 290
            print(f"📡 TARS_RELIABLE set to {value} ({'reliable' if value else 'unreliable'})")
        elif name == "popup_active":
            self.popup_active = value
            print(f"{'🔒' if value else '🔓'} popup_active = {value}")

        # Simulator inputs
        elif name == "On_Off":
            self.is_on_off[0] = value
        elif name == "l_bottle_arm":
            agent_object.l_bottle_arm_i = value
        elif name == "r_bottle_arm":
            agent_object.r_bottle_arm_i = value
        elif name == "pitot_heat":
            agent_object.pitot_heat_i = value
        elif name == "engine_fire_l":
            agent_object.engine_fire_l_i = value
            if value == True:
                self.engine_failed_side = "Left"
        elif name == "engine_fire_r":
            agent_object.engine_fire_r_i = value
            if value == True:
                self.engine_failed_side = "Right"
        elif name == "anti_coll_lights":
            agent_object.anti_coll_lights_i = value
        elif name == "n1_match_bug":
            agent_object.n1_match_bug_i = value

    def integer_input_callback(self, io_type, name, value_type, value, my_data):
        agent_object = my_data
        assert isinstance(agent_object, Echo)
        if name == "alt_sel":
            agent_object.alt_sel_i = value * 100 # Convert from hundreds of feet to feet
        elif name == "heading_sel":
            agent_object.heading_sel_i = value
        elif name == "freq_1":
            agent_object.freq_1_i = value

    def double_input_callback(self, io_type, name, value_type, value, my_data):
        #start_time = time.perf_counter()
        #igs.info(f"Input {name} written to {value}")
        agent_object = my_data
        assert isinstance(agent_object, Echo)
        if name == "airspeed":
            agent_object.airspeed_i = value
        elif name == "pitch":
            agent_object.pitch_i = value
        elif name == "roll":
            agent_object.roll_i = value
        elif name == "heading":
            agent_object.heading_i = value
        elif name == "control_rudder":
            agent_object.control_rudder_i = value
        elif name == "vertical_speed":
            agent_object.vertical_speed_i = value
        elif name == "altitude":
            agent_object.altitude_i = value
        elif name == "control_throttle":
            agent_object.control_throttle_i = value
        elif name == "control_flaps":
            agent_object.control_flaps_i = value
        elif name == "control_gear":
            agent_object.control_gear_i = value
        elif name == "speed_brakes":
            agent_object.speed_brakes_i = value
        elif name == "park_brake":
            agent_object.park_brakes_i = value
        elif name == "l_throttle":
            agent_object.l_throttle_i = value
        elif name == "r_throttle":
            agent_object.r_throttle_i = value
        elif name == "e1_n1_percent":
            agent_object.e1_n1_percent_i = value
        elif name == "e2_n1_percent":
            agent_object.e2_n1_percent_i = value
        elif name == "slip":
            agent_object.slip_i = value
        elif name == "test_knob":
            agent_object.test_knob_i = value
        elif name == "l_gen_switch":    
            agent_object.l_gen_switch_i = value
        elif name == "r_gen_switch":
            agent_object.r_gen_switch_i = value
        elif name == "l_ign_switch":
            agent_object.l_ign_switch_i = value
        elif name == "r_ign_switch":
            agent_object.r_ign_switch_i = value
        elif name == "fuel_boost_l":
            agent_object.fuel_boost_l_i = value
        elif name == "fuel_boost_r":
            agent_object.fuel_boost_r_i = value
        elif name == "master_warning":
            agent_object.master_warning_i = value
        elif name == "master_caution":
            agent_object.master_caution_i = value
        elif name == "yaw_damper":
            agent_object.yaw_damper_i = value
        elif name == "autopilot_heading_set":
            agent_object.autopilot_heading_set_i = value
        elif name == "pax_safety":
            agent_object.pax_safety_i = value
        elif name == "flight_director":
            agent_object.flight_director_i = value
        elif name == "speed_mode":
            agent_object.speed_mode_i = value
        elif name == "heading_mode":
            agent_object.heading_mode_i = value
        elif name == "fd_pitch_deg":
            agent_object.fd_pitch_deg_i = value
        elif name == "trim_rudder":
            agent_object.trim_rudder_i = value
        elif name == "cabin_altitude":
            agent_object.cabin_altitude_i = value
        elif name == "l_gen_load":
            agent_object.l_gen_load_i = value
        elif name == "r_gen_load":
            agent_object.r_gen_load_i = value
        elif name == "latitude":
            agent_object.latitude_i = value
        elif name == "longitude":
            agent_object.longitude_i = value
        elif name == "autopilot_airspeed":
            agent_object.autopilot_airspeed_i = value
        
        # EVENT-DRIVEN CONDITION MONITORING
        # Check if this input affects any monitored conditions
        if name in self.input_to_conditions:
            affected_condition_names = self.input_to_conditions[name]
            self.check_affected_conditions(name, value, affected_condition_names)

    def string_input_callback(self, io_type, name, value_type, value, my_data):
        agent_object = my_data
        assert isinstance(agent_object, Echo)
        
        # GUI Agent → TARS Agent string inputs (Phase 6)
        if name == "load_csv":
            # Reload all task allocation states from a new CSV file
            import os
            # Security: only allow bare filenames (no path separators) that exist in Core/
            if not value or os.sep in value or '/' in value or '..' in value:
                print(f"❌ load_csv rejected: unsafe filename '{value}'")
                return
            csv_dir = Path(__file__).parent
            csv_path = csv_dir / value
            if not csv_path.resolve().parent == csv_dir.resolve():
                print(f"❌ load_csv rejected: path traversal attempt '{value}'")
                return
            if not csv_path.exists():
                print(f"❌ load_csv: file not found: {csv_path}")
                return
            try:
                new_states = self.create_states_from_csv(csv_path)
                new_checklists = self.create_checklists_from_states(new_states)
                self.states = new_states
                self.checklists = new_checklists
                self.CURRENT_BRIEFING_EXPORT_LOADED = value
                # Remap all FSM transition state references to new state objects
                # (from_state/to_state were captured at init; must be updated so
                #  delay_before_action, delay_after_action, and role fields reflect the new CSV)
                for t in self.fsm.transitions:
                    from_key = (t.from_state.procedure, t.from_state.task_object, t.from_state.value)
                    to_key = (t.to_state.procedure, t.to_state.task_object, t.to_state.value)
                    if from_key in new_states:
                        t.from_state = new_states[from_key]
                    if to_key in new_states:
                        t.to_state = new_states[to_key]
                # Reset FSM to IDLE
                idle_key = ("IDLE", "Idle", "WAITING")
                if idle_key in self.states:
                    self.fsm.current_state = self.states[idle_key]
                import json as _json
                payload = _json.dumps({"csv": value, "states_count": len(self.states)})
                igs.output_set_string("allocation_reloaded", payload)
                print(f"✅ load_csv: loaded '{value}' ({len(self.states)} states), FSM transitions remapped, reset to IDLE")
            except Exception as e:
                print(f"❌ load_csv failed for '{value}': {e}")

        elif name == "emergency_inject":
            print(f"🚨 Emergency procedure inject requested: {value}")
            # TODO: Implement emergency procedure injection logic
            
        elif name == "update_allocation":
            # Briefing page sent a new role-allocation from the GUI
            if not value or not value.strip():
                return
            import json
            try:
                allocation_list = json.loads(value)
                updated = 0
                for entry in allocation_list:
                    key = (
                        entry.get('procedure', ''),
                        entry.get('task_object', ''),
                        entry.get('value', ''),
                    )
                    if key in self.states:
                        self.states[key].human_role = entry.get('human_role', '')
                        self.states[key].autonomy_role = entry.get('autonomy_role', '')
                        updated += 1
                print(f"✅ update_allocation applied: {updated}/{len(allocation_list)} states patched")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"❌ Invalid update_allocation payload: {e}")

        elif name == "force_state_jump":
            # User clicked on checklist or timeline - force jump to that state
            if not value or not value.strip():
                return
            import json
            try:
                state_info = json.loads(value)
                procedure = state_info.get("procedure")
                task_object = state_info.get("task_object")
                value_str = state_info.get("value")
                
                print(f"🎯 Force state jump: {procedure} - {task_object} - {value_str}")
                
                # Find the matching state in TarsAgent.states (self.states, not agent_object)
                target_state = None
                task_key = (procedure, task_object, value_str)
                if task_key in self.states:
                    target_state = self.states[task_key]
                
                if target_state:
                    print(f"✅ Jumping to state: {target_state.procedure} {target_state.task_object} {target_state.value}")
                    self.fsm.current_state = target_state
                    # Publish the new state
                    from Core.message_protocol import encode_state_to_json
                    igs.output_set_string("current_state", encode_state_to_json(target_state))
                else:
                    print(f"⚠️ State not found for: {task_key}")
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON in force_state_jump: {e}")
            
        elif name == "speech_input":
            agent_object.speech_input_i = value
            
            # Match speech input to ALL matching commands
            commands = match_all_commands(value)
            
            if commands:
                print(f"🎯 Matched {len(commands)} command(s) from speech: '{value}'")
                
                # Execute all matched commands
                for cmd in commands:
                    print(f"   ➜ Executing: {cmd.action}")
                    
                    if cmd.action == "next_step":
                        self.impulsion_input_callback(igs.INPUT_T, "next_step", igs.IMPULSION_T, True, agent_object)
                        
                    elif cmd.action == "previous_step":
                        self.impulsion_input_callback(igs.INPUT_T, "previous_step", igs.IMPULSION_T, True, agent_object)
                        
                    elif cmd.action == "approve":
                        # Set approval flag for pending task
                        self.task_approval_status[0] = ApprovalStatus.APPROVED
                        self.on_speak_action("Action approved.")
                        print("✅ Approval granted")
                        
                    elif cmd.action == "deny":
                        # Set denial flag for pending task
                        self.task_approval_status[0] = ApprovalStatus.DENIED
                        print("❌ Request denied")
                        self.on_speak_action("Action denied.")
                        
                    elif cmd.action == "acknowledge":
                        # Task acknowledgment
                        self.task_acked[0] = True
                        print("✅ Task acknowledged")
            else:
                self.on_speak_action(f"Can you please repeat that?")
                print(f"⚠️ No command matched for speech input: '{value}'")

    # Utility functions
    def return_io_value_type_as_str(self, value_type):
        if value_type == igs.INTEGER_T:
            return "Integer"
        elif value_type == igs.DOUBLE_T:
            return "Double"
        elif value_type == igs.BOOL_T:
            return "Bool"
        elif value_type == igs.STRING_T:
            return "String"
        elif value_type == igs.IMPULSION_T:
            return "Impulsion"
        elif value_type == igs.DATA_T:
            return "Data"
        else:
            return "Unknown"

    def return_event_type_as_str(self, event_type):
        if event_type == igs.PEER_ENTERED:
            return "PEER_ENTERED"
        elif event_type == igs.PEER_EXITED:
            return "PEER_EXITED"
        elif event_type == igs.AGENT_ENTERED:
            return "AGENT_ENTERED"
        elif event_type == igs.AGENT_UPDATED_DEFINITION:
            return "AGENT_UPDATED_DEFINITION"
        elif event_type == igs.AGENT_KNOWS_US:
            return "AGENT_KNOWS_US"
        elif event_type == igs.AGENT_EXITED:
            return "AGENT_EXITED"
        elif event_type == igs.AGENT_UPDATED_MAPPING:
            return "AGENT_UPDATED_MAPPING"
        elif event_type == igs.AGENT_WON_ELECTION:
            return "AGENT_WON_ELECTION"
        elif event_type == igs.AGENT_LOST_ELECTION:
            return "AGENT_LOST_ELECTION"
        else:
            return "UNKNOWN"

    # Start agent and FSM
    def start(self):
        import sys

        igs.agent_set_name(self.agent_name)
        igs.definition_set_version("1.0")
        igs.log_set_console(self.verbose)
        igs.log_set_file(True, None)
        igs.log_set_stream(self.verbose)
        igs.set_command_line(sys.executable + " " + " ".join(sys.argv))
        igs.observe_agent_events(self.on_agent_event_callback, self.agent)
        igs.observe_freeze(self.on_freeze_callback, self.agent)

        igs.output_create("pax_safety", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.output_create("flight_director", igs.DOUBLE_T, None)  # Not sure how to set FD up using a comm
        igs.output_create("speed_mode", igs.DOUBLE_T, None)  # Mustang/airspeedmach
        igs.output_create("heading_mode", igs.DOUBLE_T, None)  # Mustang/heading
        igs.output_create("autopilot_master", igs.DOUBLE_T, None)  # 0 is off, 1 is FD 2 is AP + FD
        igs.output_create("autopilot_heading_set", igs.DOUBLE_T, None)  # 0 to 360
        igs.output_create("autopilot_state", igs.DOUBLE_T, None)  # need to understand this seems to be an integer that represents the state of the autopilot
        igs.output_create("yaw_damper", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.output_create("flaps", igs.DOUBLE_T, None)  # 0.0 = retracted, 0.5 = 15° takeoff, 1.0 = full
        igs.output_create("altimeter_setting", igs.DOUBLE_T, None)  # inHg * 1000
        igs.output_create("trim_rudder", igs.DOUBLE_T, None)  # -1.0 to 1.0 but can go beyond that programmatically
        igs.output_create("request_takeoff_clearance", igs.IMPULSION_T, None)  # Impulsion to request takeoff clearance
        igs.output_create("declare_mayday", igs.IMPULSION_T, None)  # Impulsion to declare mayday
        igs.output_create("declare_pan", igs.IMPULSION_T, None)  # Impulsion to declare pan
        igs.output_create("request_vectors", igs.IMPULSION_T, None)  # Impulsion to request vectors
        
        # Message Protocol Outputs (TARS → GUI)
        igs.output_create("current_state", igs.STRING_T, None)  # JSON encoded current FSM state
        igs.output_create("current_procedure", igs.STRING_T, None)  # Current procedure name
        igs.output_create("current_task_object", igs.STRING_T, None)  # Current task object name
        igs.output_create("current_task_value", igs.STRING_T, None)  # Current task object value
        igs.output_create("current_task_autonomy_role", igs.STRING_T, None)  # Current task autonomy role
        igs.output_create("current_task_human_role", igs.STRING_T, None)  # Current task human role
        igs.output_create("next_state", igs.STRING_T, None)  # JSON encoded next FSM state
        igs.output_create("previous_state", igs.STRING_T, None)  # JSON encoded previous FSM state
        igs.output_create("countdown_current", igs.INTEGER_T, None)  # Current countdown value in seconds
        igs.output_create("countdown_next", igs.INTEGER_T, None)  # Next countdown value in seconds
        igs.output_create("countdown_max_current", igs.INTEGER_T, None)  # Max current countdown
        igs.output_create("countdown_max_next", igs.INTEGER_T, None)  # Max next countdown
        igs.output_create("alert", igs.STRING_T, None)  # JSON alert message with color and severity
        igs.output_create("alert_clear", igs.IMPULSION_T, None)  # Clear alert display
        igs.output_create("condition_violated", igs.STRING_T, None)  # JSON condition violation
        igs.output_create("condition_restored", igs.STRING_T, None)  # JSON condition restoration
        igs.output_create("action_about_to_fire", igs.STRING_T, None)  # JSON state before action fires
        igs.output_create("checklist_item_complete", igs.STRING_T, None)  # JSON checklist completion
        igs.output_create("emergency_procedure_inject", igs.STRING_T, None)  # Emergency procedure name
        igs.output_create("interaction_message", igs.STRING_T, None)  # JSON interaction panel message
        igs.output_create("alt_sel", igs.INTEGER_T, None)  # Altitude select in feet
        igs.output_create("end_signal", igs.IMPULSION_T, None)  # Impulsion to signal end of procedure
        igs.output_create("action_time", igs.STRING_T, None)  # Time taken to perform last action
        igs.output_create("tars_status", igs.STRING_T, None)  # Human-readable status line for the GUI label
        igs.output_create("nose_down", igs.IMPULSION_T, None)  # Impulsion to command nose down maneuver
        igs.output_create("nose_up", igs.IMPULSION_T, None)  # Impulsion to command nose up maneuver
        
        # TTS Agent communication
        igs.output_create("tts_request", igs.STRING_T, None)  # Text to send to TTS agent
        igs.output_create("allocation_reloaded", igs.STRING_T, None)  # JSON: {csv, states_count} after load_csv

        igs.input_create("Reset", igs.IMPULSION_T, None)
        igs.input_create("On_Off", igs.BOOL_T, None)
        igs.input_create("next_step", igs.IMPULSION_T, None)
        igs.input_create("previous_step", igs.IMPULSION_T, None)
        igs.input_create("airspeed", igs.DOUBLE_T, None)
        igs.input_create("pitch", igs.DOUBLE_T, None)
        igs.input_create("roll", igs.DOUBLE_T, None)
        igs.input_create("heading", igs.DOUBLE_T, None)
        igs.input_create("control_rudder", igs.DOUBLE_T, None)
        igs.input_create("vertical_speed", igs.DOUBLE_T, None)
        igs.input_create("altitude", igs.DOUBLE_T, None)
        igs.input_create("control_throttle", igs.DOUBLE_T, None)
        igs.input_create("control_flaps", igs.DOUBLE_T, None)
        igs.input_create("control_gear", igs.DOUBLE_T, None)
        igs.input_create("speed_brakes", igs.DOUBLE_T, None)
        igs.input_create("park_brake", igs.DOUBLE_T, None)
        igs.input_create("l_throttle", igs.DOUBLE_T, None)
        igs.input_create("r_throttle", igs.DOUBLE_T, None)
        igs.input_create("n1_match_bug", igs.BOOL_T, None)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.input_create("e1_n1_percent", igs.DOUBLE_T, None)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.input_create("e2_n1_percent", igs.DOUBLE_T, None)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.input_create("slip", igs.DOUBLE_T, None)  # positive is right, negative is left
        igs.input_create("engine_fire_l", igs.BOOL_T, None)  # [0, 0] first means E1, second means E2
        igs.input_create("engine_fire_r", igs.BOOL_T, None)  # [0, 0] first means E1, second means E2
        igs.input_create("pax_safety", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("master_warning", igs.DOUBLE_T, None)  # readonly 0 is off, 1 is on
        igs.input_create("master_caution", igs.DOUBLE_T, None)  # readonly 0 is off, 1 is on
        igs.input_create("flight_director", igs.DOUBLE_T, None)  # Not sure how to set FD up using a comm
        igs.input_create("fd_pitch_deg", igs.DOUBLE_T, None)  # Flight director pitch reference in degrees
        igs.input_create("speed_mode", igs.DOUBLE_T, None)  # Mustang/airspeedmach
        igs.input_create("heading_mode", igs.DOUBLE_T, None)  # Mustang/heading
        igs.input_create("fuel_boost_l", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("fuel_boost_r", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("test_knob", igs.DOUBLE_T, None)  # 0 to 11 for each test position
        igs.input_create("autopilot_heading_set", igs.DOUBLE_T, None)  # 0 to 360
        igs.input_create("yaw_damper", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("l_ign_switch", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("r_ign_switch", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("l_gen_switch", igs.DOUBLE_T, None)  # 0 is reset, 1 is off 2 is on
        igs.input_create("r_gen_switch", igs.DOUBLE_T, None)  # 0 is reset, 1 is off 2 is on
        igs.input_create("transfer_knob", igs.DOUBLE_T, None)  # 0 is left, 1 is off 2 is right
        igs.input_create("trim_rudder", igs.DOUBLE_T, None)  # -1.0 to 1.0 but can go beyond that programmatically
        igs.input_create("cabin_altitude", igs.DOUBLE_T, None)  # in feet
        igs.input_create("l_gen_load", igs.DOUBLE_T, None)  #
        igs.input_create("r_gen_load", igs.DOUBLE_T, None)  # 
        igs.input_create("l_bottle_arm", igs.BOOL_T, None)  # Left fire bottle armed
        igs.input_create("r_bottle_arm", igs.BOOL_T, None)  # Right fire bottle armed
        igs.input_create("speech_input", igs.STRING_T, None)  # For speech recognition input
        igs.input_create("pitot_heat", igs.BOOL_T, None)  # Pitot heat on/off
        igs.input_create("latitude", igs.DOUBLE_T, None)  # Latitude
        igs.input_create("longitude", igs.DOUBLE_T, None)  # Longitude
        igs.input_create("anti_coll_lights", igs.BOOL_T, None)  # Anti-collision lights on/off
        igs.input_create("alt_sel", igs.INTEGER_T, None)  # Altitude select in feet
        igs.input_create("heading_sel", igs.INTEGER_T, None)  # Heading select in degrees
        igs.input_create("autopilot_airspeed", igs.DOUBLE_T, None)  # Airspeed set for autopilot
        igs.input_create("freq_1", igs.INTEGER_T, None)  # COM1 active frequency (e.g. 11990 = 119.90 MHz)
        igs.output_create("set_freq_1", igs.INTEGER_T, None)  # Set COM1 active frequency

        # GUI Agent → TARS Agent inputs (Phase 6: from message_protocol.py)
        igs.input_create("task_approval", igs.BOOL_T, None)  # User approved/denied current task
        igs.input_create("task_acknowledged", igs.IMPULSION_T, None)  # User acknowledged task completion
        igs.input_create("task_cancelled", igs.IMPULSION_T, None)  # User cancelled action (reclaim authority)
        igs.input_create("start_procedure", igs.IMPULSION_T, None)  # Start FSM execution
        igs.input_create("stop_procedure", igs.IMPULSION_T, None)  # Stop/pause FSM execution
        igs.input_create("emergency_inject", igs.STRING_T, None)  # Emergency procedure name to inject
        igs.input_create("force_state_jump", igs.STRING_T, None)  # Force jump to specific state (from UI clicks)
        igs.input_create("countdown_complete", igs.IMPULSION_T, None)  # Countdown timer reached zero
        igs.input_create("update_allocation", igs.STRING_T, None)  # Briefing role-allocation update (JSON list)
        igs.input_create("load_csv", igs.STRING_T, None)  # Reload all states from a new CSV filename
        igs.input_create("tars_reliable", igs.BOOL_T, None)  # Toggle TARS reliability (True=real data, False=inverted/unreliable)
        igs.input_create("popup_active", igs.BOOL_T, None)  # GUI dialog is open; block joystick task_acknowledged
        
        igs.observe_input("On_Off", self.bool_input_callback, self.agent)
        igs.observe_input("next_step", self.impulsion_input_callback, self.agent)
        igs.observe_input("previous_step", self.impulsion_input_callback, self.agent)
        igs.observe_input("airspeed", self.double_input_callback, self.agent)
        igs.observe_input("autopilot_airspeed", self.double_input_callback, self.agent)
        igs.observe_input("pitch", self.double_input_callback, self.agent)
        igs.observe_input("roll", self.double_input_callback, self.agent)
        igs.observe_input("heading", self.double_input_callback, self.agent)
        igs.observe_input("control_rudder", self.double_input_callback, self.agent)
        igs.observe_input("vertical_speed", self.double_input_callback, self.agent)
        igs.observe_input("altitude", self.double_input_callback, self.agent)
        igs.observe_input("control_throttle", self.double_input_callback, self.agent)
        igs.observe_input("control_flaps", self.double_input_callback, self.agent)
        igs.observe_input("control_gear", self.double_input_callback, self.agent)
        igs.observe_input("speed_brakes", self.double_input_callback, self.agent)
        igs.observe_input("park_brake", self.double_input_callback, self.agent)
        igs.observe_input("l_throttle", self.double_input_callback, self.agent)
        igs.observe_input("r_throttle", self.double_input_callback, self.agent)
        igs.observe_input("n1_match_bug", self.bool_input_callback, self.agent)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.observe_input("e1_n1_percent", self.double_input_callback, self.agent)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.observe_input("e2_n1_percent", self.double_input_callback, self.agent)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.observe_input("slip", self.double_input_callback, self.agent)  # positive is right, negative is left
        igs.observe_input("engine_fire_l", self.bool_input_callback, self.agent)  
        igs.observe_input("engine_fire_r", self.bool_input_callback, self.agent)  
        igs.observe_input("pax_safety", self.double_input_callback, self.agent)  # 0 is off, 1 is on
        igs.observe_input("master_warning", self.double_input_callback, self.agent)  # readonly 0 is off, 1 is on
        igs.observe_input("master_caution", self.double_input_callback, self.agent)  # readonly 0 is off, 1 is on
        igs.observe_input("flight_director", self.double_input_callback, self.agent)  # Not sure how to set FD up using a comm
        igs.observe_input("speed_mode", self.double_input_callback, self.agent)  # Mustang/airspeedmach
        igs.observe_input("heading_mode", self.double_input_callback, self.agent)  # Mustang/heading
        igs.observe_input("l_ign_switch", self.double_input_callback, self.agent)  # 0 is off, 1 is on
        igs.observe_input("r_ign_switch", self.double_input_callback, self.agent)
        igs.observe_input("fuel_boost_l", self.double_input_callback, self.agent)  # 0 is off, 1 is on
        igs.observe_input("fuel_boost_r", self.double_input_callback, self.agent)  # 0 is off, 1 is on
        igs.observe_input("test_knob", self.double_input_callback, self.agent)  # 0 to 11 for each test position
        igs.observe_input("autopilot_heading_set", self.double_input_callback, self.agent)  # 0 to 360
        igs.observe_input("yaw_damper", self.double_input_callback, self.agent)  # 0 is off, 1 is on
        igs.observe_input("l_gen_switch", self.double_input_callback, self.agent)  # 0 is reset, 1 is off 2 is on
        igs.observe_input("r_gen_switch", self.double_input_callback, self.agent)  # 0 is reset, 1 is off 2 is on
        igs.observe_input("transfer_knob", self.double_input_callback, self.agent)  # 0 is left, 1 is off 2 is right
        igs.observe_input("trim_rudder", self.double_input_callback, self.agent)  # -1.0 to 1.0 but can go beyond that programmatically
        igs.observe_input("cabin_altitude", self.double_input_callback, self.agent)  # in feet
        igs.observe_input("l_gen_load", self.double_input_callback, self.agent)  # 
        igs.observe_input("r_gen_load", self.double_input_callback, self.agent)  #
        igs.observe_input("l_bottle_arm", self.bool_input_callback, self.agent)  # Left fire bottle armed
        igs.observe_input("r_bottle_arm", self.bool_input_callback, self.agent)
        igs.observe_input("speech_input", self.string_input_callback, self.agent)  # For speech recognition input
        igs.observe_input("pitot_heat", self.bool_input_callback, self.agent)  # Pitot heat on/off
        igs.observe_input("latitude", self.double_input_callback, self.agent)  # Latitude
        igs.observe_input("longitude", self.double_input_callback, self.agent)  # Longitude
        igs.observe_input("anti_coll_lights", self.bool_input_callback, self.agent)  # Anti-collision lights on/off
        igs.observe_input("alt_sel", self.integer_input_callback, self.agent)  # Altitude select in feet
        igs.observe_input("heading_sel", self.integer_input_callback, self.agent)  #

        # GUI Agent → TARS Agent observers (Phase 6)
        igs.observe_input("Reset", self.impulsion_input_callback, self.agent)
        igs.observe_input("task_approval", self.bool_input_callback, self.agent)
        igs.observe_input("task_acknowledged", self.impulsion_input_callback, self.agent)
        igs.observe_input("task_cancelled", self.impulsion_input_callback, self.agent)
        igs.observe_input("start_procedure", self.impulsion_input_callback, self.agent)
        igs.observe_input("stop_procedure", self.impulsion_input_callback, self.agent)
        igs.observe_input("emergency_inject", self.string_input_callback, self.agent)
        igs.observe_input("force_state_jump", self.string_input_callback, self.agent)
        igs.observe_input("countdown_complete", self.impulsion_input_callback, self.agent)
        igs.observe_input("update_allocation", self.string_input_callback, self.agent)
        igs.observe_input("load_csv", self.string_input_callback, self.agent)
        igs.observe_input("tars_reliable", self.bool_input_callback, self.agent)
        igs.observe_input("popup_active", self.bool_input_callback, self.agent)

        # Map Aircraft outputs → our inputs
        igs.mapping_add("airspeed", "Aircraft", "airspeed")
        igs.mapping_add("pitch", "Aircraft", "pitch")
        igs.mapping_add("roll", "Aircraft", "Roll")
        igs.mapping_add("heading", "Aircraft", "heading")
        igs.mapping_add("control_rudder", "Aircraft", "controlYaw")
        igs.mapping_add("vertical_speed", "Aircraft", "verticalSpeed")
        igs.mapping_add("latitude", "Aircraft", "latitude")
        igs.mapping_add("longitude", "Aircraft", "longitude")
        igs.mapping_add("altitude", "Aircraft", "altitude")
        igs.mapping_add("control_throttle", "Aircraft", "controlThrottle")
        igs.mapping_add("control_flaps", "Aircraft", "controlFlaps")
        igs.mapping_add("control_gear", "Aircraft", "controlGear")
        igs.mapping_add("speed_brakes", "Aircraft", "speedBrakes")
        igs.mapping_add("park_brake", "Aircraft", "park_brake")
        igs.mapping_add("l_throttle", "Aircraft", "l_throttle")
        igs.mapping_add("r_throttle", "Aircraft", "r_throttle")
        igs.mapping_add("n1_match_bug", "Aircraft", "n1_match_bug")
        igs.mapping_add("slip", "Aircraft", "slip")
        igs.mapping_add("pax_safety", "Aircraft", "pax_safety")
        igs.mapping_add("master_warning", "Aircraft", "master_warning")
        igs.mapping_add("master_caution", "Aircraft", "Master_caution")
        igs.mapping_add("flight_director", "Aircraft", "flight_director")
        igs.mapping_add("speed_mode", "Aircraft", "speed_mode")
        igs.mapping_add("heading_mode", "Aircraft", "heading_mode")
        igs.mapping_add("fuel_boost_l", "Aircraft", "fuel_boost_l")
        igs.mapping_add("fuel_boost_r", "Aircraft", "fuel_boost_r")
        igs.mapping_add("test_knob", "Aircraft", "test_knob")
        igs.mapping_add("autopilot_heading_set", "Aircraft", "autopilot_heading_set")
        igs.mapping_add("yaw_damper", "Aircraft", "yaw_damper")
        igs.mapping_add("l_ign_switch", "Aircraft", "l_ign_switch")
        igs.mapping_add("r_ign_switch", "Aircraft", "r_ign_switch")
        igs.mapping_add("l_gen_switch", "Aircraft", "l_gen_switch")
        igs.mapping_add("r_gen_switch", "Aircraft", "r_gen_switch")
        igs.mapping_add("transfer_knob", "Aircraft", "transfer_knob")
        igs.mapping_add("e1_n1_percent", "Aircraft", "e1_n1_percent")
        igs.mapping_add("e2_n1_percent", "Aircraft", "e2_n1_percent")
        igs.mapping_add("engine_fire_l", "Aircraft", "engine_fire_l")
        igs.mapping_add("engine_fire_r", "Aircraft", "engine_fire_r")
        igs.mapping_add("cabin_altitude", "Aircraft", "cabin_altitude")
        igs.mapping_add("l_gen_load", "Aircraft", "l_gen_load")
        igs.mapping_add("r_gen_load", "Aircraft", "r_gen_load")
        igs.mapping_add("pitot_heat", "Aircraft", "pitot_heat")
        igs.mapping_add("trim_rudder", "Aircraft", "trim_rudder")
        igs.mapping_add("l_bottle_arm", "Aircraft", "l_bottle_arm")
        igs.mapping_add("r_bottle_arm", "Aircraft", "r_bottle_arm")
        igs.mapping_add("anti_coll_lights", "Aircraft", "anti_coll_light")
        igs.mapping_add("alt_sel", "Aircraft", "alt_sel")
        igs.mapping_add("heading_sel", "Aircraft", "heading_sel")
        igs.mapping_add("autopilot_airspeed", "Aircraft", "autopilot_airspeed")
        # Map Shared Interface outputs → our inputs
        igs.mapping_add("previous_step", "Shared Interface", "previous_step")
        igs.mapping_add("next_step", "Shared Interface", "next_step")
        igs.mapping_add("task_approval", "Shared Interface", "task_approval")
        igs.mapping_add("task_acknowledged", "Shared Interface", "task_acknowledged")
        igs.mapping_add("task_cancelled", "Shared Interface", "task_cancelled")
        igs.mapping_add("start_procedure", "Shared Interface", "start_procedure")
        igs.mapping_add("stop_procedure", "Shared Interface", "stop_procedure")
        igs.mapping_add("emergency_inject", "Shared Interface", "emergency_inject")
        igs.mapping_add("countdown_complete", "Shared Interface", "countdown_complete")
        igs.mapping_add("force_state_jump", "Shared Interface", "force_state_jump")
        igs.mapping_add("update_allocation", "Shared Interface", "update_allocation")
        igs.mapping_add("load_csv", "Shared Interface", "load_csv")
        igs.mapping_add("popup_active", "Shared Interface", "popup_active")
        # Map Speech_to_Text_Agent.speech_output → our speech_input
        igs.mapping_add("speech_input", "Speech_to_Text_Agent", "speech_output")

        igs.log_set_console(True)
        igs.log_set_console_level(igs.LOG_INFO)
        
        # Try multiple network devices in fallback order
        start_with_device_fallback(igs, self.port)

    def set_tts_completion_event(self, event):
        """Set the threading.Event used to track TTS completion"""
        self.tts_completion_event = event
    
    def format_callout(self, text: str) -> str:
        """Format callout text by replacing {variable_name} with agent attribute values
        
        Examples:
            "FLC V two {V_TWO}" -> "FLC V two 97 knots"
            "Heading {heading_i}" -> "Heading 237"
            
        Args:
            text: Callout text with optional {variable_name} placeholders
            
        Returns:
            Formatted text with variables replaced by their values
        """
        # Find all {variable_name} patterns
        pattern = r'\{([^}]+)\}'
        matches = re.findall(pattern, text)
        
        for var_name in matches:
            var_name_stripped = var_name.strip()
            
            # Try to get the value from agent attributes
            value = None
            
            # First, try agent attributes directly
            if hasattr(self, var_name_stripped):
                value = getattr(self, var_name_stripped)
            # Try with _i suffix (common for inputs like heading_i)
            elif hasattr(self, f"{var_name_stripped}_i"):
                value = getattr(self, f"{var_name_stripped}_i")
            # Try uppercase (class constants like V_TWO, V_ONE)
            elif hasattr(self, var_name_stripped.upper()):
                value = getattr(self, var_name_stripped.upper())
            
            # Format the value if found
            if value is not None:
                # Format numbers nicely
                if isinstance(value, float):
                    if value.is_integer():
                        formatted_value = str(int(value))
                    else:
                        formatted_value = f"{value:.1f}"
                elif isinstance(value, int):
                    # Format heading/angles with leading zeros (e.g., 237)
                    if 'heading' in var_name_stripped.lower() or 'runway' in var_name_stripped.lower():
                        formatted_value = f"{value:03d}"
                    else:
                        formatted_value = str(value)
                else:
                    formatted_value = str(value)
                
                # Replace the placeholder
                text = text.replace(f"{{{var_name}}}", formatted_value)
            else:
                # Variable not found - leave placeholder
                print(f"⚠️  TTS variable not found: {var_name_stripped}")
                text = text.replace(f"{{{var_name}}}", f"[{var_name_stripped}]")
        
        return text

    def reset_agent(self):
        """Reset the agent and FSM to initial IDLE state"""
        print("🔄 Resetting TARS Agent to IDLE state...")
        
        # Reset FSM to IDLE state
        idle_key = ("IDLE", "Idle", "WAITING")
        if idle_key in self.states:
            self.fsm.current_state = self.states[idle_key]
            print(f"  ✓ FSM reset to: {self.fsm.current_state}")
            
            # Publish the reset state via Ingescape
            try:
                state_data = encode_state_to_json(self.fsm.current_state)
                igs.output_set_string("current_state", state_data)
                print(f"  ✓ Published IDLE state to GUI")
            except Exception as e:
                print(f"  ❌ Error publishing state: {e}")
        
        # Reset agent state variables
        self.task_acked[0] = False
        self.is_on_off[0] = False
        self.task_approval_status[0] = ApprovalStatus.NOT_ANSWERED
        self.follow_vectors_status[0] = ApprovalStatus.NOT_ANSWERED
        self.engine_failed_side = "None"
        self.engine_spool_alert_sent = False
        
        # Reset threading events
        if self.countdown_completion_event:
            self.countdown_completion_event.set()  # Clear any pending countdowns
        if self.tts_completion_event:
            self.tts_completion_event.set()  # Clear any pending TTS
        
        # Stop any running threads
        if self.trim_thread and self.trim_thread.is_alive():
            self.trim_stop_event.set()
            self.trim_thread.join(timeout=1.0)
            self.trim_stop_event.clear()
            print("  ✓ Stopped trim thread")
        
        if self.atc_thread and self.atc_thread.is_alive():
            self.atc_stop_event.set()
            self.atc_thread.join(timeout=1.0)
            self.atc_stop_event.clear()
            print("  ✓ Stopped ATC thread")
        
        # Clear interaction messages
        igs.output_set_string("interaction_message", create_interaction_message("", ""))
        igs.output_set_string("current_task_object", "")
        igs.output_set_string("current_task_value", "")
        igs.output_set_string("current_task_autonomy_role", "")
        igs.output_set_string("current_task_human_role", "")
        
        print("✅ Agent reset complete - ready for new procedure")

    def send_reset_signal(self):
        """Set the reset signal to trigger agent output reset"""
        igs.output_set_string("interaction_message", create_interaction_message("", ""))
        #igs.output_set_string("current_task_object", "")
        #igs.output_set_string("current_task_value", "")
        #igs.output_set_string("current_task_autonomy_role", "")
        #igs.output_set_string("current_task_human_role", "")
        igs.output_set_impulsion("end_signal")

    def on_speak_action(self, speak_message=None, sleep=True):
        print(f"Action: {self.fsm.current_state}")
        if speak_message:
            # Format the callout with variable interpolation
            formatted_text = self.format_callout(speak_message)
            # Send to TTS agent via Ingescape
            igs.output_set_string("tts_request", formatted_text)
            # Return True to indicate this was a speech action
            return True
        return False
    
    def arm_speed_mode_send_signal(self):
        if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")].autonomy_role == "supporter":
            self.on_speak_action("800 feet. Autopilot speed mode can be armed to 120 knots")
        elif self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")].autonomy_role == "performer":
            self.on_speak_action("800 feet. I am arming autopilot FLC mode to V2 120 knots")

            if self.speed_mode == 2:
                return  # Already armed
            if self.flight_director_mode == 2:
                print("Flight Director is already in AP+FD mode, cannot arm speed mode.")
                return
            if self.agent.alt_sel_i is not None and self.agent.alt_sel_i != self.CLEARED_ALTITUDE:
                igs.output_set_int("alt_sel", self.CLEARED_ALTITUDE)
            igs.output_set_double("speed_mode", 1.0)  # Arm speed mode
            if self.agent.autopilot_airspeed_i is not None:
                _deadline = time.monotonic() + 2.0
                while (abs(self.agent.autopilot_airspeed_i - self.V_ENR) > 2):  # Wait until airspeed is close to V_ENR
                    if time.monotonic() >= _deadline:
                        print("[TARS] ⚠️  nose_up/nose_down timeout (2s) in arm_speed_mode_send_signal")
                        break
                    if self.agent.autopilot_airspeed_i > self.V_ENR:
                        igs.output_set_impulsion("nose_down")  # Command nose down to increase speed
                        print(f"Current airspeed: {self.agent.autopilot_airspeed_i} - commanding nose down to increase speed")
                    elif self.agent.autopilot_airspeed_i < self.V_ENR:
                        igs.output_set_impulsion("nose_up")  # Command nose up to reduce speed
                        print(f"Current airspeed: {self.agent.autopilot_airspeed_i} - commanding nose up to reduce speed")
                    time.sleep(0.1)  # Check every 100ms
            self.on_speak_action("Speed mode armed.")
            msg = create_interaction_message("", "Speed mode armed.")
            igs.output_set_string("interaction_message", msg)
    
    def set_fd_to_mode(self):
        """Set Flight Director to takeoff/departure mode:
        - Activate FD
        - Set heading to 237° and arm HDG mode
        - Ensure PIT mode (deactivate SPD mode if armed)
        - Adjust pitch reference to 10° ± 0.1 via nose_up / nose_down
        """
        # 1. Activate Flight Director
        igs.output_set_double("flight_director", 1)

        # 2. Set heading bug to 237° if not already set
        if self.RUNWAY_HEADING is not None:
            if self.agent.autopilot_heading_set_i is None or abs(self.agent.autopilot_heading_set_i - self.RUNWAY_HEADING) > 1:
                igs.output_set_double("autopilot_heading_set", self.RUNWAY_HEADING)

        # 3. Arm heading (HDG) mode if not already on
        if not self.is_heading_mode_on():
            igs.output_set_double("heading_mode", 1.0)

        # 4. Ensure PIT mode — if SPD mode (==2) is armed, pulse it off
        if self.agent.speed_mode_i is not None and self.agent.speed_mode_i == 2:
            _deadline = time.monotonic() + 2.0
            while self.agent.speed_mode_i is not None and self.agent.speed_mode_i == 2:
                if time.monotonic() >= _deadline:
                    print("[TARS] ⚠️  speed_mode pulse timeout (2s) in set_fd_to_mode")
                    break
                igs.output_set_double("speed_mode", 1.0)  # Pulse to toggle speed mode off
                time.sleep(0.2)

        # 5. Adjust FD pitch reference to 10° ± 0.1 using nose_up / nose_down
        if self.agent.fd_pitch_deg_i is not None:
            _deadline = time.monotonic() + 2.0
            while abs(self.agent.fd_pitch_deg_i - 10.0) > 0.1:
                if time.monotonic() >= _deadline:
                    print("[TARS] ⚠️  nose_up/nose_down timeout (2s) in set_fd_to_mode")
                    break
                if self.agent.fd_pitch_deg_i < 9.9:
                    igs.output_set_impulsion("nose_up")   # Increase pitch
                elif self.agent.fd_pitch_deg_i > 10.1:
                    igs.output_set_impulsion("nose_down")  # Decrease pitch
                time.sleep(0.1)

        self.on_speak_action("Flight director set")
        msg = create_interaction_message("", "Flight Director set:\nHDG 237° — PIT mode — Pitch 10°")
        igs.output_set_string("interaction_message", msg)

    def arm_heading_mode_send_signal(self):
        if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")].autonomy_role == "supporter":
            self.on_speak_action(f"Autopilot heading mode can be armed to {self.RUNWAY_HEADING} degrees")
        elif self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")].autonomy_role == "performer":
            self.on_speak_action(f"I am arming autopilot heading mode to {self.RUNWAY_HEADING} degrees")
            if self.heading_mode == 2:
                if self.agent.autopilot_heading_set_i is not None and self.RUNWAY_HEADING is not None and abs(self.agent.autopilot_heading_set_i - self.RUNWAY_HEADING) > 1:
                    igs.output_set_double("autopilot_heading_set", self.RUNWAY_HEADING)
                return  # Already armed
            if self.flight_director_mode == 2:
                print("Flight Director is already in AP+FD mode, cannot arm heading mode.")
                return
            if self.agent.autopilot_heading_set_i is not None and self.RUNWAY_HEADING is not None and abs(self.agent.autopilot_heading_set_i - self.RUNWAY_HEADING) > 1:
                igs.output_set_double("autopilot_heading_set", self.RUNWAY_HEADING)
            igs.output_set_double("heading_mode", 1.0)  # Arm heading mode
            self.on_speak_action(f"Heading mode armed to {self.RUNWAY_HEADING} degrees.")
            msg = create_interaction_message("", f"Heading mode armed to {self.RUNWAY_HEADING} degrees.")
            igs.output_set_string("interaction_message", msg)
        
    def engage_autopilot_action(self):
        if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")].autonomy_role == "supporter":
            self.on_speak_action("Autopilot can be engaged.")
        elif self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")].autonomy_role == "performer":
            igs.output_set_string("interaction_message", create_interaction_message("Ready to engage autopilot on your approval.", left_button="DENY", right_button="APPROVE"))  # Clear previous messages
            # Check if denied
            while self.task_approval_status[0] == ApprovalStatus.NOT_ANSWERED:
                if self.flight_director_mode == 2:
                    print("Flight Director already in AP+FD mode during wait.")
                    igs.output_set_string("interaction_message", create_interaction_message("", "Flight Director already in AP+FD mode."))
                    self.task_approval_status[0] = ApprovalStatus.NOT_ANSWERED  # Reset
                    return 
                time.sleep(0.1)  # Wait for user response
            if self.task_approval_status[0] == ApprovalStatus.DENIED :
                self.task_approval_status[0] = ApprovalStatus.NOT_ANSWERED  # Reset
                return
            # Approved - proceed with autopilot engagement
            if self.flight_director_mode == 2:
                print("Flight Director already in AP+FD mode.")
                return
            else:
                self.on_speak_action("Engaging autopilot.")
                igs.output_set_double("autopilot_master", 1.0)  # Engage autopilot
                time.sleep(1)  # Wait a moment
                self.on_speak_action("Autopilot engaged.")
                msg = create_interaction_message("", "Autopilot engaged.")
                igs.output_set_string("interaction_message", msg)
                self.task_approval_status[0] = ApprovalStatus.NOT_ANSWERED  # Reset

    def trim_action(self):
        """Non-blocking trim action - starts background thread after approval"""
        allow_string = f"Ready to trim rudder for {self.engine_failed_side} engine failure. Please approve or deny."
        self.on_speak_action(allow_string)
        igs.output_set_string("interaction_message", create_interaction_message("", allow_string, left_button="DENY", right_button="APPROVE"))
        # Check if denied
        while self.task_approval_status[0] == ApprovalStatus.NOT_ANSWERED:
            time.sleep(0.1)  # Wait for user response
        if self.task_approval_status[0] == ApprovalStatus.DENIED :
            self.task_approval_status[0] = ApprovalStatus.NOT_ANSWERED  # Reset
            return
        
        # Approved - start trim in background thread
        print("✅ Trim action approved - starting background thread")
        self.stop_trim_action()  # Stop any existing trim thread
        self.trim_stop_event.clear()  # Clear stop flag
        
        # Start trim worker in background
        self.trim_thread = threading.Thread(target=self._trim_worker, daemon=True, name="TrimWorker")
        self.trim_thread.start()
        
        # Return immediately - FSM can continue!
        self.task_approval_status[0] = ApprovalStatus.NOT_ANSWERED  # Reset for next use
    
    def _trim_worker(self):
        """Background worker thread for continuous trim adjustment"""
        try:
            # Determine trim direction based on failed engine
            # Left engine failure: need right rudder (positive trim), slip target is negative
            # Right engine failure: need left rudder (negative trim), slip target is positive
            is_left_failure = self.engine_failed_side == "Left"
            trim_direction = 1 if is_left_failure else -1  # +1 for right, -1 for left
            slip_target = -1 if is_left_failure else 1  # Slip threshold to correct
            
            direction_name = "right" if is_left_failure else "left"
            self.on_speak_action(f"Trimming {direction_name} rudder for {self.engine_failed_side.lower()} engine failure.")
            igs.output_set_string("tars_status", f"Trimming {direction_name}")

            stable_start_time = None
            stable_announced = False
            
            # Single loop for both engine sides - runs until stop event
            while not self.trim_stop_event.is_set():
                current_trim = self.agent.trim_rudder_i if self.agent.trim_rudder_i is not None else 0.0
                current_slip = self.agent.slip_i if self.agent.slip_i is not None else 0.0
                
                # Check if conditions are met
                if self.is_slip_skid_centered() and self.is_rudder_control_release():
                    if stable_start_time is None:
                        stable_start_time = time.time()
                        print(f"Conditions met, waiting for 3 seconds of stability...")
                    elif time.time() - stable_start_time >= 3.0 and not stable_announced:
                        print(f"✅ Conditions stable for 3 seconds, trim complete - continuing to monitor")
                        #self.on_speak_action("Rudder trim complete")
                        igs.output_set_string("tars_status", f"Trim {direction_name} - stable")
                        stable_announced = True  # Announce only once
                    # Continue monitoring (don't break) - trim might need adjustment if conditions change
                else:
                    # Conditions lost - reset and resume trimming if needed
                    if stable_announced:
                        print(f"⚠️ Stability lost, resuming trim adjustments...")
                        stable_announced = False
                    stable_start_time = None
                    
                    # Trim logic: check if we need to apply trim or if we've overshot
                    if current_slip * trim_direction < -1 and abs(current_trim) < 5:  # Need to trim in primary direction
                        #print(f"Current rudder trim: {current_trim}, slip: {current_slip:.2f}, trimming {direction_name}...")
                        igs.output_set_double("trim_rudder", current_trim + (0.1 * trim_direction))
                    elif current_slip * trim_direction > 1 and abs(current_trim) < 5:  # Overshot, need to correct opposite direction
                        #print(f"Overshot! Current trim: {current_trim}, slip: {current_slip:.2f}, correcting...")
                        igs.output_set_double("trim_rudder", current_trim - (0.1 * trim_direction))
                time.sleep(0.5)
            
            igs.output_set_string("tars_status", "TARS Agent RUNNING")
            print("🛑 Trim worker thread exiting")
        except Exception as e:
            print(f"❌ Error in trim worker thread: {e}")
            import traceback
            traceback.print_exc()
    
    def stop_trim_action(self):
        """Stop the trim action thread if running
        
        This will be called when:
        - Manual rudder input detected (placeholder for future implementation)
        - Application shutdown
        - New trim action needs to start
        """
        if self.trim_thread and self.trim_thread.is_alive():
            print("🛑 Stopping trim action thread...")
            self.trim_stop_event.set()
            self.trim_thread.join(timeout=2.0)
            if self.trim_thread.is_alive():
                print("⚠️ Trim thread did not stop gracefully")
            else:
                print("✅ Trim thread stopped successfully")
    
    def send_vector_signals(self):
        igs.output_set_string("interaction_message", create_interaction_message("",self.get_vectors_prompt(), left_button="DENY", right_button="APPROVE"))
        self.on_speak_action("Do you want me to set the heading and altitude following ATC vectors?")
    
    def set_heading_action(self):
        if self.agent.autopilot_heading_set_i is not None and self.VECTOR_HEADING is not None and self.FALSE_VECTOR_HEADING is not None and self.agent.heading_i is not None:
            if self.TARS_RELIABLE:
                half_brg = self.agent.heading_i + ((self.VECTOR_HEADING - self.agent.heading_i) / 2)
                igs.output_set_double("autopilot_heading_set", half_brg)  # Set initial heading to halfway between current and vector for smoother transition
                time.sleep(1)  # Brief pause before setting final heading
                igs.output_set_double("autopilot_heading_set", self.VECTOR_HEADING)
                self.on_speak_action(f"Setting heading to {self.VECTOR_HEADING} degrees.")
                msg = create_interaction_message("", f"Heading set to {self.VECTOR_HEADING} degrees.")
                igs.output_set_string("interaction_message", msg)
            else:
                igs.output_set_double("autopilot_heading_set", self.FALSE_VECTOR_HEADING)
                self.on_speak_action(f"Setting heading to {self.FALSE_VECTOR_HEADING} degrees.")
                msg = create_interaction_message("", f"Heading set to {self.FALSE_VECTOR_HEADING} degrees.")
                igs.output_set_string("interaction_message", msg)
    
    def set_altitude_action(self):
        if self.follow_vectors_status[0] == ApprovalStatus.DENIED:
            self.follow_vectors_status[0] = ApprovalStatus.NOT_ANSWERED  # Reset
            return
        if self.agent.alt_sel_i is not None and self.VECTOR_ALTITUDE is not None:
            igs.output_set_int("alt_sel", self.VECTOR_ALTITUDE)
            self.on_speak_action(f"Setting altitude to {self.VECTOR_ALTITUDE} feet.")
            msg = create_interaction_message("", f"Altitude set to {self.VECTOR_ALTITUDE} feet.")
            igs.output_set_string("interaction_message", msg)
    
    def engage_yaw_damper_action(self):
        if self.is_alarm() or self.is_engine_failed():
            return  # Do not engage yaw damper during alarm
        if self.agent.yaw_damper_i == 1:
            print("Yaw Damper already engaged.")
            return
        else:
            self.on_speak_action("Engaging yaw damper.")
            igs.output_set_double("yaw_damper", 1.0)  # Engage yaw damper
            time.sleep(1)  # Wait a moment
            self.on_speak_action("Yaw damper engaged.")
            msg = create_interaction_message("", "Yaw damper engaged.")
            igs.output_set_string("interaction_message", msg)
    
    def request_takeoff_clearance_action(self):
        """Request takeoff clearance - uses parallel thread if ALLOW_PARALLEL_ATC and performer"""
        autonomy_role = self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")].autonomy_role
        
        if ALLOW_PARALLEL_ATC and autonomy_role == "performer":
            # Use parallel ATC thread for non-blocking communication
            self.contact_atc_action("takeoff_clearance")
        else:
            igs.output_set_impulsion("request_takeoff_clearance")
            time.sleep(6)  # Simulate waiting for ATC response
            # Original blocking implementation for supporter or when parallel ATC disabled
            self.on_display_clearance_action()
    
    def on_display_clearance_action(self):
        """Original blocking clearance display - used by supporter or when parallel ATC disabled"""
        igs.output_set_string("interaction_message", create_interaction_message("", "CLEARANCE RECEIVED:\nWIND: 190 4KTS\nRWY: 24R\nALTI: 29.92"))  
        if self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")].autonomy_role == "performer":
            time.sleep(5)
            self.on_speak_action(self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")].callout)

    def start_chrono_action(self):
        if self.states[("ENGINE FIRE", "Chrono", "START")].autonomy_role == "supporter":
            self.on_speak_action("Ready to start chrono")
    
    def create_interaction_atc(self, message):
        if message == "mayday":
            if self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")].autonomy_role == "performer":
                igs.output_set_string("interaction_message", create_interaction_message(self.get_interaction_prompt_mayday(), self.get_mayday_message(), left_button="DENY", right_button="APPROVE"))
            elif self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")].autonomy_role == "supporter":
                igs.output_set_string("interaction_message", create_interaction_message(self.get_interaction_prompt_mayday(), self.get_mayday_message()))
        elif message == "panpan":
            if self.states[("DECLARE PANPAN", "ATC", "ANNOUNCE PANPAN AND REQUEST VECTOR")].autonomy_role == "performer":
                igs.output_set_string("interaction_message", create_interaction_message(self.get_interaction_prompt_panpan(), self.get_panpan_message(), left_button="DENY", right_button="APPROVE"))
            elif self.states[("DECLARE PANPAN", "ATC", "ANNOUNCE PANPAN AND REQUEST VECTOR")].autonomy_role == "supporter":
                igs.output_set_string("interaction_message", create_interaction_message(self.get_interaction_prompt_panpan(), self.get_panpan_message()))


    def contact_atc_action(self, message=None):
        """Start ATC communication in background thread - non-blocking"""
        # Check if autonomy role is not none
        if self.fsm.current_state.autonomy_role is None:
            print("Autonomy role is None, skipping contact_atc_action.")
            return
        
        print(f"✈️  Starting ATC communication in background: {message}")
        
        # Stop any existing ATC thread
        self.stop_atc_action()
        self.atc_stop_event.clear()
        
        # Start ATC worker in background thread
        self.atc_thread = threading.Thread(
            target=self._atc_worker,
            args=(message,),
            daemon=True,
            name="ATCWorker"
        )
        self.atc_thread.start()
        
        # Return immediately - FSM continues while ATC communication happens in background
        print("✅ ATC thread started, FSM can continue")
    
    def _ensure_freq(self, required_freq: int) -> None:
        """Check COM1 freq and set it if it does not match required_freq.

        Args:
            required_freq: Target frequency as integer (e.g. 11990 for 119.90 MHz)
        """
        current = self.agent.freq_1_i
        if current != required_freq:
            print(f"📻 COM1 freq mismatch (current={current}, required={required_freq}) — switching")
            igs.output_set_int("set_freq_1", required_freq)
            time.sleep(0.5)  # Brief pause to allow the simulator to switch frequency

    def _atc_worker(self, message):
        """Background worker thread for ATC communication"""
        try:
            print(f"Contacting ATC with message: {message}")
            if message == "takeoff_clearance":
                self._ensure_freq(11990)  # Tower: 119.90 MHz
                self.on_speak_action("Montreal Tower, C-POLY lined-up at runway 24R, ready for departure.")
                time.sleep(8)
                igs.output_set_impulsion("request_takeoff_clearance")
                
                # Wait for ATC response (interruptible)
                if not self.atc_stop_event.wait(timeout=13):
                    # Display clearance message
                    #igs.output_set_string("interaction_message", create_interaction_message(
                    #    "C-POLY, Montréal Tower, wind one-niner-zero at four, runway zero-six left, cleared for takeoff. Maintain runway heading, climb to 5000ft, Proceed direct AGMEB then OMEKI. Departure on one-one-eight decimal niner. Good flight.", 
                    #    "CLEARANCE RECEIVED:\nWIND: 190 4KTS\nRWY: 06L\nCLIMB: 5000FT\nHEADING: RUNWAY HDG\nDEPARTURE: AGMEB THEN OMEKI\nCOM: 118.9"))
                    
                    # Speak readback callout
                    if self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")].autonomy_role == "performer":
                        self.on_speak_action(self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")].callout)
                else:
                    print("🛑 Takeoff clearance communication interrupted")
            
            elif message == "mayday":
                self._ensure_freq(11890)  # Departure: 118.90 MHz
                if self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")].autonomy_role == "performer":
                    self.on_speak_action(f"Mayday, Mayday, Mayday, Cessna Papa Oscar Lima Yankee, engine fire, {self.altitude_rounded} feet, continuing {self.heading} degrees heading, two souls on board.") 
                    igs.output_set_impulsion("declare_mayday")
                
                # Wait for ATC response (interruptible)
                if not self.atc_stop_event.wait(timeout=32):
                    # Timeout completed - send readback
                    #igs.output_set_string("interaction_message", create_interaction_message(self.INTERACTION_MAYDAY_READBACK, ""))
                    if self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "READBACK")].autonomy_role == "performer":
                        self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "READBACK")].callout)
                else:
                    print("🛑 ATC communication interrupted")
                    
            elif message == "panpan":
                self._ensure_freq(11890)  # Departure: 118.90 MHz
                if self.states[("DECLARE PANPAN", "ATC", "ANNOUNCE PANPAN AND REQUEST VECTOR")].autonomy_role == "performer":
                    self.on_speak_action(f"Pan-Pan, Pan-Pan, Pan-Pan, Montreal Tower, Cessna Papa Oscar Lima Yankee, single engine operation after engine failure, {self.altitude_rounded} feet, {self.position_compared_to_initial}, {self.heading} degrees.  requesting vectors for immediate return to runway {self.RUNWAY_NUMBER}")
                    igs.output_set_impulsion("request_vectors")
                # Wait for ATC response (interruptible)
                if not self.atc_stop_event.wait(timeout=38):
                    # Timeout completed - send readback
                    if self.states[("DECLARE PANPAN", "ATC", "READBACK")].autonomy_role == "performer" and self.TARS_RELIABLE:
                        self.on_speak_action(self.states[("DECLARE PANPAN", "ATC", "READBACK")].callout)
                    elif self.states[("DECLARE PANPAN", "ATC", "READBACK")].autonomy_role == "performer" and not self.TARS_RELIABLE:
                        self.on_speak_action("Turning right heading zero-three-zero, descending to three thousand, expect ILS runway two-four right, C-POLY.")
                else:
                    print("🛑 ATC communication interrupted")
            
            self.task_approval_status[0] = ApprovalStatus.NOT_ANSWERED  # Reset for next use
            print("✅ ATC communication completed")
            
        except Exception as e:
            print(f"❌ Error in ATC worker thread: {e}")
            traceback.print_exc()
    
    def stop_atc_action(self):
        """Stop the ATC action thread if running"""
        if self.atc_thread and self.atc_thread.is_alive():
            print("🛑 Stopping ATC action thread...")
            self.atc_stop_event.set()
            self.atc_thread.join(timeout=2.0)
            if self.atc_thread.is_alive():
                print("⚠️  ATC thread did not stop gracefully")
            else:
                print("✅ ATC thread stopped successfully")

    def check_slip_skid_action(self):
        if not self.is_slip_skid_centered():
            from Core.message_protocol import create_alert_message
            alert_json = create_alert_message("Slip/Skid indicator is not centered!", "red", "warning")
            igs.output_set_string("alert", alert_json)
        else:
            igs.output_set_impulsion("alert_clear")
    
    def crew_briefing_action(self, topic):
        """Perform a crew briefing action for the given WANRAM topic.
        
        Displays the briefing text on the interaction panel and speaks it via TTS.
        
        Args:
            topic: One of 'weather', 'aircraft', 'notams', 'routing', 'automation', 'miscellaneous'
        """
        topic_map = {
            "weather": ("CREW BRIEFING", "Weather", "BRIEF", self.INTERACTION_CREW_BRIEFING_WEATHER, self.INTERACTION_CREW_BRIEFING_WEATHER_TARS),
            "aircraft": ("CREW BRIEFING", "Aircraft", "BRIEF", self.INTERACTION_CREW_BRIEFING_AIRCRAFT, self.INTERACTION_CREW_BRIEFING_AIRCRAFT_TARS),
            "notams": ("CREW BRIEFING", "NOTAMs", "BRIEF", self.INTERACTION_CREW_BRIEFING_NOTAMS, self.INTERACTION_CREW_BRIEFING_NOTAMS_TARS),
            "routing": ("CREW BRIEFING", "Routing", "BRIEF", self.INTERACTION_CREW_BRIEFING_ROUTING, self.INTERACTION_CREW_BRIEFING_ROUTING_TARS),
            "automation": ("CREW BRIEFING", "Automation", "BRIEF", self.INTERACTION_CREW_BRIEFING_AUTOMATION, self.INTERACTION_CREW_BRIEFING_AUTOMATION_TARS),
            "miscellaneous": ("CREW BRIEFING", "Miscellaneous", "BRIEF", self.INTERACTION_CREW_BRIEFING_MISCELLANEOUS, self.INTERACTION_CREW_BRIEFING_MISCELLANEOUS_TARS),
        }
        if topic not in topic_map:
            print(f"⚠️  Unknown crew briefing topic: {topic}")
            return
        procedure, task_object, value, display_msg, tars_input = topic_map[topic]
        state_key = (procedure, task_object, value)
        state = self.states[state_key]
        # Display on interaction panel
        interaction_json = create_interaction_message(display_msg, tars_input)
        igs.output_set_string("interaction_message", interaction_json)
        # Speak the callout if performer
        if state.autonomy_role == "performer" and state.callout:
            self.on_speak_action(state.callout)

    def dummy_action(self):
        print(f"Dummy action executed for {self.fsm.current_state}.")
    
    def check_electrical_load_action(self):
        if not self.is_electrical_load_under_limit():
            from Core.message_protocol import create_alert_message
            alert_json = create_alert_message("Electrical load is above 300 amps", "red", "warning")
            igs.output_set_string("alert", alert_json)
        else:
            igs.output_set_impulsion("alert_clear")
    
    def throttle_idle_action(self):
        self.on_speak_action(self.states[("ENGINE FIRE", "Throttle (affected engine)", "IDLE")].callout)
        igs.output_set_string("interaction_message", create_interaction_message("", f"Throttle {self.engine_failed_side} engine to IDLE."))
        wrong_throttle_flag = False
        while(not self.is_throttle_idle() and not self.is_acked() and not wrong_throttle_flag):
            if self.engine_failed_side == "Left":
                if self.agent.r_throttle_i is not None and self.agent.r_throttle_i < 1:
                    self.on_speak_action("Wrong throttle adjusted.")
                    wrong_throttle_flag = True
            elif self.engine_failed_side == "Right":
                if self.agent.l_throttle_i is not None and self.agent.l_throttle_i < 1:
                    self.on_speak_action("Wrong throttle adjusted.")
                    wrong_throttle_flag = True
            time.sleep(1)  # Wait until throttle is set to idle
    
    def check_winds_send_signal(self):
        wind_extra = {
            "runway_heading": int(self.RUNWAY_HEADING or 0),
            "initial_wind_dir": self._wind_dir,
            "initial_wind_mag": self._wind_mag,
        }
        role = self.states[("LINE-UP AND HOLD", "Winds", "CHECK")].autonomy_role
        metar_header = self.INTERACTION_WINDS_HEADER if self.TARS_RELIABLE else self.INTERACTION_FALSE_WINDS_HEADER
        wind_data   = self.INTERACTION_WINDS_DATA    if self.TARS_RELIABLE else self.INTERACTION_FALSE_WINDS_DATA

        if role == "performer":
            msg = create_interaction_message(
                metar_header, wind_data,
                left_button="LISTEN TO ATIS", middle_button="EDIT", right_button="CONFIRM",
                extra_data=wind_extra
            )
            igs.output_set_string("interaction_message", msg)
            callout = self.states[("LINE-UP AND HOLD", "Winds", "CHECK")].callout if self.TARS_RELIABLE else self.FALSE_WIND_CALLOUT
            self.on_speak_action(callout)
        else:  # supporter
            supporter_data = "Max crosswind for this aircraft type: 25 knots"
            msg = create_interaction_message(
                metar_header, supporter_data,
                left_button="LISTEN TO ATIS",
                middle_button="ENTER WIND",
                right_button="CHECK",
                extra_data=wind_extra
            )
            igs.output_set_string("interaction_message", msg)
    
    def check_fire_warn_test_send_signals(self):
        if self.agent.test_knob_i is not None and self.agent.test_knob_i == 1:
            interaction_json = create_interaction_message("", "Fire warning test is ON")
            igs.output_set_string("interaction_message", interaction_json)
        elif self.agent.test_knob_i is not None and self.agent.test_knob_i == 0:
            interaction_json = create_interaction_message("", "Fire warning test is OFF")
            igs.output_set_string("interaction_message", interaction_json)
        else:
            interaction_json = create_interaction_message("", "Fire warning test state is UNKNOWN")
            igs.output_set_string("interaction_message", interaction_json)

    def check_bottle_pushed_send_signals(self):
        if self.engine_failed_side == "Left":
            if self.agent.l_bottle_arm_i is not None and self.agent.l_bottle_arm_i == 1:
                interaction_json = create_interaction_message("", "Fire extinguisher bottle is pushed")
                igs.output_set_string("interaction_message", interaction_json)
            elif self.agent.l_bottle_arm_i is not None and self.agent.l_bottle_arm_i == 0:
                interaction_json = create_interaction_message("", "Fire extinguisher bottle is NOT pushed")
                igs.output_set_string("interaction_message", interaction_json)
            else:
                interaction_json = create_interaction_message("", "Fire extinguisher bottle state is UNKNOWN")
                igs.output_set_string("interaction_message", interaction_json)
        elif self.engine_failed_side == "Right":
            if self.agent.r_bottle_arm_i is not None and self.agent.r_bottle_arm_i == 1:
                interaction_json = create_interaction_message("", "Fire extinguisher bottle is pushed")
                igs.output_set_string("interaction_message", interaction_json)
            elif self.agent.r_bottle_arm_i is not None and self.agent.r_bottle_arm_i == 0:
                interaction_json = create_interaction_message("", "Fire extinguisher bottle is NOT pushed")
                igs.output_set_string("interaction_message", interaction_json)
            else:
                interaction_json = create_interaction_message("", "Fire extinguisher bottle state is UNKNOWN")
                igs.output_set_string("interaction_message", interaction_json)
        
    def check_fuel_boost_off_send_signal(self):
        igs.output_set_string("interaction_message", create_interaction_message("", self.get_interaction_fuel_boost_off(), ""))
        
    def check_pax_safety_send_signal(self):
        if self.agent.pax_safety_i is not None and self.agent.pax_safety_i < 1:
            interaction_json = create_interaction_message("", "PAX SAFETY Switch is OFF")
            igs.output_set_string("interaction_message", interaction_json)
            if self.states[("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY")].autonomy_role == "performer":
                self.on_speak_action("PAX SAFETY Switch is OFF")
        elif self.agent.pax_safety_i is not None and self.agent.pax_safety_i >= 1:
            interaction_json = create_interaction_message("", "PAX SAFETY Switch is ON")
            igs.output_set_string("interaction_message", interaction_json)
            if self.states[("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY")].autonomy_role == "performer":
                self.on_speak_action("PAX SAFETY Switch is ON")
        else:
            interaction_json = create_interaction_message("", "PAX SAFETY Switch state is UNKNOWN")
            igs.output_set_string("interaction_message", interaction_json)
            if self.states[("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY")].autonomy_role == "performer":
                self.on_speak_action("PAX SAFETY Switch state is UNKNOWN")
    
    def check_fadec_bug_to_send_signal(self):
        if self.agent.n1_match_bug_i is not None:
            if self.agent.n1_match_bug_i == False:
                interaction_json = create_interaction_message("", "FADEC BUG is not set to TO")
                igs.output_set_string("interaction_message", interaction_json)
                if self.states[("TAKEOFF", "FADEC bug", "CHECK TO")].autonomy_role == "performer":
                    self.on_speak_action("FADEC ABNORMAL")
                    igs.output_set_string("alert", create_alert_message("FADEC N1 Match Bug is not set to TO", "yellow", "warning"))
            else:
                interaction_json = create_interaction_message("", "FADEC BUG is set to TO")
                igs.output_set_string("interaction_message", interaction_json)
                if self.states[("TAKEOFF", "FADEC bug", "CHECK TO")].autonomy_role == "performer":
                    self.on_speak_action("FADEC NORMAL")
    
    def check_anti_coll_lights_send_signal(self):
        if self.agent.anti_coll_lights_i is not None and self.agent.anti_coll_lights_i == False:
            interaction_json = create_interaction_message("", "ANTI-COLLISION Lights are OFF")
            igs.output_set_string("interaction_message", interaction_json)
            if self.states[("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON")].autonomy_role == "performer":
                self.on_speak_action("ANTI-COLLISION Lights are OFF")
        elif self.agent.anti_coll_lights_i is not None and self.agent.anti_coll_lights_i == True:
            interaction_json = create_interaction_message("", "ANTI-COLLISION Lights are ON")
            igs.output_set_string("interaction_message", interaction_json)
            if self.states[("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON")].autonomy_role == "performer":
                self.on_speak_action("ANTI-COLLISION Lights are ON")
        else:
            interaction_json = create_interaction_message("", "ANTI-COLLISION Lights state is UNKNOWN")
            igs.output_set_string("interaction_message", interaction_json)
            if self.states[("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON")].autonomy_role == "performer":
                self.on_speak_action("ANTI-COLLISION Lights state is UNKNOWN")
    
    def select_altitude_action(self):
        if self.states[("LINE-UP AND HOLD", "Select Altitude", "PRESET AS CLEARED")].autonomy_role == "performer":
            self.on_speak_action(f"I am setting autopilot altitude preset to {self.CLEARED_ALTITUDE} feet as cleared by ATC.")
            igs.output_set_int("alt_sel", self.CLEARED_ALTITUDE)
            #time.sleep(1)  # Wait a moment
            msg = create_interaction_message("", f"Cleared to altitude {self.CLEARED_ALTITUDE} ft from ATC.")
            igs.output_set_string("interaction_message", msg)
            #time.sleep(2)
            self.on_speak_action("Altitude set.")
        else:
            igs.output_set_string("interaction_message", create_interaction_message("", self.INTERACTION_ALT_PRESET)) 

    # ===================================================================
    # String - String Database for display on the GUI
    # ===================================================================
    
    # FLAPS - Takeoff configuration
    INTERACTION_FLAPS_TAKEOFF = "Set flap handle to TAKEOFF position (15°)"

    # FLAPS - UP (retracted)
    INTERACTION_FLAPS_UP = "FLAP HANDLE — UP\n\nRetract flap handle to UP position.\nVerify FLAPS indicator shows 0° on EICAS."

    # Crew Briefing - WANRAM Departure Memo
    INTERACTION_CREW_BRIEFING_WEATHER = "WEATHER\nTemp 5°C, fog, reduced visibility expected.\nWind 190° at 4 kts, light crosswind from the left for RWY 24R.\nRunway dry.\nNo gusts, no thunderstorms, no wind shear reports."

    INTERACTION_CREW_BRIEFING_WEATHER_TARS = "METAR: CYUL 201500Z 19004KT 1SM FG OVC015 05/04 A2992\nCrosswind: 02 kt from the left\nHeadwind: 3.5 kt"

    INTERACTION_CREW_BRIEFING_AIRCRAFT = "AIRCRAFT\n\nCessna Citation Mustang (Model 510).\nNo MEL items / tech log issues affecting departure."
    INTERACTION_CREW_BRIEFING_AIRCRAFT_TARS = "Aircraft: Cessna Citation Mustang (510)"

    INTERACTION_CREW_BRIEFING_NOTAMS = "NOTAMs\n\nNo departure-critical NOTAMs affecting runway 24R or initial climb."
    INTERACTION_CREW_BRIEFING_NOTAMS_TARS = "No critical NOTAMs for RWY 24R departure."

    INTERACTION_CREW_BRIEFING_ROUTING = "ROUTING\n\nDeparture RWY 24R CYUL.\nRunway heading after takeoff.\nInitial climb to 5 000 ft.\nWaypoints: After EBMAN THEN BIRPO: right turn direct CYOW, plan arrival RWY 07."
    INTERACTION_CREW_BRIEFING_ROUTING_TARS = "RWY 24R → HDG 237 → 5000 ft\nEBMAN → BIRPO → CYOW RWY 07"

    INTERACTION_CREW_BRIEFING_AUTOMATION = "AUTOMATION\n\nManual takeoff.\nAfter 800 ft AGL:\n  • Engage autopilot\n  • Heading mode — runway heading\n  • FLC 120 kt climb to 5 000 ft."

    INTERACTION_CREW_BRIEFING_AUTOMATION_TARS = "Manual TO → AP @ 800 ft AGL\nHDG mode → FLC 120 kt → 5000 ft"

    INTERACTION_CREW_BRIEFING_MISCELLANEOUS = "MISCELLANEOUS\n\nSingle passenger onboard.\nAbnormality plan:\n  • Before V1 → reject takeoff.\n  • After V1 → continue, maintain V2 120 kt, climb to 1 500 ft, then handle checklists."

    INTERACTION_CREW_BRIEFING_MISCELLANEOUS_TARS = "1 PAX onboard\nBefore V1: RTO\nAfter V1: continue → 120 kt → 1500 ft AGL → checklists"

    # Pitot Static Switch
    INTERACTION_PITOT_STATIC_SWITCH = "PITOT STATIC HEAT SWITCH - PITOT-STATIC\nCAUTION\n\nLIMIT GROUND OPERATION OF PITOT-STATIC HEAT TO TWO MINUTES TO PRECLUDE DAMAGE TO THE PITOT-STATIC AND STALL WARNING HEATERS."
    
    # Anti-Ice Requirements
    INTERACTION_ENGINE_ANTI_ICE = "LAST METAR TEMPERATURE 05 degrees Celsius - IF VISIBLE MOISTURE PRESENT, ENGINE ANTI-ICE ON"
    INTERACTION_WINDSHIELD_ANTI_ICE = "LAST METAR TEMPERATURE 05 degrees Celsius - IF VISIBLE MOISTURE PRESENT, WINDSHIELD ANTI-ICE ON"
    INTERACTION_ANTI_ICE_SYSTEMS = "LAST METAR TEMPERATURE 05 degrees Celsius - IF VISIBLE MOISTURE PRESENT, ANTI-ICE SYSTEMS ON"
    
    # Landing Lights
    INTERACTION_LANDING_LIGHT_RUNWAY = "On an active runway, to enhance visibility: LANDING LIGHTS ON"
    INTERACTION_LANDING_LIGHT_AFTER_TAKEOFF = "After takeoff, and under 10 000 ft AGL to enhance visibility: LANDING LIGHTS ON"

    # Announce Alarm
    def get_alarm_callout(self) -> str:
        if self.is_engine_failed():
            return f"{self.engine_failed_side.upper()} ENGINE FIRE, Low oil pressure {self.engine_failed_side.upper()}"
        else:
            return "ALARM CONDITION UNKNOWN"
    
    # Winds Display
    INTERACTION_WINDS_HEADER = "WIND REPORT:\n\nMETAR: CYUL 201500Z 19004KT 1SM FG OVC015 05/04 A2992 \nRMK CU OVC TOPS 100 MSL CI BASE 250 TOP 120 DRY RWY"
    INTERACTION_WINDS_DATA = "WIND 190 degrees / 04 kt\nCrosswind Component: 03 kt from the left < Max Crosswind (25 knots)\nHeadwind Component: 2.7 kt"
    INTERACTION_FALSE_WINDS_HEADER = "WIND REPORT:\n\nMETAR: CYHU 201500Z 29004KT 1SM FG OVC015 05/04 A2992 \nRMK CU OVC TOPS 100 MSL CI BASE 250 TOP 120 DRY RWY"
    INTERACTION_FALSE_WINDS_DATA = "WIND 290 degrees / 08 kt\nCrosswind Component: 06 kt from the right < Max Crosswind (25 knots)\nHeadwind Component: 5 kt"
    FALSE_WIND_CALLOUT = "Wind 290 degrees at 8 knots"
    
    # Altitude Preset
    INTERACTION_ALT_PRESET = f"CLEARED TO ALTITUDE {CLEARED_ALTITUDE} FT FROM ATC"

    #V1 Speed Display
    INTERACTION_SHOW_V_ONE = f"V1 = {V_ONE} knots"

    INTERACTION_SET_SPD_MODE = "ARMING SPEED MODE"
    INTERACTION_SET_HDG_MODE = "ARMING HEADING MODE"

    INTERACTION_CHECK_V2_PLUS_10 = f"CHECK IAS V2+10 = {V_TWO + 10} KNOTS"
    def get_interaction_current_airspeed(self) -> str:
        current_speed = self.agent.airspeed_i if self.agent.airspeed_i is not None else 0
        return f"Current indicated airspeed: {current_speed} knots"

    #After takeoff checklist
    INTERACTION_START_AFT_TO_CHECKLIST = "Safe altitude reached. Ready to start After Takeoff Checklist."

    #Safe altitude reached
    INTERACTION_SAFE_ALTITUDE_REACHED = "Safe altitude is 1500 feet AGL."
    
    # Emergency - Engine Failure After V1
    INTERACTION_ENG_FAILURE_AFT_V1_MEMO = "ENGINE FAILURE OR FIRE OR MASTER WARNING \nOR ANY OTHER NON-NORMAL EVENT DURING TAKEOFF SPEED ABOVE V1\n\n1. Maintain directional control\n2. Accelerate to Vr = {V_ROTATE}\n3. Rotate at Vr = {V_ROTATE}, climb at V2 = {V_TWO}\n4. LANDING GEAR - UP (after positive rate of climb)\n5. At 1,500 feet AGL, retract flaps at V2+10  and accelerate to Venr = {V_ENR}"
    INTERACTION_ENG_FAILURE_AFT_V1_TARS_INPUT = "Engine fire detected on {engine_side} engine."
    
    # Engine Fire
    # Immediate Action Items
    INTERACTION_IMMEDIATE_ACTION_ITEMS = "IMMEDIATE ACTION ITEMS:\n\nNON-NORMAL EVENT DURING TAKEOFF\n1. Climb to a safe altitude (1500ft AGL)\n\nENGINE FIRE L OR R\n(ENGINE FIRE WARNING LIGHT ILLUMINATED)\n1. Throttle ({engine_side}) - IDLE\nIF LIGHT REMAINS ON (15 SECONDS)\n2. ENGINE FIRE Button ({engine_side}) LIFT COVER and PUSH"
    def get_immediate_action_items(self) -> str:
        return f"IMMEDIATE ACTION ITEMS:\nNON-NORMAL EVENT DURING TAKEOFF\n1. Climb to a safe altitude (1500ft AGL)\nENGINE FIRE L OR R\n(ENGINE FIRE WARNING LIGHT ILLUMINATED)\n1. Throttle ({self.engine_failed_side}) - IDLE\nIF LIGHT REMAINS ON (15 SECONDS)\n2. ENGINE FIRE Button ({self.engine_failed_side}) LIFT COVER and PUSH"

    # Prompt Messages
    INTERACTION_PROMPT_START_CHECKLIST = "{callout}?"
    INTERACTION_PROMPT_NEXT_CHECKLIST = "{value}?"
    
    # Trim/Rudder Approval
    INTERACTION_ALLOW_TRIM_RUDDER = "Allow TARS to adjust trim/rudder settings?"

    def get_interaction_allow_trim_rudder(self) -> str:
        return f"Adjust rudder trim for {self.engine_failed_side} engine failure"
    
    # Autopilot Approval
    INTERACTION_ALLOW_ENGAGE_AP = "Allow TARS to engage the autopilot?"

    def get_interaction_throttle_cutoff(self) -> str:
        return f"Throttle {self.engine_failed_side} CUTOFF"
    
    def get_interaction_fuel_boost_off(self) -> str:
        if self.is_fuel_boost_off():
            return f"FUEL BOOST Switch {self.engine_failed_side} is OFF"
        else:
            return f"FUEL BOOST Switch {self.engine_failed_side} is ON"
    
    def get_interaction_flaps(self) -> str:
        if self.agent.control_flaps_i is not None:
            if self.agent.control_flaps_i == 0.5:
                return f"FLAP HANDLE is currently set to TAKEOFF position (15°)"
            elif self.agent.control_flaps_i == 0.0:
                 return f"FLAP HANDLE is currently set to UP position (0°)"
            elif self.agent.control_flaps_i == 1.0:
                 return f"FLAP HANDLE is currently set to FULL position (40°)"
            else:
                 return f"FLAP HANDLE is currently set to an intermediate position ({self.agent.control_flaps_i})"
        else:
            return f"FLAP HANDLE is currently set to an unknown position ({self.agent.control_flaps_i})"
    
    def get_interaction_fuel_boost_norm(self) -> str:
        return f"FUEL BOOST Switch {self.engine_failed_side} NORM"
    
    def get_interaction_check_engine_fire_light(self) -> str:
        return f"Check ENGINE FIRE light {self.engine_failed_side} remains ON"
    
    # Speed Display
    INTERACTION_SHOW_V_ENR = "Set speed to VEnr = {V_ENR} knots"
    
    def get_interaction_set_heading(self) -> str:
        if self.TARS_RELIABLE:
            return f"Set heading to {VECTOR_HEADING} degrees"
        else:
            return f"Set heading to {FALSE_VECTOR_HEADING} degrees"

    INTERACTION_SET_HEADING = f"Set heading to {VECTOR_HEADING} degrees"
    INTERACTION_SET_ALTITUDE = f"Set altitude to {VECTOR_ALTITUDE} feet"
    # ATC Communication Approval
    def get_interaction_prompt_mayday(self) -> str:
        return f"Declare MAYDAY to Montreal Departure on {self.DEPARTURE_FREQUENCY} for {self.engine_failed_side} engine fire at {self.altitude_rounded} feet, heading {self.agent.heading_i} degrees?"
    def get_mayday_message(self) -> str:
        return f"Mayday, Mayday, Mayday,  Cessna Papa Oscar Lima Yankee, engine fire, {self.altitude_rounded} feet, continuing {self.agent.heading_i} degrees heading, two souls on board."
    
    INTERACTION_MAYDAY_READBACK = "C-POLY, Montréal Tower, roger Mayday. Continue runway heading. You are cleared to return runway two-four right to land. Emergency vehicles are standing by."
    
    # PAN-PAN Announcement
    #INTERACTION_PROMPT_ANNOUNCE_PANPAN = f"Do you want me to announce announce PAN-PAN and request vectors to Montreal Departure on {self.DEPARTURE_FREQUENCY}?"
    def get_interaction_prompt_panpan(self) -> str:
        return f"Announce PAN-PAN to Montreal Departure on {self.DEPARTURE_FREQUENCY} for {self.engine_failed_side} engine failure at {self.altitude_rounded} feet, heading {self.agent.heading_i} degrees?"
    def get_panpan_message(self) -> str:
        return f"Pan-Pan, Pan-Pan, Pan-Pan, Montreal Tower, Cessna Papa Oscar Lima Yankee, single engine operation after engine failure, {self.altitude_rounded} feet, {self.position_compared_to_initial}, {self.heading} degrees.  requesting vectors for immediate return to runway {self.RUNWAY_NUMBER}"

    def get_vectors_atc_string(self) -> str:
        return f"C-POLY, Montréal Tower, roger. Turn right heading three-three-zero, descend and maintain three thousand feet. Expect ILS approach runway two-four right."

    def get_vectors_prompt(self) -> str:
        if self.TARS_RELIABLE:
            return f"ATC has instructed to turn right heading {VECTOR_HEADING} degrees, descend and maintain {VECTOR_ALTITUDE} feet. Expect ILS approach runway 24R.\n\nDo you want me to set the heading and altitude?"
        else:
            return f"ATC has instructed to turn right heading {FALSE_VECTOR_HEADING} degrees, descend and maintain {VECTOR_ALTITUDE} feet. Expect ILS approach runway 24R.\n\nDo you want me to set the heading and altitude?"
    # Display Messages
    INTERACTION_DISPLAY_TRIM_RUDDER = "Adjusting rudder trim for single-engine operation"
    INTERACTION_DISPLAY_ALARM = "Alarm: Engine Fire"
    INTERACTION_DISPLAY_ENGAGE_AUTOPILOT = "Engage Autopilot: "
    
    # Immediate Action Item (single)
    INTERACTION_IMMEDIATE_ACTION_ITEM = "Immediate action item : \n1. Throttle {engine_side} engine throttle IDLE\n- IF LIGHT REMAINS ON (15 SECONDS)\nIlluminated ENGINE FIRE Switch LIFT COVER AND PUSH"
    
    # Checklist Prompts
    INTERACTION_CHECKLIST_EMER_ENG_FIRE_CONTINUE = "Emergency Fire Checklist: "
    INTERACTION_CHECKLIST_AFT_TAKEOFF_CONTINUE = "After takeoff Checklist: "
    INTERACTION_CHECKLIST_AFT_TAKEOFF = "After takeoff Checklist: "
    INTERACTION_CHECKLIST_ENG_FAIL_PROC_CONTINUE = "Engine Failure Procedure"
    INTERACTION_CHECKLIST_ENG_FAIL_PROC = "Engine Failure Procedure"
    INTERACTION_CHECKLIST_SING_ENG_APP = "Single Engine Approach and Landing Checklist"
    
    # Yaw Damper
    def get_interaction_engage_yaw_damper(self) -> str:
        if self.is_engine_failed():
            return self.INTERACTION_YAW_DAMPER_SINGLE_ENGINE
        else:
            return self.INTERACTION_YAW_DAMPER_NORMAL
    INTERACTION_YAW_DAMPER_SINGLE_ENGINE = "OFF for full rudder authority during single-engine operations"
    INTERACTION_YAW_DAMPER_NORMAL = "ON for comfort during normal operations"
    
    # Pax Safety Switch
    def get_interaction_pax_safety_switch(self) -> str:
        if self.is_engine_failed():
            return self.INTERACTION_PAX_SAFETY_SWITCH_ENG_FAILED
        else:
            return self.INTERACTION_PAX_SAFETY_SWITCH_NORMAL
    INTERACTION_PAX_SAFETY_SWITCH_ENG_FAILED = "ABNORMAL SITUATION: PAX SAFETY Switch SET TO SEATBELT"
    INTERACTION_PAX_SAFETY_SWITCH_NORMAL = "PAX SAFETY Switch SET TO OFF"

    def get_interaction_gen_switch_off(self) -> str:
        if self.engine_failed_side == "Left":
            return "GENERATOR Switch LEFT OFF"
        else:
            return "GENERATOR Switch RIGHT OFF"
    
    def get_interaction_ignition_switch_norm(self) -> str:
        if self.engine_failed_side == "Left":
            return "IGNITION Switch LEFT NORM"
        else:
            return "IGNITION Switch RIGHT NORM"
    
    INTERACTION_REDUCE_ELECTRICAL_LOAD = "Reduce electrical load to under 300 amps"

    INTERACTION_FUEL_TRANSFER_KNOB = "Checking fuel balance"
    def get_interaction_verify_engine_fire_switch(self) -> str:
        return f"Verify ENGINE FIRE Switch {self.engine_failed_side} is PUSHED"
    
    INTERACTION_NEXT_CHECKLIST_SINGLE_ENGINE_APPROACH = "Next: Single Engine Approach and Landing Checklist"
    
    # Altimeter
    INTERACTION_ALTI_SET_STD = "Setting altimeter to STD"
    
    # Cautions
    INTERACTION_CAUTION_TEXT_READOUT = "Caution: \nIf possible, the engines should remain at idle for a minimum of two minutes prior to shutdown to allow the engine inter-turbine temperature to stabilize and avoid turbine blade rub.\nIf the engine windmills for more than 15 minutes without a positive indication of oil pressure, a notation is required in the engine logbook and the engine must be inspected in accordance with the Pratt & Whitney engine maintenance manual.\nIf the engine windmills for more than 30 minutes with the firewall shutoff closed or the boost pump turned off, the engine fuel pump must be inspected in accordance with the Pratt & Whitney engine maintenance manual."
    
    # Pressurization
    INTERACTION_PRESSURIZATION_CHECK = "Pressurization Check: "
    INTERACTION_PRESSURIZATION_STATUS = "CABIN ALTITUDE: NORMAL\nDIFFERENTIAL PRESSURE: NORMAL"
    
    # Button Labels
    BUTTON_LABEL_EDIT = "EDIT"
    BUTTON_LABEL_CHECK = "CHECK"
    BUTTON_LABEL_START = "START"
    BUTTON_LABEL_NEXT = "NEXT"
    BUTTON_LABEL_CANCEL = "CANCEL"
    BUTTON_LABEL_APPROVE = "APPROVE"
    BUTTON_LABEL_DENY = "DENY"
    BUTTON_LABEL_START_CHECKLIST = "START CHECKLIST"
    
    # Alert Messages
    def get_alert_engine_fire(self) -> str:
        return f"Failure detected: {self.engine_side} ENGINE FIRE"

    # ===================================================================
    # End of String - String Database for display on the GUI
    # ===================================================================

# Example usage
if __name__ == "__main__":
    agent = TarsAgent()
    agent.start()