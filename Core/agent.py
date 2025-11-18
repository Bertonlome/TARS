from doctest import master
from operator import is_
#from os import wait
import stat
import time
import signal
from pathlib import Path
from Core.echo import *
from Core.fsm import FiniteStateMachine, State, Transition
from Core.tts import speak_wait
import csv

from ingescape import output_create
from PySide6.QtCore import QObject, Signal

# Direct import for better IDE support
try:
    import ingescape as igs
except ImportError:
    # Fallback if already imported via echo
    pass

### PARAMETERS ###
V_ONE = 90  # Takeoff decision speed
V_ROTATE = 100  # Rotation speed
V_TWO = 120  # Climb speed
AIRSPEED_ALIVE_THRESHOLD = 40  # Minimum airspeed to consider "alive"
SEVENTY_KTS = 70  # 70 knots speed

# Agent Class
class TarsAgent(QObject):
    # Define signals
    alertRequested = Signal(str, str)  # (message, color)
    
    def __init__(self, agent_name="TARS Agent", device="Wi-Fi", port=5670, verbose=False):
        super().__init__()  # Initialize QObject
        self.agent_name = agent_name
        self.device = device
        self.port = port
        self.verbose = verbose
        self.is_interrupted = False
        self.impulsion_count = 0

        # FSM setup
        self.task_done_human = [False]
        #conditions
        self.is_on_off = [False]
        self.is_allowed_to_comm_atc = [False]
        self.is_requesting_vectors = [False]
        self.engine_failed_side = "None"

        # Alert state tracking to prevent spam
        self.engine_spool_alert_sent = False
        
        # TTS completion event - will be set by MainWindow
        self.tts_completion_event = None
        
        # Reference to main window - will be set by MainWindow for countdown synchronization
        self.main_window = None
        
        # Input-to-condition mapping for event-driven monitoring
        # Maps input names to condition function names that depend on them
        self.input_to_conditions = {
            'control_throttle': ['is_thrust_toga', 'is_throttle_clb'],
            'control_gear': ['is_gear_up'],
            'control_flaps': ['is_flaps_retracted'],
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
        allocation_csv_path = Path(__file__).parent / "briefing_export_HIGH_LOA.csv"        
        # Create states from allocation CSV
        self.states = self.create_states_from_csv(allocation_csv_path)
        self.checklists = self.create_checklists_from_states(self.states)
        idle_key = ("IDLE", "Idle", "WAITING")
        finished_key = ("FINISHED", "Finished", "COMPLETED")
        self.fsm = FiniteStateMachine(self.states[("LINE-UP AND HOLD", "Runway centerline", "ALIGN")])

        # BEFORE TAKEOFF Procedure
        self.fsm.add_transition(Transition(
            self.states[("IDLE", "Idle", "WAITING")], 
            self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")], 
            self.is_started, 
            lambda: self.on_speak_action(self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")].callout)))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")], 
            self.states[("BEFORE TAKEOFF", "Pitot-Static Switch", "PITOT-STATIC")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "Pitot-Static Switch", "PITOT-STATIC")], 
            self.states[("BEFORE TAKEOFF", "ENGINE ANTI-ICE Switches", "AS REQUIRED")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "ENGINE ANTI-ICE Switches", "AS REQUIRED")], 
            self.states[("BEFORE TAKEOFF", "WINDSHIELD ANTI-ICE Switches", "AS REQUIRED")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "WINDSHIELD ANTI-ICE Switches", "AS REQUIRED")], 
            self.states[("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY")], 
            self.states[("BEFORE TAKEOFF", "LANDING Light Switch", "AS DESIRED")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "LANDING Light Switch", "AS DESIRED")], 
            self.states[("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON")], 
            self.states[("BEFORE TAKEOFF", "Radar", "AS REQUIRED")], 
            self.is_acked, 
            self.dummy_action))
        
        # LINE-UP AND HOLD Procedure
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "Radar", "AS REQUIRED")], 
            self.states[("LINE-UP AND HOLD", "Runway centerline", "ALIGN")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("LINE-UP AND HOLD", "Runway centerline", "ALIGN")], 
            self.states[("LINE-UP AND HOLD", "Winds", "CHECK")], 
            self.allow_transition, 
            lambda: self.on_speak_action(self.states[("LINE-UP AND HOLD", "Winds", "CHECK")].callout) if self.states[("LINE-UP AND HOLD", "Winds", "CHECK")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("LINE-UP AND HOLD", "Winds", "CHECK")], 
            self.states[("LINE-UP AND HOLD", "Brakes", "HOLD")], 
            self.is_acked, 
            self.dummy_action))
        
        # TAKEOFF Procedure
        self.fsm.add_transition(Transition(
            self.states[("LINE-UP AND HOLD", "Brakes", "HOLD")], 
            self.states[("TAKEOFF", "CAS", "CHECK CLEAR")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "CAS", "CHECK CLEAR")], 
            self.states[("TAKEOFF", "\"Set thrust\"", "ANNOUNCE")], 
            self.allow_transition, 
            self.takeoff_throttles_action_dev_mode))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Set thrust\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "THROTTLES", "TO Detent")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "THROTTLES", "TO Detent")], 
            self.states[("TAKEOFF", "FADEC bug", "CHECK TO")], 
            self.is_thrust_toga, 
            lambda: self.on_speak_action(self.states[("TAKEOFF", "FADEC bug", "CHECK TO")].callout) if self.states[("TAKEOFF", "FADEC bug", "CHECK TO")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "FADEC bug", "CHECK TO")], 
            self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")], 
            self.is_fadec_bug_to, 
            lambda: self.on_speak_action(self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")].callout) if self.states[("TAKEOFF", "\"Thrust set\"", "ANNOUNCE")].autonomy_role == "performer" and self.is_engine_spool_even() else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")], 
            self.states[("TAKEOFF", "\"Thrust set\"", "ANNOUNCE")], 
            self.is_engine_spool_even, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Thrust set\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "Engine Instruments", "CHECK NORMAL")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Engine Instruments", "CHECK NORMAL")], 
            self.states[("TAKEOFF", "Brakes", "RELEASE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Brakes", "RELEASE")], 
            self.states[("TAKEOFF", "\"Airspeed's alive\"", "ANNOUNCE")], 
            self.is_brake_released, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Airspeed's alive\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")], 
            self.is_airspeed_alive, 
            lambda: self.on_speak_action(self.states[("TAKEOFF", "\"Airspeed's alive\"", "ANNOUNCE")].callout)))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")], 
            self.is_seventy_kts, 
            lambda: self.on_speak_action(self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")].callout)))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")], 
            self.is_v_one, 
            lambda: self.on_speak_action(self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")].callout)))
        
        # Rotation and initial climb if no alarms        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "Elevator Control", "ROTATE")], 
            lambda: not self.is_alarm(), 
            lambda: self.on_speak_action(self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")].callout)))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Elevator Control", "ROTATE")], 
            self.states[("TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            lambda: self.is_v_rotate and not self.is_alarm(), 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            self.states[("TAKEOFF", "Slip/Skid", "CHECK")], 
            lambda: self.is_pitch_maintained and not self.is_alarm(), 
            self.check_slip_skid_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Slip/Skid", "CHECK")], 
            self.states[("TAKEOFF", "Climb rate", "CHECK POSITIVE")], 
            lambda: not self.is_alarm(), 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Climb rate", "CHECK POSITIVE")], 
            self.states[("TAKEOFF", "\"Positive rate, gear up\"", "ANNOUNCE")], 
            lambda : self.is_positive_rate and not self.is_alarm(), 
            lambda: self.on_speak_action(self.states[("TAKEOFF", "\"Positive rate, gear up\"", "ANNOUNCE")].callout)))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Positive rate, gear up\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "LANDING GEAR", "UP")], 
            lambda : not self.is_alarm(), 
            self.dummy_action))
        
        # Branch: Normal path to AFTER TAKEOFF
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "LANDING GEAR", "UP")], 
            self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")], 
            self.is_400_ft_no_alarm, 
            self.dummy_action))
        
        # Branch: Emergency path - ENGINE FAILURE DURING TAKEOFF AFTER V1 added transitions for EACH state after V1
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")],
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "APPLY")],
            self.is_engine_failed,
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")],
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "APPLY")],
            self.is_engine_failed,
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Elevator Control", "ROTATE")],
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "APPLY")],
            self.is_engine_failed,
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "APPLY")], 
            self.is_engine_failed, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Slip/Skid", "CHECK")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "APPLY")], 
            self.is_engine_failed, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Climb rate", "CHECK POSITIVE")],
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "APPLY")],
            self.is_engine_failed,
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Positive rate, gear up\"", "ANNOUNCE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "APPLY")], 
            self.is_engine_failed, 
            self.dummy_action))

        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "LANDING GEAR", "UP")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "APPLY")], 
            self.is_engine_failed, 
            self.dummy_action))

        # ENG FAILURE DURING TAKEOFF transitions
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "APPLY")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "TRIM")], 
            self.allow_transition, 
            lambda: self.trim_action() if self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "TRIM")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "TRIM")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Alarm", "ANNOUNCE")], 
            lambda: self.is_slip_skid_centered and self.is_master_warning_on, 
            lambda: self.on_speak_action(f"Alarm {self.engine_failed_side} Engine fire, low oil pressure {self.engine_failed_side}")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Alarm", "ANNOUNCE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "\"Reset Master Warning\"", "ANNOUNCE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "\"Reset Master Warning\"", "ANNOUNCE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Master Warning", "RESET")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Master Warning", "RESET")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")], 
            lambda: not self.is_master_warning_on(), 
            lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            self.allow_transition, 
            lambda : igs.output_set_double("flight_director", 1) if self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "LANDING GEAR", "UP")], 
            self.is_pitch_maintained, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "LANDING GEAR", "UP")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2")], 
            self.is_gear_up, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "\"Speed mode FLC V2, heading mode\"", "ANNOUNCE")], 
            self.is_airspeed_v_two, 
            lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "\"Speed mode FLC V2, heading mode\"", "ANNOUNCE")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "\"Speed mode FLC V2, heading mode\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "\"Speed mode FLC V2, heading mode\"", "ANNOUNCE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")], 
            self.allow_transition, 
            lambda: (igs.output_set_double("speed_mode", 1), self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")].callout)) if self.states[("ENG FAILURE DURING TAKEOFF", "\"Speed mode FLC V2, heading mode\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")], 
            self.allow_transition, 
            lambda: (igs.output_set_double("heading_mode", 1), self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")].callout)) if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")].autonomy_role == "performer" else self.dummy_action()))

        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "LISTEN")], 
            self.is_allowed_comm, 
            lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "LISTEN")].callout)))
        
        # If not allowed to communicate, skip to READBACK
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "READBACK")], 
            lambda: not self.is_allowed_comm(), 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "LISTEN")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "READBACK")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "READBACK")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 700ft AGL")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 700ft AGL")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "\"700ft, engage autopilot\"", "ANNOUNCE")], 
            self.is_ap_altitude, 
            lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "\"700ft, engage autopilot\"", "ANNOUNCE")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "\"700ft, engage autopilot\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "\"700ft, engage autopilot\"", "ANNOUNCE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")], 
            self.is_acked, 
            lambda: (igs.output_set_double("autopilot_master", 1), self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")].callout) ) if self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")].autonomy_role == "performer" else self.dummy_action()))
        
        # If not acked, Check 1500ft AGL directly
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "\"700ft, engage autopilot\"", "ANNOUNCE")],
            self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 1500ft AGL")],
            lambda: not self.is_acked(),
            self.dummy_action))
        

        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 1500ft AGL")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 1500ft AGL")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2+10")], 
            self.is_1500_ft, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2+10")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Obstacles", "CHECK Clear")], 
            self.is_v2_plus_10, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Obstacles", "CHECK Clear")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "\"Retract flaps\"", "Announce")], 
            self.allow_transition, 
            lambda: self.on_speak_action(self.states[("ENG FAILURE DURING TAKEOFF", "\"Retract flaps\"", "Announce")].callout) if self.states[("ENG FAILURE DURING TAKEOFF", "\"Retract flaps\"", "Announce")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "\"Retract flaps\"", "Announce")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "FLAP Handle", "UP")], 
            self.allow_transition, 
            self.dummy_action))
        
        # Branch to ENGINE FIRE procedure
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "FLAP Handle", "UP")], 
            self.states[("ENGINE FIRE", "\"Affected thrust lever, confirm and idle\"", "ANNOUNCE")], 
            self.is_flaps_retracted, 
            lambda: self.on_speak_action(f"Engine fire procedure, {self.engine_failed_side} thrust lever, confirm and idle") if self.states[("ENGINE FIRE", "\"Affected thrust lever, confirm and idle\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        # ENGINE FIRE transitions
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"Affected thrust lever, confirm and idle\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "\"Idle\"", "ANNOUNCE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"Idle\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "Throttle (affected engine)", "IDLE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Throttle (affected engine)", "IDLE")], 
            self.states[("ENGINE FIRE", "\"TOP\"", "ANNOUNCE")], 
            self.is_throttle_idle, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"TOP\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "Chrono", "START")], 
            self.allow_transition, 
            lambda: self.on_speak_action(self.states[("ENGINE FIRE", "\"TOP\"", "ANNOUNCE")].callout) if self.states[("ENGINE FIRE", "\"TOP\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Chrono", "START")], 
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 15s")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 15s")], 
            self.states[("ENGINE FIRE", "Illuminated ENGINE FIRE Switch", "LIFT COVER AND PUSH")], 
            self.allow_transition, 
            lambda: self.on_speak_action(f"{self.engine_failed_side} Engine fire switch, lift cover and push") if self.states[("ENGINE FIRE", "Illuminated ENGINE FIRE Switch", "LIFT COVER AND PUSH")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Illuminated ENGINE FIRE Switch", "LIFT COVER AND PUSH")], 
            self.states[("ENGINE FIRE", "Checklist", "ORDER START")], 
            self.is_acked, 
            lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Checklist", "ORDER START")].callout) if self.states[("ENGINE FIRE", "Checklist", "ORDER START")].autonomy_role == "performer" else self.dummy_action()))
        
        ##TO BE DELETED LATER
        ##self.fsm.add_transition(Transition(
            #self.states[("ENGINE FIRE", "Checklist", "ORDER START")], 
            #self.states[("ENGINE FIRE", "Radio", "ALLOCATE")], 
            #self.is_acked, 
            #self.dummy_action))
        #TO BE DELETED LATER END
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Checklist", "ORDER START")],
            self.states[("ENGINE FIRE", "Checklist", "RETRIEVE")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Checklist", "RETRIEVE")], 
            self.states[("ENGINE FIRE", "Immediate Action Item", "CHECK DONE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Immediate Action Item", "CHECK DONE")], 
            self.states[("ENGINE FIRE", "\"Affected thrust lever, confirm and cutoff\"", "ANNOUNCE")], 
            self.is_acked, 
            lambda: self.on_speak_action(f"{self.engine_failed_side} thrust lever, confirm and cutoff") if self.states[("ENGINE FIRE", "\"Affected thrust lever, confirm and cutoff\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"Affected thrust lever, confirm and cutoff\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "\"cutoff\"", "ANNOUNCE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"cutoff\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "Throttle (affected engine)", "CUTOFF")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Throttle (affected engine)", "CUTOFF")], 
            self.states[("ENGINE FIRE", "\"Affected engine fuel boost confirm off then norm\"", "ANNOUNCE")], 
            self.is_throttle_cutoff, 
            lambda: self.on_speak_action(f"{self.engine_failed_side} engine fuel boost confirm off then norm") if self.states[("ENGINE FIRE", "\"Affected engine fuel boost confirm off then norm\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"Affected engine fuel boost confirm off then norm\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "\"off then norm\"", "ANNOUNCE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"off then norm\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "OFF")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "OFF")], 
            self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "NORM")], 
            self.is_fuel_boost_off, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "NORM")], 
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 30s")], 
            self.is_fuel_boost_norm, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 30s")], 
            self.states[("ENGINE FIRE", "\"30 seconds, light remains on, bottle discharge\"", "ANNOUNCE")], 
            self.allow_transition, 
            lambda: self.on_speak_action(self.states[("ENGINE FIRE", "\"30 seconds, light remains on, bottle discharge\"", "ANNOUNCE")].callout) if self.states[("ENGINE FIRE", "\"30 seconds, light remains on, bottle discharge\"", "ANNOUNCE")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"30 seconds, light remains on, bottle discharge\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "\"discharge\"", "ANNOUNCE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"discharge\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "Illuminated BOTTLE ARMED Switch", "PUSH")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Illuminated BOTTLE ARMED Switch", "PUSH")], 
            self.states[("ENGINE FIRE", "Rotary Test", "FIRE WARN")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Rotary Test", "FIRE WARN")], 
            self.states[("ENGINE FIRE", "Engine fire lights", "Check both illuminate")], 
            self.is_test_knob_turned, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Engine fire lights", "Check both illuminate")], 
            self.states[("ENGINE FIRE", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")], 
            self.is_acked, 
            lambda: self.on_speak_action(self.states[("ENGINE FIRE", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")].callout) if self.states[("ENGINE FIRE", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")], 
            self.states[("ENGINE FIRE", "Checklist", "ANNOUNCE COMPLETED")], 
            self.is_acked, 
            self.dummy_action))
        
        # DECLARE EMERGENCY transitions
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Checklist", "ANNOUNCE COMPLETED")], 
            self.states[("DECLARE EMERGENCY", "ATC", "ANNOUNCE EMERGENCY")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "ATC", "ANNOUNCE EMERGENCY")], 
            self.states[("DECLARE EMERGENCY", "ATC", "REQUEST VECTOR")], 
            self.is_allowed_comm, 
            self.dummy_action))
        
        # If TARS not allowed, skip to READBACK
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "ATC", "ANNOUNCE EMERGENCY")], 
            self.states[("DECLARE EMERGENCY", "ATC", "READBACK")],
            lambda: not self.is_allowed_comm(),
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "ATC", "REQUEST VECTOR")], 
            self.states[("DECLARE EMERGENCY", "ATC", "LISTEN")], 
            self.is_allowed_comm_and_vector, 
            lambda: (self.on_speak_action(self.states[("DECLARE EMERGENCY", "ATC", "ANNOUNCE EMERGENCY")].callout), self.on_speak_action(self.states[("DECLARE EMERGENCY", "ATC", "REQUEST VECTOR")].callout))))

        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "ATC", "REQUEST VECTOR")],
            self.states[("DECLARE EMERGENCY", "ATC", "LISTEN")],
            lambda: not self.is_allowed_comm_and_vector(),
            lambda: self.on_speak_action(self.states[("DECLARE EMERGENCY", "ATC", "ANNOUNCE EMERGENCY")].callout)))

        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "ATC", "LISTEN")], 
            self.states[("DECLARE EMERGENCY", "ATC", "READBACK")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "ATC", "READBACK")], 
            self.states[("DECLARE EMERGENCY", "Heading", "SET ACCORDINGLY")], 
            lambda: self.is_acked() and self.is_allowed_comm_and_vector(), 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "Heading", "SET ACCORDINGLY")], 
            self.states[("DECLARE EMERGENCY", "FLC", "SET ACCORDINGLY")], 
            self.is_acked, 
            self.dummy_action))
        
        # Skip to AFTER TAKEOFF if no vector requested
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "ATC", "READBACK")],
            self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")],
            lambda: self.is_acked() and not self.is_allowed_comm_and_vector(),
            self.dummy_action))

        # Continue to AFTER TAKEOFF from DECLARE EMERGENCY
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "FLC", "SET ACCORDINGLY")], 
            self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")], 
            self.is_acked, 
            lambda: self.on_speak_action(self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].callout) if self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")].autonomy_role == "performer" else self.dummy_action()))
        
        # AFTER TAKEOFF transitions (normal path)
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")], 
            self.states[("AFTER TAKEOFF", "Checklist", "RETRIEVE")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Checklist", "RETRIEVE")], 
            self.states[("AFTER TAKEOFF", "LANDING GEAR Handle", "UP")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "LANDING GEAR Handle", "UP")], 
            self.states[("AFTER TAKEOFF", "Airspeed", "CHECK V2 + 10")], 
            self.is_gear_up, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Airspeed", "CHECK V2 + 10")], 
            self.states[("AFTER TAKEOFF", "Obstacles", "CHECK CLEAR")], 
            self.is_v2_plus_10, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Obstacles", "CHECK CLEAR")], 
            self.states[("AFTER TAKEOFF", "FLAP Handle", "UP")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "FLAP Handle", "UP")], 
            self.states[("AFTER TAKEOFF", "THROTTLES", "CLB Detent")], 
            self.is_flaps_retracted, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "THROTTLES", "CLB Detent")], 
            self.states[("AFTER TAKEOFF", "Yaw Damper", "AS DESIRED")], 
            self.is_throttle_clb, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Yaw Damper", "AS DESIRED")], 
            self.states[("AFTER TAKEOFF", "Anti-Ice/Deice Systems", "AS REQUIRED")], 
            self.allow_transition, 
            lambda: igs.output_set_double("yaw_damper", 1) if self.states[("AFTER TAKEOFF", "Yaw Damper", "AS DESIRED")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Anti-Ice/Deice Systems", "AS REQUIRED")], 
            self.states[("AFTER TAKEOFF", "PAX SAFETY Switch", "AS REQUIRED")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "PAX SAFETY Switch", "AS REQUIRED")], 
            self.states[("AFTER TAKEOFF", "LANDING Light Switch", "AS REQUIRED")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "LANDING Light Switch", "AS REQUIRED")], 
            self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")], 
            self.is_acked, 
            lambda: self.on_speak_action(self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")].callout) if self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")], 
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")], 
            self.is_cab_alt_ok, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")], 
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "CROSSCHECK")], 
            self.allow_transition, 
            lambda: (igs.output_set_double("altimeter_setting", 29.92), self.on_speak_action("Setting altimeter to standard pressure")) if self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "CROSSCHECK")], 
            self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")], 
            self.is_acked, 
            self.dummy_action))
        
        # Branch: Normal completion 
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")], 
            self.states[finished_key], 
            self.is_engine_not_failed, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")], 
            self.states[("AFTER TAKEOFF", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")], 
            self.is_engine_failed, 
            lambda: self.on_speak_action("Start checklist: Engine Failure/Precautionary Shutdown Procedure and Checklist") if self.states[("AFTER TAKEOFF", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")].autonomy_role == "performer" else self.dummy_action()))
        
        # ENGINE FAILURE/PRECAUTIONARY SHUTDOWN transitions
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Checklist", "ORDER START")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Checklist", "ORDER START")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Checklist", "RETRIEVE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Checklist", "RETRIEVE")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Throttle (affected engine)", "CUTOFF")], 
            self.allow_transition, 
            lambda: self.on_speak_action(f"{self.engine_failed_side} thrust lever, confirm and cutoff") if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Throttle (affected engine)", "CUTOFF")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Throttle (affected engine)", "CUTOFF")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "CAUTION text", "READ")], 
            self.is_throttle_cutoff, 
            lambda: self.on_speak_action(self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "CAUTION text", "READ")].callout) if self.is_acked() else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "CAUTION text", "READ")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "GEN Switch (affected side)", "OFF")], 
            self.allow_transition, 
            lambda: self.on_speak_action(f"Generator switch, {self.engine_failed_side}, off") if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "GEN Switch (affected side)", "OFF")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "GEN Switch (affected side)", "OFF")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "IGNITION switch (affected side)", "NORM")], 
            self.is_gen_switch_off, 
            lambda: self.on_speak_action(f"Ignition switch, {self.engine_failed_side}, norm") if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "IGNITION switch (affected side)", "NORM")].autonomy_role == "performer" else self.dummy_action()))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "IGNITION switch (affected side)", "NORM")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Electrical Load", "REDUCE as required (<= 300A)")], 
            self.is_ignition_switch_norm, 
            self.check_electrical_load_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Electrical Load", "REDUCE as required (<= 300A)")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Fuel TRANSFER Knob", "AS REQUIRED")], 
            self.is_electrical_load_under_limit, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Fuel TRANSFER Knob", "AS REQUIRED")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Verify ENGINE FIRE Switch (affected side)", "Is pushed")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Verify ENGINE FIRE Switch (affected side)", "Is pushed")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Next checklist", "SINGLE-ENGINE APPROACH AND LANDING")], 
            self.is_acked, 
            lambda: self.on_speak_action(self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Next checklist", "SINGLE-ENGINE APPROACH AND LANDING")].callout) if self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Next checklist", "SINGLE-ENGINE APPROACH AND LANDING")].autonomy_role == "performer" else self.dummy_action()))

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
            self.is_engine_not_failed, 
            self.dummy_action))

        self.agent = Echo()
    # END INITIALIZATION OF FSM AND STATES

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
    
    def is_allowed_comm(self):
        if self.is_allowed_to_comm_atc[0]:
            self.is_allowed_to_comm_atc[0] = False
            self.is_requesting_vectors[0] = False
            return True
        return False
    
    def is_allowed_comm_and_vector(self):
        if self.is_allowed_to_comm_atc[0] and self.is_requesting_vectors[0]:
            self.is_allowed_to_comm_atc[0] = False
            self.is_requesting_vectors[0] = False
            return True
        return False
    
    def is_acked(self):
        if self.task_done_human[0]:
            self.task_done_human[0] = False
            return True
        return False
    
    def is_cab_alt_ok(self):
        if self.agent.cabin_altitude_i is not None and self.agent.cabin_altitude_i < 8000:
            return True
        return False
    
    def is_electrical_load_under_limit(self):
        if self.engine_failed_side == "Left":
            if self.agent.l_gen_load_i is not None and self.agent.l_gen_load_i <= 300:
                return True
        if self.engine_failed_side == "Right":
            if self.agent.r_gen_load_i is not None and self.agent.r_gen_load_i <= 300:
                return True
        return False

    def is_thrust_toga(self):
        if self.agent.control_throttle_i is not None and self.agent.control_throttle_i == 1:
            return True
        return False
    
    def is_engine_spool_even(self):
        if self.agent.e1_n1_percent_i is not None and self.agent.e2_n1_percent_i is not None:
            if self.agent.e1_n1_percent_i > 30 and self.agent.e2_n1_percent_i > 30:  # Both engines above idle
                diff = abs(self.agent.e1_n1_percent_i - self.agent.e2_n1_percent_i)
                if diff <= 5:  # Assuming a threshold of 5% for even spool
                    self.engine_spool_alert_sent = False
                    return True
                else:
                    self.alertRequested.emit("Engine N1 mismatch detected!", "red")
                    self.engine_spool_alert_sent = True
        return False
    
    def is_n1_percent_above_90(self):
        if self.agent.e1_n1_percent_i is not None and self.agent.e2_n1_percent_i is not None:
            if self.agent.e1_n1_percent_i >= 90 and self.agent.e2_n1_percent_i >= 90:
                return True
        return False
    
    def is_fadec_bug_to(self):
        if self.agent.n1_match_bug_i is not None and self.agent.n1_match_bug_i >= 0: # Assuming FADEC bug set to TO position is represented by a value >= 0
            return True
        return False

    def is_brake_released(self):
        if self.agent.park_brakes_i is not None and self.agent.park_brakes_i == 0:
            return True
        return False

    def is_airspeed_alive(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i > 10:
            return True
        return False

    def is_seventy_kts(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 70:
            return True
        return False

    def is_v_one(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 90:
            return True
        return False

    def is_v_rotate(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 100:
            return True
        return False
    
    def is_pitch_maintained(self):
        if self.agent.pitch_i is not None and self.agent.pitch_i >= 7:
            if self.agent.pitch_i >= 8:
                return True
        return False

    def is_slip_skid_centered(self):
        if self.agent.slip_skid_i is not None and abs(self.agent.slip_skid_i) < 2:
            return True
        return False

    def is_positive_rate(self):
        if self.agent.vertical_speed_i is not None and self.agent.vertical_speed_i > 100:
            return True
        return False
    
    def is_400_ft_no_alarm(self):
        if self.agent.altitude_i is not None and self.agent.altitude_i >= 400:
            if self.agent.master_warning_i is None or self.agent.master_warning_i == 0:
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
        # Just return the alarm condition - UI will auto-discover the procedure
        if self.agent.master_warning_i is not None and self.agent.master_warning_i == 1 or self.agent.master_caution_i is not None and self.agent.master_caution_i == 1:
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

    def is_engine_not_failed(self):
        if self.agent.e1_n1_percent_i is not None and self.agent.e1_n1_percent_i >= 50:
            if self.agent.e2_n1_percent_i is not None and self.agent.e2_n1_percent_i >= 50:
                return True
        return False
    
    def is_airspeed_v_two(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 120:
            return True
        return False
    
    def is_ap_altitude(self):
        if self.agent.altitude_i is not None and self.agent.altitude_i >= 700:
            return True
        return False

    def is_1500_ft(self):
        if self.agent.altitude_i is not None and self.agent.altitude_i >= 1500:
            return True
        return False
    
    def is_v2_plus_10(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 130:
            return True
        return False
    
    def is_flaps_retracted(self):
        if self.agent.control_flaps_i is not None and self.agent.control_flaps_i == 0:
            return True
        return False
    
    def is_throttle_cutoff(self):
        if self.agent.l_throttle_i == 0 or self.agent.r_throttle_i == 0:
            return True
        return False
    
    def is_fuel_boost_off(self):
        #print(f"Checking if fuel boost is off - Left: {self.agent.fuel_boost_l_i}, Right: {self.agent.fuel_boost_r_i}")
        if self.agent.fuel_boost_l_i == 1 or self.agent.fuel_boost_r_i == 1:
            return True
        return False
    
    def is_fuel_boost_norm(self):
        if self.agent.fuel_boost_l_i == 0 and self.agent.fuel_boost_r_i == 0:
            return True
        return False
    
    def is_test_knob_turned(self):
        if self.agent.test_knob_i is not None and self.agent.test_knob_i == 1:
            return True
        return False
    
    def is_throttle_clb(self):
        if self.agent.control_throttle_i is not None and self.agent.control_throttle_i > 0.8 and self.agent.control_throttle_i < 0.9 :
            return True
        return False
    
    
    def is_throttle_idle(self):
        if self.agent.l_throttle_i is not None and self.agent.l_throttle_i == 0 or self.agent.r_throttle_i == 0:
            return True
        return False
    
    def is_gen_switch_off(self):
        if self.agent.l_gen_switch_i == 0 or self.agent.r_gen_switch_i == 0:
            return True
        return False
    
    def is_ignition_switch_norm(self):
        if self.agent.l_ign_switch_i == 1 or self.agent.r_ign_switch_i == 1:
            return True
        return False
    
    def is_slip_skid_centered(self):
        """Check if slip/skid indicator is centered (within tolerance)"""
        if self.agent.slip_i is not None:
            # Consider centered if within ±1 degree
            return abs(self.agent.slip_i) <= 1
        return False
    
    def is_v2_plus_10(self):
        """Check if airspeed is at V2+10 (120 + 10 = 130 kts)"""
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 130:
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
        # Only check if main_window and FSM worker are available
        if not self.main_window or not hasattr(self.main_window, 'fsm_worker'):
            return
        
        fsm_worker = self.main_window.fsm_worker
        
        # Iterate through all actively monitored conditions
        for state_key, monitor_info in list(fsm_worker.active_monitored_conditions.items()):
            condition_func_name = monitor_info['condition_func_name']
            
            # Is this monitored condition affected by the input that just changed?
            if condition_func_name in affected_condition_names:
                # Re-evaluate the condition
                condition_func = monitor_info['condition_func']
                try:
                    current_value = condition_func()  # Call it (e.g., is_gear_up())
                except Exception as e:
                    print(f"Error evaluating condition {condition_func_name}: {e}")
                    continue
                
                last_value = monitor_info['last_value']
                
                # Has the condition changed?
                if current_value != last_value:
                    # VIOLATION or RESTORATION detected!
                    monitor_info['last_value'] = current_value
                    state = monitor_info['state']
                    
                    # Update state.condition attribute
                    state.condition = current_value
                    
                    # Emit signal to UI thread
                    if current_value is False:
                        # Condition violated (was True, now False)
                        print(f"⚠️  VIOLATION: {state.procedure} - {state.task_object} - condition '{condition_func_name}' no longer satisfied!")
                        fsm_worker.condition_violated_signal.emit(state, condition_func_name)
                    elif current_value is True:
                        # Condition restored (was False, now True)
                        print(f"✅ RESTORED: {state.procedure} - {state.task_object} - condition '{condition_func_name}' satisfied again!")
                        fsm_worker.condition_restored_signal.emit(state, condition_func_name)

    def on_start(self):
        print("Action: Starting FSM...")
        time.sleep(3)  # Simulate some startup delay

    # Ingescape callbacks
    def signal_handler(self, signal_received, frame):
        print("\n", signal.strsignal(signal_received), sep="")
        self.is_interrupted = True

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
        self.impulsion_count += 1
        print(f"Impulsion count: {self.impulsion_count}")
        igs.info(f"Input {name} written")
        igs.output_set_impulsion("impulsion")

    def bool_input_callback(self, io_type, name, value_type, value, my_data):
        igs.info(f"Input {name} written to {value}")
        if name == "On_Off":
            self.is_on_off[0] = value
        agent_object = my_data
        assert isinstance(agent_object, Echo)

    def integer_input_callback(self, io_type, name, value_type, value, my_data):
        igs.info(f"Input {name} written to {value}")
        agent_object = my_data
        assert isinstance(agent_object, Echo)

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
        elif name == "n1_match_bug":
            agent_object.n1_match_bug_i = value
        elif name == "e1_n1_percent":
            agent_object.e1_n1_percent_i = value
        elif name == "e2_n1_percent":
            agent_object.e2_n1_percent_i = value
        elif name == "slip":
            agent_object.slip_i = value
        elif name == "engine_fire_l":
            agent_object.engine_fire_l_i = value
        elif name == "engine_fire_r":
            agent_object.engine_fire_r_i = value
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
        elif name == "trim_rudder":
            agent_object.trim_rudder_i = value
        elif name == "cabin_altitude":
            agent_object.cabin_altitude_i = value
        
        # EVENT-DRIVEN CONDITION MONITORING
        # Check if this input affects any monitored conditions
        if name in self.input_to_conditions:
            affected_condition_names = self.input_to_conditions[name]
            self.check_affected_conditions(name, value, affected_condition_names)

    def string_input_callback(self, io_type, name, value_type, value, my_data):
        igs.info(f"Input {name} written to {value}")
        agent_object = my_data
        assert isinstance(agent_object, Echo)

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
        igs.output_create("altimeter_setting", igs.DOUBLE_T, None)  # inHg * 1000
        igs.output_create("trim_rudder", igs.DOUBLE_T, None)  # -1.0 to 1.0 but can go beyond that programmatically

        igs.input_create("On_Off", igs.BOOL_T, None)
        igs.input_create("airspeed", igs.DOUBLE_T, None)
        igs.input_create("pitch", igs.DOUBLE_T, None)
        igs.input_create("roll", igs.DOUBLE_T, None)
        igs.input_create("heading", igs.DOUBLE_T, None)
        igs.input_create("vertical_speed", igs.DOUBLE_T, None)
        igs.input_create("altitude", igs.DOUBLE_T, None)
        igs.input_create("control_throttle", igs.DOUBLE_T, None)
        igs.input_create("control_flaps", igs.DOUBLE_T, None)
        igs.input_create("control_gear", igs.DOUBLE_T, None)
        igs.input_create("speed_brakes", igs.DOUBLE_T, None)
        igs.input_create("park_brake", igs.DOUBLE_T, None)
        igs.input_create("l_throttle", igs.DOUBLE_T, None)
        igs.input_create("r_throttle", igs.DOUBLE_T, None)
        igs.input_create("n1_match_bug", igs.DOUBLE_T, None)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.input_create("e1_n1_percent", igs.DOUBLE_T, None)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.input_create("e2_n1_percent", igs.DOUBLE_T, None)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.input_create("slip", igs.DOUBLE_T, None)  # positive is right, negative is left
        igs.input_create("engine_fire_l", igs.DOUBLE_T, None)  # [0, 0] first means E1, second means E2
        igs.input_create("engine_fire_r", igs.DOUBLE_T, None)  # [0, 0] first means E1, second means E2
        igs.input_create("pax_safety", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("master_warning", igs.DOUBLE_T, None)  # readonly 0 is off, 1 is on
        igs.input_create("master_caution", igs.DOUBLE_T, None)  # readonly 0 is off, 1 is on
        igs.input_create("flight_director", igs.DOUBLE_T, None)  # Not sure how to set FD up using a comm
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

        igs.observe_input("On_Off", self.bool_input_callback, self.agent)
        igs.observe_input("airspeed", self.double_input_callback, self.agent)
        igs.observe_input("pitch", self.double_input_callback, self.agent)
        igs.observe_input("roll", self.double_input_callback, self.agent)
        igs.observe_input("heading", self.double_input_callback, self.agent)
        igs.observe_input("vertical_speed", self.double_input_callback, self.agent)
        igs.observe_input("altitude", self.double_input_callback, self.agent)
        igs.observe_input("control_throttle", self.double_input_callback, self.agent)
        igs.observe_input("control_flaps", self.double_input_callback, self.agent)
        igs.observe_input("control_gear", self.double_input_callback, self.agent)
        igs.observe_input("speed_brakes", self.double_input_callback, self.agent)
        igs.observe_input("park_brake", self.double_input_callback, self.agent)
        igs.observe_input("l_throttle", self.double_input_callback, self.agent)
        igs.observe_input("r_throttle", self.double_input_callback, self.agent)
        igs.observe_input("n1_match_bug", self.double_input_callback, self.agent)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.observe_input("e1_n1_percent", self.double_input_callback, self.agent)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.observe_input("e2_n1_percent", self.double_input_callback, self.agent)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.observe_input("slip", self.double_input_callback, self.agent)  # positive is right, negative is left
        igs.observe_input("engine_fire_l", self.double_input_callback, self.agent)  
        igs.observe_input("engine_fire_r", self.double_input_callback, self.agent)  
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

        igs.log_set_console(True)
        igs.log_set_console_level(igs.LOG_INFO)
        igs.start_with_device(self.device, self.port)

    def set_tts_completion_event(self, event):
        """Set the threading.Event used to track TTS completion"""
        self.tts_completion_event = event

    def on_speak_action(self, speak_message=None, sleep=True):
        print(f"Action: {self.fsm.current_state}")
        if speak_message:
            speak_wait(speak_message)
            # Return True to indicate this was a speech action
            return True
        return False
    
    def takeoff_throttles_action_dev_mode(self):
        print("will set Throttle to TOGA (1.0) in dev mode.")
        igs.output_set_double("autopilot_state", 1.0)  # Set throttle to TOGA (1.0)
        print("Throttle set to TOGA (1.0).")
    
    def trim_action(self):
        if self.engine_failed_side == "Left":
            while not self.is_slip_skid_centered():
                current_trim = self.agent.trim_rudder_i if self.agent.trim_rudder_i is not None else 0.0
                print(f"Current rudder trim: {current_trim}, adjusting...")
                igs.output_set_double("trim_rudder", current_trim + 0.1)  # Trim right
                time.sleep(1)  # Small delay to allow for trim adjustment
        elif self.engine_failed_side == "Right":
            while not self.is_slip_skid_centered():
                current_trim = self.agent.trim_rudder_i if self.agent.trim_rudder_i is not None else 0.0
                print(f"Current rudder trim: {current_trim}, adjusting...")
                igs.output_set_double("trim_rudder", current_trim - 0.1)  # Trim left
                time.sleep(1)  # Small delay to allow for trim adjustment

    def check_slip_skid_action(self):
        if not self.is_slip_skid_centered():
            self.alertRequested.emit("Slip/Skid indicator is not centered!", "red")
    
    def dummy_action(self):
        print(f"Dummy action executed for {self.fsm.current_state}.")
    
    def check_electrical_load_action(self):
        if not self.is_electrical_load_under_limit():
            self.alertRequested.emit("Electrical load is above 300 amps", "red")

# Example usage
if __name__ == "__main__":
    agent = TarsAgent()
    agent.start()