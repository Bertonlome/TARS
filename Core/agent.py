import time
import signal
from pathlib import Path
from Core.echo import *
from Core.fsm import FiniteStateMachine, State, Transition
from Core.tts import speak_wait
import csv

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
class TarsAgent:
    def __init__(self, agent_name="TARS Agent", device="wlp0s20f3", port=5670, verbose=False):
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
        
        # TTS completion event - will be set by MainWindow
        self.tts_completion_event = None
        
        # Reference to main window - will be set by MainWindow for countdown synchronization
        self.main_window = None

        # Load task definitions with role allocations
        allocation_csv_path = Path(__file__).parent / "briefing_export_HIGH_LOA.csv"        
        # Create states from allocation CSV
        self.states = self.create_states_from_csv(allocation_csv_path)
        idle_key = ("IDLE", "Idle", "WAITING")
        finished_key = ("FINISHED", "Finished", "COMPLETED")
        self.fsm = FiniteStateMachine(self.states[idle_key])

        # BEFORE TAKEOFF Procedure
        self.fsm.add_transition(Transition(
            self.states[("IDLE", "Idle", "WAITING")], 
            self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")], 
            self.is_started, 
            lambda: self.on_speak_action("Starting before takeoff procedure")))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "Takeoff clearance", "CONFIRM")], 
            self.states[("BEFORE TAKEOFF", "Pitot-Static Switch", "PITOT-STATIC")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Pitot-static set to pitot-static")))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "Pitot-Static Switch", "PITOT-STATIC")], 
            self.states[("BEFORE TAKEOFF", "ENGINE ANTI-ICE Switches", "AS REQUIRED")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Engine anti-ice switches set as required")))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "ENGINE ANTI-ICE Switches", "AS REQUIRED")], 
            self.states[("BEFORE TAKEOFF", "WINDSHIELD ANTI-ICE Switches", "AS REQUIRED")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Windshield anti-ice switches set as required")))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "WINDSHIELD ANTI-ICE Switches", "AS REQUIRED")], 
            self.states[("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "PAX SAFETY Switch", "PAX SAFETY")], 
            self.states[("BEFORE TAKEOFF", "LANDING Light Switch", "AS DESIRED")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "LANDING Light Switch", "AS DESIRED")], 
            self.states[("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "ANTI-COLL Light Switch", "ON")], 
            self.states[("BEFORE TAKEOFF", "Radar", "AS REQUIRED")], 
            self.allow_transition, 
            self.dummy_action))
        
        # LINE-UP AND HOLD Procedure
        self.fsm.add_transition(Transition(
            self.states[("BEFORE TAKEOFF", "Radar", "AS REQUIRED")], 
            self.states[("LINE-UP AND HOLD", "Runway centerline", "ALIGN")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("LINE-UP AND HOLD", "Runway centerline", "ALIGN")], 
            self.states[("LINE-UP AND HOLD", "Winds", "CHECK")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Wind report, wind calm, zero two six degrees at three knots")))
        
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
            lambda: self.on_speak_action("C A S is clear")))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "CAS", "CHECK CLEAR")], 
            self.states[("TAKEOFF", "\"Set thrust\"", "ANNOUNCE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Set thrust\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "THROTTLES", "TO Detent")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "THROTTLES", "TO Detent")], 
            self.states[("TAKEOFF", "FADEC bug", "CHECK TO")], 
            self.is_thrust_sensed, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "FADEC bug", "CHECK TO")], 
            self.states[("TAKEOFF", "Engine spool", "CHECK EVEN")], 
            self.is_fadec_bug_to, 
            self.dummy_action))
        
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
            self.is_brake_released_sensed, 
            lambda: self.on_speak_action("Airspeed's alive")))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Airspeed's alive\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")], 
            self.is_airspeed_alive, 
            lambda: self.on_speak_action("seventy knots")))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"70 kts\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")], 
            self.is_seventy_kts, 
            lambda: self.on_speak_action("V one")))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"V1\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")], 
            self.is_v_one, 
            lambda: self.on_speak_action("Rotate")))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Rotate\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "Elevator Control", "ROTATE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Elevator Control", "ROTATE")], 
            self.states[("TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            self.is_v_rotate, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            self.states[("TAKEOFF", "Slip/Skid", "CHECK")], 
            self.is_pitch_maintained, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Slip/Skid", "CHECK")], 
            self.states[("TAKEOFF", "Climb rate", "CHECK POSITIVE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "Climb rate", "CHECK POSITIVE")], 
            self.states[("TAKEOFF", "\"Positive rate, gear up\"", "ANNOUNCE")], 
            self.is_positive_rate, 
            lambda: self.on_speak_action("Positive rate, gear up")))
        
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "\"Positive rate, gear up\"", "ANNOUNCE")], 
            self.states[("TAKEOFF", "LANDING GEAR", "UP")], 
            self.allow_transition, 
            self.dummy_action))
        
        # Branch: Normal path to AFTER TAKEOFF
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "LANDING GEAR", "UP")], 
            self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")], 
            self.is_400_ft, 
            self.dummy_action))
        
        # Branch: Emergency path - ENGINE FAILURE DURING TAKEOFF
        self.fsm.add_transition(Transition(
            self.states[("TAKEOFF", "LANDING GEAR", "UP")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "APPLY")], 
            self.is_alarm, 
            lambda: self.on_speak_action("Engine failure detected")))
        
        # ENG FAILURE DURING TAKEOFF transitions
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "APPLY")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "TRIM")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Rudder", "TRIM")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Alarm", "ANNOUNCE")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Alarm Engine fire, low oil pressure")))
        
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
            self.is_master_warning_reset, 
            lambda: self.on_speak_action("Flight Director on, takeoff mode")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Flight Director", "SET TO MODE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Pitch", "MAINTAIN 10°")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "LANDING GEAR", "UP")], 
            self.allow_transition, 
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
            lambda: self.on_speak_action("V two, speed mode FLC, heading mode can be engaged")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "\"Speed mode FLC V2, heading mode\"", "ANNOUNCE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET SPD MODE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "SET HDG MODE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "CONTACT")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "LISTEN")], 
            self.is_acked, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "LISTEN")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "READBACK")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "ATC", "READBACK")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 700ft AGL")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 700ft AGL")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "\"700ft, engage autopilot\"", "ANNOUNCE")], 
            self.is_ap_altitude, 
            lambda: self.on_speak_action("Seven hundred feet, autopilot ready to engage")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "\"700ft, engage autopilot\"", "ANNOUNCE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Autopilot", "ENGAGE")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 1500ft AGL")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Altitude", "CHECK 1500ft AGL")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2+10")], 
            self.is_v2_plus_12, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Airspeed", "CHECK V2+10")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "Obstacles", "CHECK Clear")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENG FAILURE DURING TAKEOFF", "Obstacles", "CHECK Clear")], 
            self.states[("ENG FAILURE DURING TAKEOFF", "\"Retract flaps\"", "Announce")], 
            self.allow_transition, 
            self.dummy_action))
        
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
            lambda: self.on_speak_action("Affected thrust lever, confirm and idle")))
        
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
            lambda: self.on_speak_action("Chronometer started, fifteen seconds to check light")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"TOP\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "Chrono", "START")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Chrono", "START")], 
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 15s")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 15s")], 
            self.states[("ENGINE FIRE", "Illuminated ENGINE FIRE Switch", "LIFT COVER AND PUSH")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Engine fire switch, lift cover and push")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Illuminated ENGINE FIRE Switch", "LIFT COVER AND PUSH")], 
            self.states[("ENGINE FIRE", "Checklist", "ORDER START")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Checklist", "ORDER START")], 
            self.states[("ENGINE FIRE", "Radio", "ALLOCATE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Radio", "ALLOCATE")], 
            self.states[("ENGINE FIRE", "Checklist", "RETRIEVE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Checklist", "RETRIEVE")], 
            self.states[("ENGINE FIRE", "Immediate Action Item", "CHECK DONE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Immediate Action Item", "CHECK DONE")], 
            self.states[("ENGINE FIRE", "\"Affected thrust lever, confirm and cutoff\"", "ANNOUNCE")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Affected thrust lever, confirm and cutoff")))
        
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
            lambda: self.on_speak_action("Affected engine fuel boost, confirm off then norm")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"Affected engine fuel boost confirm off then norm\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "\"off then norm\"", "ANNOUNCE")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Fuel boost off")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "\"off then norm\"", "ANNOUNCE")], 
            self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "OFF")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "OFF")], 
            self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "NORM")], 
            self.is_fuel_boost_off, 
            lambda: self.on_speak_action("Fuel boost norm")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "FUEL BOOST Switch (affected side)", "NORM")], 
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 30s")], 
            self.is_fuel_boost_norm, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Engine FIRE LIGHT", "CHECK ON AFTER 30s")], 
            self.states[("ENGINE FIRE", "\"30 seconds, light remains on, bottle discharge\"", "ANNOUNCE")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Thirty seconds light remains on, bottle discharge")))
        
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
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Rotary Test", "FIRE WARN")], 
            self.states[("ENGINE FIRE", "Engine fire lights", "Check both illuminate")], 
            self.is_test_knob_turned, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FIRE", "Engine fire lights", "Check both illuminate")], 
            self.states[("ENGINE FIRE", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Start checklist : Engine Failure/Precautionary Shutdown")))
        
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
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "ATC", "REQUEST VECTOR")], 
            self.states[("DECLARE EMERGENCY", "ATC", "LISTEN")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "ATC", "LISTEN")], 
            self.states[("DECLARE EMERGENCY", "ATC", "READBACK")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "ATC", "READBACK")], 
            self.states[("DECLARE EMERGENCY", "Heading", "SET ACCORDINGLY")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "Heading", "SET ACCORDINGLY")], 
            self.states[("DECLARE EMERGENCY", "FLC", "SET ACCORDINGLY")], 
            self.allow_transition, 
            self.dummy_action))
        
        # Continue to AFTER TAKEOFF from DECLARE EMERGENCY
        self.fsm.add_transition(Transition(
            self.states[("DECLARE EMERGENCY", "FLC", "SET ACCORDINGLY")], 
            self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")], 
            self.allow_transition, 
            self.dummy_action))
        
        # AFTER TAKEOFF transitions (normal path)
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Checklist", "ORDER START")], 
            self.states[("AFTER TAKEOFF", "Checklist", "RETRIEVE")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Checklist", "RETRIEVE")], 
            self.states[("AFTER TAKEOFF", "LANDING GEAR Handle", "UP")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "LANDING GEAR Handle", "UP")], 
            self.states[("AFTER TAKEOFF", "Airspeed", "CHECK V2 + 12")], 
            self.is_gear_up, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Airspeed", "CHECK V2 + 12")], 
            self.states[("AFTER TAKEOFF", "Obstacles", "CHECK CLEAR")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Obstacles", "CHECK CLEAR")], 
            self.states[("AFTER TAKEOFF", "FLAP Handle", "UP")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "FLAP Handle", "UP")], 
            self.states[("AFTER TAKEOFF", "THROTTLES", "CLB Detent")], 
            self.is_flaps_retracted, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "THROTTLES", "CLB Detent")], 
            self.states[("AFTER TAKEOFF", "Yaw Damper", "AS DESIRED")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Yaw Damper", "AS DESIRED")], 
            self.states[("AFTER TAKEOFF", "Anti-Ice/Deice Systems", "AS REQUIRED")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Anti-Ice/Deice Systems", "AS REQUIRED")], 
            self.states[("AFTER TAKEOFF", "PAX SAFETY Switch", "AS REQUIRED")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "PAX SAFETY Switch", "AS REQUIRED")], 
            self.states[("AFTER TAKEOFF", "LANDING Light Switch", "AS REQUIRED")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "LANDING Light Switch", "AS REQUIRED")], 
            self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Pressurization", "CHECK")], 
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Altimeter set to standard pressure")))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "SET STD")], 
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "CROSSCHECK")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Altimeters (transition altitude)", "CROSSCHECK")], 
            self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")], 
            self.allow_transition, 
            self.dummy_action))
        
        # Branch: Normal completion or continue to ENGINE FAILURE/PRECAUTIONARY SHUTDOWN
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Checklist", "ANNOUNCE COMPLETED")], 
            self.states[("AFTER TAKEOFF", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")], 
            self.is_failed, 
            lambda: self.on_speak_action("Start checklist: Engine Failure/Precautionary Shutdown Procedure and Checklist")))
        
        # ENGINE FAILURE/PRECAUTIONARY SHUTDOWN transitions
        self.fsm.add_transition(Transition(
            self.states[("AFTER TAKEOFF", "Next Checklist", "ENGINE FAILURE/PRECAUTIONARY SHUTDOWN")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Checklist", "ORDER START")], 
            self.allow_transition, 
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
            lambda: self.on_speak_action("Affected thrust lever, confirm and cutoff")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Throttle (affected engine)", "CUTOFF")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "CAUTION text", "READ")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "CAUTION text", "READ")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "GEN Switch (affected side)", "OFF")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Gen switch affected side off")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "GEN Switch (affected side)", "OFF")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "IGNITION switch (affected side)", "NORM")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Ignition switch affected side norm")))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "IGNITION switch (affected side)", "NORM")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Electrical Load", "REDUCE as required (<= 300A)")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Electrical Load", "REDUCE as required (<= 300A)")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Fuel TRANSFER Knob", "AS REQUIRED")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Fuel TRANSFER Knob", "AS REQUIRED")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Verify ENGINE FIRE Switch (affected side)", "Is pushed")], 
            self.allow_transition, 
            self.dummy_action))
        
        self.fsm.add_transition(Transition(
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Verify ENGINE FIRE Switch (affected side)", "Is pushed")], 
            self.states[("ENGINE FAILURE/PRECAUTIONARY SHUTDOWN", "Next checklist", "SINGLE-ENGINE APPROACH AND LANDING")], 
            self.allow_transition, 
            lambda: self.on_speak_action("Current checklist completed, next: single engine approach and landing")))
        
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
            self.is_not_failed, 
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
                    delay_before_action = float(row.get('Time to Initiate Action', 0) or 0)
                    delay_after_action = float(row.get('Time after Ending Action', 0) or 0)
                    callout = row.get('Callout', '').strip()
                    
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
                        callout=callout
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
    
    def is_started(self):
        if self.is_on_off[0]:
            return True
        return False
    
    def allow_transition(self):
        """Always returns True - timing is managed by main.py using delay_before_action and delay_after_action"""
        return True
    
    def is_acked(self):
        if self.task_done_human[0]:
            self.task_done_human[0] = False
            return True
        return False

    def is_thrust_sensed(self):
        if self.agent.control_throttle_i is not None and self.agent.control_throttle_i == 1:
            return True
        return False
    
    def is_engine_spool_even(self):
        if self.agent.e1_n1_percent_i is not None and self.agent.e2_n1_percent_i is not None:
            if self.agent.e1_n1_percent_i > 50 and self.agent.e2_n1_percent_i > 50:  # Both engines above idle
                diff = abs(self.agent.e1_n1_percent_i - self.agent.e2_n1_percent_i)
                if diff <= 5:  # Assuming a threshold of 5% for even spool
                    return True
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

    def is_brake_released_sensed(self):
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

    def is_positive_rate(self):
        if self.agent.vertical_speed_i is not None and self.agent.vertical_speed_i > 100:
            return True
        return False
    
    def is_400_ft(self):
        if self.agent.altitude_i is not None and self.agent.altitude_i >= 400:
            return True
        return False

    def is_gear_up(self):
        if self.agent.control_gear_i is not None and self.agent.control_gear_i == 0:
            return True
        return False

    def is_alarm(self):
        if self.agent.master_warning_i is not None and self.agent.master_warning_i == 1:
            return True
        return False
    
    def is_failed(self):
        if self.agent.e1_n1_percent_i is not None and self.agent.e1_n1_percent_i < 50:
            return True
        if self.agent.e2_n1_percent_i is not None and self.agent.e2_n1_percent_i < 50:
            return True
        return False

    def is_not_failed(self):
        if self.agent.e1_n1_percent_i is not None and self.agent.e1_n1_percent_i >= 50:
            if self.agent.e2_n1_percent_i is not None and self.agent.e2_n1_percent_i >= 50:
                return True
        return False
    
    def is_master_warning_reset(self):
        if self.agent.master_warning_i is not None and self.agent.master_warning_i == 0:
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
    
    def is_v2_plus_12(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 132:
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
        print(f"Checking if fuel boost is off - Left: {self.agent.fuel_boost_l_i}, Right: {self.agent.fuel_boost_r_i}")
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
        if self.agent.control_throttle_i is not None and self.agent.control_throttle_i > 0.5:
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
    
    def dummy_action(self):
        print(f"Dummy action executed for {self.fsm.current_state}.")

# Example usage
if __name__ == "__main__":
    agent = TarsAgent()
    agent.start()