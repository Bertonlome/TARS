import time
import signal
from Core.echo import *
from Core.fsm import FiniteStateMachine, State, Transition
from Core.tts import speak
import csv

# Agent Class
class TarsAgent:
    def __init__(self, agent_name="TARS Agent", device="wlo1", port=5670, verbose=False):
        self.agent_name = agent_name
        self.device = device
        self.port = port
        self.verbose = verbose
        self.is_interrupted = False
        self.impulsion_count = 0

        # FSM setup
        self.idle = State("Idle")
        self.confirm_takeoff_clearance = State("Confirm takeoff clearance")
        self.ali_run_cen = State("Align with runway centerline")
        self.check_winds = State("Check winds")
        self.hold_brakes = State("Hold brakes")
        self.check_cas_clear = State("Check CAS clear")
        self.say_set_thrust = State("\"Set thrust\"")
        self.set_thrust = State("Set thrust")
        self.check_fadec_bug_to = State("Check FADEC bug TO")
        self.check_engine_spool_evenly = State("Check engine spool evenly")
        self.thrust_set = State("\"Thrust set\"")
        self.check_n1_percent = State("Check N1% matches command bug")
        self.release_brakes = State("Release brakes")
        self.airspeed_alive = State("\"Airspeed's alive\"")
        self.seventy_kts = State("\"70 kts\"")
        self.v1 = State("\"V1\"")
        self.rotate = State("Rotate")
        self.maintain_pitch = State("Maintain 10deg pitch")
        self.scan_slip_skid = State("Scan slip/skid indicator")
        self.check_positive_rate = State("Check positive rate")
        self.positive_rate_gear_up = State("\"Positive rate, gear up\"")
        self.gear_up = State("Gear up")
        self.apply_rudder = State("Apply rudder")
        self.trim_rudder = State("Trim rudder")
        self.announce_alarm = State("Announce alarm")
        self.reset_master_warning = State("Reset Master Warning")
        self.set_fd_to_mode = State("Set FD TO Mode")
        self.maintain_pitch_after_fd = State("Maintain 10deg pitch after FD")
        self.check_lg_up = State("Check L/G up")
        self.check_airspeed_v2 = State("Check Airspeed V2")
        self.say_speed_mode_flc_v2_heading_mode = State("\"Speed mode FLC V2 heading mode\"")
        self.speed_mode_flc_v2_heading_mode = State("Speed mode FLC V2, heading mode")
        self.contact_atc_emergency = State("Contact ATC to announce emergency")
        self.listen_atc = State("Listen ATC")
        self.seven_hundred_ft_engage_ap = State("\"700ft, engage autopilot\"")
        self.engage_autopilot = State("Engage autopilot")
        self.check_v2_plus_twelve = State("Check V2+12")
        self.say_retract_flaps = State("\"Retract flaps\"")
        self.retract_flaps = State("Retract flaps")
        self.affected_thrust_lever_confirm_idle = State("\"Affected thrust lever, confirm and idle\"")
        self.throttle_affected_idle = State("Throttle affected idle")
        self.top = State("\"TOP\"")
        self.start_chrono = State("Start chrono")
        self.check_light_after_15_seconds = State("Check light after 15 seconds")
        self.eng_fire_switch_lift_cover_push = State("ENG FIRE switch lift cover and push")
        self.affected_thrust_lever_confirm_cutoff = State("\"Affected thrust lever, confirm and cutoff\"")
        self.cutoff = State("\"cutoff\"")
        self.affected_engine_fuel_boost_confirm_off_then_norm = State("\"Affected engine fuel boost confirm off then norm\"")
        self.off_then_norm = State("\"off then norm\"")
        self.fuel_boost_off = State("fuel boost off")
        self.fuel_boost_norm = State("fuel boost norm")
        self.check_light_after_30_seconds = State("Check light after 30 seconds")
        self.thirty_seconds_light_remains_on_bottle_discharge = State("\"30 seconds, light remains on, bottle discharge\"")
        self.discharge = State("\"discharge\"")
        self.illuminated_bottle_armed_switch_push = State("Illuminated bottle armed switch push")
        self.turn_rotary_test_knob = State("Turn rotary test knob")
        self.check_engine_fire_lights = State("Check engine fire lights both illuminate")
        self.order_start_checklist = State("Order start checklist")
        self.allocate_radio = State("Allocate radio")
        self.retrieve_checklist = State("Retrieve checklist")
        self.check_immediate_action_items_done = State("Check immediate action items done")
        self.immediate_action_checked = State("\"immediate action checked, Current checklist completed, Checklist to refer next: precautionary shutdown\"")
        self.contact_atc_vector = State("Contact ATC to announce emergency and request vector")
        self.listen_atc_vector = State("Listen ATC")
        self.acknowledge_transmission = State("Acknowledge transmission")
        self.set_heading_accordingly = State("Set heading accordingly")
        self.set_flc_accordingly = State("Set FLC accordingly")
        self.announce_start_checklist = State("Announce start checklist")
        self.retrieve_checklist_start = State("Retrieve checklist")
        self.landing_gear_up = State("Landing gear up")
        self.flap_handle_up = State("Flap handle up")
        self.throttles_clb_detent = State("Throttles CLB detent")
        self.yaw_damper_as_desired = State("Yaw damper as desired")
        self.deice_as_required = State("Deice as required")
        self.pax_safety_switch_as_required = State("Pax safety switch as required")
        self.pressurization_check = State("Pressurization check")
        self.alti_set_std = State("Alti set STD")
        self.crosscheck_alti = State("Crosscheck alti")
        self.announce_checklist_completed = State("Announce checklist completed")
        self.announce_start_checklist_retrieve = State("Announce start checklist")
        self.retrieve_checklist_start_checklist = State("Retrieve checklist")
        self.throttle_affected_engine_cutoff = State("Throttle affected engine cutoff")
        self.caution_text_readout = State("Caution text readout")
        self.gen_switch_affected_side_off = State("Gen switch affected side OFF")
        self.ignition_switch_affected_side_norm = State("Ignition switch affected side NORM")
        self.electrical_load_reduce_as_required = State("Electrical load reduce as required")
        self.fuel_transfer_knob_as_required = State("Fuel transfer knob as required")
        self.verify_engine_fire_switch_affected_side = State("Verify engine fire switch affected side is pushed")
        self.announce_current_checklist_completed = State("Announce current checklist completed, Checklist to refer next: single engine approach and landing")
        self.finished = State("Finished")

        #conditions
        self.should_run = [False]
        self.should_finish = [False]

        self.fsm = FiniteStateMachine(self.idle)
        self.fsm.add_transition(Transition(self.idle, self.confirm_takeoff_clearance, self.can_start, self.on_confirm_takeoff_clearance))
        self.fsm.add_transition(Transition(self.confirm_takeoff_clearance, self.ali_run_cen, self.can_start, self.on_ali_run_cen))
        self.fsm.add_transition(Transition(self.ali_run_cen, self.check_winds, self.can_start, self.on_check_winds))
        self.fsm.add_transition(Transition(self.check_winds, self.hold_brakes, self.can_start, self.on_hold_brakes))
        self.fsm.add_transition(Transition(self.hold_brakes, self.check_cas_clear, self.can_start, self.on_check_cas_clear))
        self.fsm.add_transition(Transition(self.check_cas_clear, self.say_set_thrust, self.can_start, self.on_set_thrust))
        self.fsm.add_transition(Transition(self.say_set_thrust, self.set_thrust, self.can_start, self.on_set_thrust))
        self.fsm.add_transition(Transition(self.set_thrust, self.check_fadec_bug_to, self.can_start, self.on_check_fadec_bug_to))
        self.fsm.add_transition(Transition(self.check_fadec_bug_to, self.check_engine_spool_evenly, self.can_start, self.on_check_engine_spool_evenly))
        self.fsm.add_transition(Transition(self.check_engine_spool_evenly, self.thrust_set, self.can_start, self.on_thrust_set))
        self.fsm.add_transition(Transition(self.thrust_set, self.check_n1_percent, self.can_start, self.on_check_n1_percent))
        self.fsm.add_transition(Transition(self.check_n1_percent, self.release_brakes, self.can_start, self.on_release_brakes))
        self.fsm.add_transition(Transition(self.release_brakes, self.airspeed_alive, self.can_start, self.on_airspeed_alive))
        self.fsm.add_transition(Transition(self.airspeed_alive, self.seventy_kts, self.can_start, self.on_seventy_kts))
        self.fsm.add_transition(Transition(self.seventy_kts, self.v1, self.can_start, self.on_v1))
        self.fsm.add_transition(Transition(self.v1, self.rotate, self.can_start, self.on_rotate))
        self.fsm.add_transition(Transition(self.rotate, self.maintain_pitch, self.can_start, self.on_maintain_pitch))
        self.fsm.add_transition(Transition(self.maintain_pitch, self.scan_slip_skid, self.can_start, self.on_scan_slip_skid))
        self.fsm.add_transition(Transition(self.scan_slip_skid, self.check_positive_rate, self.can_start, self.on_check_positive_rate))
        self.fsm.add_transition(Transition(self.check_positive_rate, self.positive_rate_gear_up, self.can_start, self.on_positive_rate_gear_up))
        self.fsm.add_transition(Transition(self.positive_rate_gear_up, self.gear_up, self.can_start, self.on_gear_up))
        self.fsm.add_transition(Transition(self.gear_up, self.apply_rudder, self.can_start, self.on_apply_rudder))
        self.fsm.add_transition(Transition(self.apply_rudder, self.trim_rudder, self.can_start, self.on_trim_rudder))
        self.fsm.add_transition(Transition(self.trim_rudder, self.announce_alarm, self.can_start, self.on_announce_alarm))
        self.fsm.add_transition(Transition(self.announce_alarm, self.reset_master_warning, self.can_start, self.on_reset_master_warning))
        self.fsm.add_transition(Transition(self.reset_master_warning, self.set_fd_to_mode, self.can_start, self.on_set_fd_to_mode))
        self.fsm.add_transition(Transition(self.set_fd_to_mode, self.maintain_pitch_after_fd, self.can_start, self.on_maintain_pitch_after_fd))
        self.fsm.add_transition(Transition(self.maintain_pitch_after_fd, self.check_lg_up, self.can_start, self.on_check_lg_up))
        self.fsm.add_transition(Transition(self.check_lg_up, self.check_airspeed_v2, self.can_start, self.on_check_airspeed_v2))
        self.fsm.add_transition(Transition(self.check_airspeed_v2, self.say_speed_mode_flc_v2_heading_mode, self.can_start, self.on_speed_mode_flc_v2_heading_mode))
        self.fsm.add_transition(Transition(self.say_speed_mode_flc_v2_heading_mode, self.speed_mode_flc_v2_heading_mode, self.can_start, self.on_speed_mode_flc_v2_heading_mode))
        self.fsm.add_transition(Transition(self.speed_mode_flc_v2_heading_mode, self.contact_atc_emergency, self.can_start, self.on_contact_atc_emergency))
        self.fsm.add_transition(Transition(self.contact_atc_emergency, self.listen_atc, self.can_start, self.on_listen_atc))
        self.fsm.add_transition(Transition(self.listen_atc, self.seven_hundred_ft_engage_ap, self.can_start, self.on_seven_hundred_ft_engage_ap))
        self.fsm.add_transition(Transition(self.seven_hundred_ft_engage_ap, self.engage_autopilot, self.can_start, self.on_engage_autopilot))
        self.fsm.add_transition(Transition(self.engage_autopilot, self.check_v2_plus_twelve, self.can_start, self.on_check_v2_plus_twelve))
        self.fsm.add_transition(Transition(self.check_v2_plus_twelve, self.say_retract_flaps, self.can_start, self.on_say_retract_flaps))
        self.fsm.add_transition(Transition(self.say_retract_flaps, self.retract_flaps, self.can_start, self.on_retract_flaps))
        self.fsm.add_transition(Transition(self.retract_flaps, self.affected_thrust_lever_confirm_idle, self.can_start, self.on_affected_thrust_lever_confirm_idle))
        self.fsm.add_transition(Transition(self.affected_thrust_lever_confirm_idle, self.throttle_affected_idle, self.can_start, self.on_throttle_affected_idle))
        self.fsm.add_transition(Transition(self.throttle_affected_idle, self.top, self.can_start, self.on_top))
        self.fsm.add_transition(Transition(self.top, self.start_chrono, self.can_start, self.on_start_chrono))
        self.fsm.add_transition(Transition(self.start_chrono, self.check_light_after_15_seconds, self.can_start, self.on_check_light_after_15_seconds))
        self.fsm.add_transition(Transition(self.check_light_after_15_seconds, self.eng_fire_switch_lift_cover_push, self.can_start, self.on_eng_fire_switch_lift_cover_push))
        self.fsm.add_transition(Transition(self.eng_fire_switch_lift_cover_push, self.affected_thrust_lever_confirm_cutoff, self.can_start, self.on_affected_thrust_lever_confirm_cutoff))
        self.fsm.add_transition(Transition(self.affected_thrust_lever_confirm_cutoff, self.cutoff, self.can_start, self.on_cutoff))
        self.fsm.add_transition(Transition(self.cutoff, self.affected_engine_fuel_boost_confirm_off_then_norm, self.can_start, self.on_affected_engine_fuel_boost_confirm_off_then_norm))
        self.fsm.add_transition(Transition(self.affected_engine_fuel_boost_confirm_off_then_norm, self.fuel_boost_off, self.can_start, self.on_fuel_boost_off))
        self.fsm.add_transition(Transition(self.fuel_boost_off, self.fuel_boost_norm, self.can_start, self.on_fuel_boost_norm))
        self.fsm.add_transition(Transition(self.fuel_boost_norm, self.check_light_after_30_seconds, self.can_start, self.on_check_light_after_30_seconds))
        self.fsm.add_transition(Transition(self.check_light_after_30_seconds, self.thirty_seconds_light_remains_on_bottle_discharge, self.can_start, self.on_thirty_seconds_light_remains_on_bottle_discharge))
        self.fsm.add_transition(Transition(self.thirty_seconds_light_remains_on_bottle_discharge, self.discharge, self.can_start, self.on_discharge))
        self.fsm.add_transition(Transition(self.discharge, self.illuminated_bottle_armed_switch_push, self.can_start, self.on_illuminated_bottle_armed_switch_push))
        self.fsm.add_transition(Transition(self.illuminated_bottle_armed_switch_push, self.turn_rotary_test_knob, self.can_start, self.on_turn_rotary_test_knob))
        self.fsm.add_transition(Transition(self.turn_rotary_test_knob, self.check_engine_fire_lights, self.can_start, self.on_check_engine_fire_lights))
        self.fsm.add_transition(Transition(self.check_engine_fire_lights, self.order_start_checklist, self.can_start, self.on_order_start_checklist))
        self.fsm.add_transition(Transition(self.order_start_checklist, self.allocate_radio, self.can_start, self.on_allocate_radio))
        self.fsm.add_transition(Transition(self.allocate_radio, self.retrieve_checklist, self.can_start, self.on_retrieve_checklist))
        self.fsm.add_transition(Transition(self.retrieve_checklist, self.check_immediate_action_items_done, self.can_start, self.on_check_immediate_action_items_done))
        self.fsm.add_transition(Transition(self.check_immediate_action_items_done, self.immediate_action_checked, self.can_start, self.on_immediate_action_checked))
        self.fsm.add_transition(Transition(self.immediate_action_checked, self.contact_atc_vector, self.can_start, self.on_contact_atc_vector))
        self.fsm.add_transition(Transition(self.contact_atc_vector, self.listen_atc_vector, self.can_start, self.on_listen_atc_vector))
        self.fsm.add_transition(Transition(self.listen_atc_vector, self.acknowledge_transmission, self.can_start, self.on_acknowledge_transmission))
        self.fsm.add_transition(Transition(self.acknowledge_transmission, self.set_heading_accordingly, self.can_start, self.on_set_heading_accordingly))
        self.fsm.add_transition(Transition(self.set_heading_accordingly, self.set_flc_accordingly, self.can_start, self.on_set_flc_accordingly))
        self.fsm.add_transition(Transition(self.set_flc_accordingly, self.announce_start_checklist, self.can_start, self.on_announce_start_checklist))
        self.fsm.add_transition(Transition(self.announce_start_checklist, self.retrieve_checklist_start, self.can_start, self.on_retrieve_checklist_start))
        self.fsm.add_transition(Transition(self.retrieve_checklist_start, self.landing_gear_up, self.can_start, self.on_landing_gear_up))
        self.fsm.add_transition(Transition(self.landing_gear_up, self.flap_handle_up, self.can_start, self.on_flap_handle_up))
        self.fsm.add_transition(Transition(self.flap_handle_up, self.throttles_clb_detent, self.can_start, self.on_throttles_clb_detent))
        self.fsm.add_transition(Transition(self.throttles_clb_detent, self.yaw_damper_as_desired, self.can_start, self.on_yaw_damper_as_desired))
        self.fsm.add_transition(Transition(self.yaw_damper_as_desired, self.deice_as_required, self.can_start, self.on_deice_as_required))
        self.fsm.add_transition(Transition(self.deice_as_required, self.pax_safety_switch_as_required, self.can_start, self.on_pax_safety_switch_as_required))
        self.fsm.add_transition(Transition(self.pax_safety_switch_as_required, self.pressurization_check, self.can_start, self.on_pressurization_check))
        self.fsm.add_transition(Transition(self.pressurization_check, self.alti_set_std, self.can_start, self.on_alti_set_std))
        self.fsm.add_transition(Transition(self.alti_set_std, self.crosscheck_alti, self.can_start, self.on_crosscheck_alti))
        self.fsm.add_transition(Transition(self.crosscheck_alti, self.announce_checklist_completed, self.can_start, self.on_announce_checklist_completed))
        self.fsm.add_transition(Transition(self.announce_checklist_completed, self.announce_start_checklist_retrieve, self.can_start, self.on_announce_start_checklist_retrieve))
        self.fsm.add_transition(Transition(self.announce_start_checklist_retrieve, self.retrieve_checklist_start_checklist, self.can_start, self.on_retrieve_checklist_start_checklist))
        self.fsm.add_transition(Transition(self.retrieve_checklist_start_checklist, self.throttle_affected_engine_cutoff, self.can_start, self.on_throttle_affected_engine_cutoff))
        self.fsm.add_transition(Transition(self.throttle_affected_engine_cutoff, self.caution_text_readout, self.can_start, self.on_caution_text_readout))
        self.fsm.add_transition(Transition(self.caution_text_readout, self.gen_switch_affected_side_off, self.can_start, self.on_gen_switch_affected_side_off))
        self.fsm.add_transition(Transition(self.gen_switch_affected_side_off, self.ignition_switch_affected_side_norm, self.can_start, self.on_ignition_switch_affected_side_norm))
        self.fsm.add_transition(Transition(self.ignition_switch_affected_side_norm, self.electrical_load_reduce_as_required, self.can_start, self.on_electrical_load_reduce_as_required))
        self.fsm.add_transition(Transition(self.electrical_load_reduce_as_required, self.fuel_transfer_knob_as_required, self.can_start, self.on_fuel_transfer_knob_as_required))
        self.fsm.add_transition(Transition(self.fuel_transfer_knob_as_required, self.verify_engine_fire_switch_affected_side, self.can_start, self.on_verify_engine_fire_switch_affected_side))
        self.fsm.add_transition(Transition(self.verify_engine_fire_switch_affected_side, self.announce_current_checklist_completed, self.can_start, self.on_announce_current_checklist_completed))
        self.fsm.add_transition(Transition(self.announce_current_checklist_completed, self.finished, self.can_start, self.on_finished))
        
        # Echo agent
        self.agent = Echo()
        
        # load tasks from CSV
        self.tasks = self.load_tasks("Core/task_allocation.csv")
        self.current_task = self.tasks[0] if self.tasks else None

    def load_tasks(self, csv_path):
        tasks = []
        with open(csv_path, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                tasks.append(row)
        return tasks
    # FSM conditions and actions
    def can_start(self):
        return True

    def can_finish(self):
        return self.should_finish[0]

    def on_start(self):
        print("Action: Starting...")
        current_state_name = self.fsm.current_state.name
        self.current_task = next(
            (task for task in self.tasks if task.get("task_name") == current_state_name), None
        )
        if self.current_task:
            speak(f"{self.current_task['task_name']}")
        else:
            print(f"No task found for state: {current_state_name}")
        time.sleep(3)  # Simulate some startup delay

    def on_confirm_takeoff_clearance(self):
        print("Action: Confirming takeoff clearance...")
        speak("Confirming takeoff clearance")
        time.sleep(2)
    def on_ali_run_cen(self):
        print("Action: Aligning with runway centerline...")
        speak("Aligning with runway centerline")
        time.sleep(2)
    def on_check_winds(self):
        print("Action: Checking winds...")
        speak("Checking winds")
        time.sleep(2)
    def on_hold_brakes(self):
        print("Action: Holding brakes...")
        speak("Holding brakes")
        time.sleep(2)
    def on_check_cas_clear(self):
        print("Action: Checking CAS clear...")
        speak("Checking CAS clear")
        time.sleep(2)
    def on_set_thrust(self):
        print("Action: Setting thrust...")
        speak("Setting thrust")
        time.sleep(2)
    def on_check_fadec_bug_to(self):
        print("Action: Checking FADEC bug TO...")
        speak("Checking FADEC bug TO")
        time.sleep(2)
    def on_check_engine_spool_evenly(self):
        print("Action: Checking engine spool evenly...")
        speak("Checking engine spool evenly")
        time.sleep(2)
    def on_thrust_set(self):
        print("Action: Thrust set...")
        speak("Thrust set")
        time.sleep(2)
    def on_check_n1_percent(self):
        print("Action: Checking N1% matches command bug...")
        speak("Checking N1% matches command bug")
        time.sleep(2)
    def on_release_brakes(self):
        print("Action: Releasing brakes...")
        speak("Releasing brakes")
        time.sleep(2)
    def on_airspeed_alive(self):
        print("Action: Airspeed's alive...")
        speak("Airspeed's alive")
        time.sleep(2)
    def on_seventy_kts(self):
        print("Action: Seventy knots...")
        speak("Seventy knots")
        time.sleep(2)
    def on_v1(self):
        print("Action: V1...")
        speak("V1")
        time.sleep(2)
    def on_rotate(self):
        print("Action: Rotate...")
        speak("Rotate")
        time.sleep(2)
    def on_maintain_pitch(self):
        print("Action: Maintaining 10 degrees pitch...")
        speak("Maintaining 10 degrees pitch")
        time.sleep(2)
    def on_scan_slip_skid(self):
        print("Action: Scanning slip/skid indicator...")
        speak("Scanning slip/skid indicator")
        time.sleep(2)
    def on_check_positive_rate(self):
        print("Action: Checking positive rate...")
        speak("Checking positive rate")
        time.sleep(2)
    def on_positive_rate_gear_up(self):
        print("Action: Positive rate, gear up...")
        speak("Positive rate, gear up")
        time.sleep(2)
    def on_gear_up(self):
        print("Action: Gear up...")
        speak("Gear up")
        time.sleep(2)
    def on_apply_rudder(self):
        print("Action: Applying rudder...")
        speak("Applying rudder")
        time.sleep(2)
    def on_trim_rudder(self):
        print("Action: Trimming rudder...")
        speak("Trimming rudder")
        time.sleep(2)
    def on_announce_alarm(self):
        print("Action: Announcing alarm...")
        speak("Announcing alarm")
        time.sleep(2)
    def on_reset_master_warning(self):
        print("Action: Resetting Master Warning...")
        speak("Resetting Master Warning")
        time.sleep(2)
    def on_set_fd_to_mode(self):
        print("Action: Setting FD TO Mode...")
        speak("Setting FD TO Mode")
        time.sleep(2)
    def on_maintain_pitch_after_fd(self):
        print("Action: Maintaining 10 degrees pitch after FD...")
        speak("Maintaining 10 degrees pitch after FD")
        time.sleep(2)
    def on_check_lg_up(self):
        print("Action: Checking Landing Gear up...")
        speak("Checking Landing Gear up")
        time.sleep(2)
    def on_check_airspeed_v2(self): 
        print("Action: Checking Airspeed V2...")
        speak("Checking Airspeed V2")
        time.sleep(2)
    def on_speed_mode_flc_v2_heading_mode(self):
        print("Action: Speed mode FLC V2, heading mode...")
        speak("Speed mode FLC V2, heading mode")
        time.sleep(2)
    def on_contact_atc_emergency(self):
        print("Action: Contacting ATC to announce emergency...")
        speak("Contacting ATC to announce emergency")
        time.sleep(2)
    def on_listen_atc(self):
        print("Action: Listening ATC...")
        speak("Listening ATC")
        time.sleep(2)
    def on_seven_hundred_ft_engage_ap(self):
        print("Action: Seven hundred feet, engage autopilot...")
        speak("Seven hundred feet, engage autopilot")
        time.sleep(2)
    def on_engage_autopilot(self):
        print("Action: Engaging autopilot...")
        speak("Engaging autopilot")
        time.sleep(2)
    def on_check_v2_plus_twelve(self):
        print("Action: Checking V2+12...")
        speak("Checking V2+12")
        time.sleep(2)
    def on_say_retract_flaps(self):
        print("Action: Retract flaps...")
        speak("Retract flaps")
        time.sleep(2)
    def on_retract_flaps(self):
        print("Action: Retracting flaps...")
        speak("Retracting flaps")
        time.sleep(2)
    def on_affected_thrust_lever_confirm_idle(self):
        print("Action: Affected thrust lever, confirm and idle...")
        speak("Affected thrust lever, confirm and idle")
        time.sleep(2)
    def on_throttle_affected_idle(self):
        print("Action: Throttle affected idle...")
        speak("Throttle affected idle")
        time.sleep(2)
    def on_top(self):
        print("Action: TOP...")
        speak("TOP")
        time.sleep(2)
    def on_start_chrono(self):
        print("Action: Starting chrono...")
        speak("Starting chrono")
        time.sleep(2)
    def on_check_light_after_15_seconds(self):
        print("Action: Checking light after 15 seconds...")
        speak("Checking light after 15 seconds")
        time.sleep(2)
    def on_eng_fire_switch_lift_cover_push(self):
        print("Action: ENG FIRE switch lift cover and push...")
        speak("ENG FIRE switch lift cover and push")
        time.sleep(2)
    def on_affected_thrust_lever_confirm_cutoff(self):
        print("Action: Affected thrust lever, confirm and cutoff...")
        speak("Affected thrust lever, confirm and cutoff")
        time.sleep(2)
    def on_cutoff(self):
        print("Action: Cutoff...")
        speak("Cutoff")
        time.sleep(2)
    def on_affected_engine_fuel_boost_confirm_off_then_norm(self):
        print("Action: Affected engine fuel boost confirm off then norm...")
        speak("Affected engine fuel boost confirm off then norm")
        time.sleep(2)
    def on_off_then_norm(self):
        print("Action: Off then norm...")
        speak("Off then norm")
        time.sleep(2)
    def on_fuel_boost_off(self):
        print("Action: Fuel boost off...")
        speak("Fuel boost off")
        time.sleep(2)
    def on_fuel_boost_norm(self):
        print("Action: Fuel boost norm...")
        speak("Fuel boost norm")
        time.sleep(2)
    def on_check_light_after_30_seconds(self):
        print("Action: Checking light after 30 seconds...")
        speak("Checking light after 30 seconds")
        time.sleep(2)
    def on_thirty_seconds_light_remains_on_bottle_discharge(self):
        print("Action: Thirty seconds, light remains on, bottle discharge...")
        speak("Thirty seconds, light remains on, bottle discharge")
        time.sleep(2)
    def on_discharge(self):
        print("Action: Discharge...")
        speak("Discharge")
        time.sleep(2)
    def on_illuminated_bottle_armed_switch_push(self):
        print("Action: Illuminated bottle armed switch push...")
        speak("Illuminated bottle armed switch push")
        time.sleep(2)
    def on_turn_rotary_test_knob(self):
        print("Action: Turning rotary test knob...")
        speak("Turning rotary test knob")
        time.sleep(2)
    def on_check_engine_fire_lights(self):
        print("Action: Checking engine fire lights both illuminate...")
        speak("Checking engine fire lights both illuminate")
        time.sleep(2)
    def on_order_start_checklist(self):
        print("Action: Ordering start checklist...")
        speak("Ordering start checklist")
        time.sleep(2)
    def on_allocate_radio(self):
        print("Action: Allocating radio...")
        speak("Allocating radio")
        time.sleep(2)
    def on_retrieve_checklist(self):
        print("Action: Retrieving checklist...")
        speak("Retrieving checklist")
        time.sleep(2)
    def on_check_immediate_action_items_done(self):
        print("Action: Checking immediate action items done...")
        speak("Checking immediate action items done")
        time.sleep(2)
    def on_immediate_action_checked(self):
        print("Action: Immediate action checked, Current checklist completed, Checklist to refer next: precautionary shutdown")
        speak("Immediate action checked, Current checklist completed, Checklist to refer next: precautionary shutdown")
        time.sleep(2)
    def on_contact_atc_vector(self):
        print("Action: Contacting ATC to announce emergency and request vector...")
        speak("Contacting ATC to announce emergency and request vector")
        time.sleep(2)
    def on_listen_atc_vector(self):
        print("Action: Listening ATC for vector...")
        speak("Listening ATC for vector")
        time.sleep(2)
    def on_acknowledge_transmission(self):
        print("Action: Acknowledging transmission...")
        speak("Acknowledging transmission")
        time.sleep(2)
    def on_set_heading_accordingly(self):
        print("Action: Setting heading accordingly...")
        speak("Setting heading accordingly")
        time.sleep(2)
    def on_set_flc_accordingly(self):
        print("Action: Setting FLC accordingly...")
        speak("Setting FLC accordingly")
        time.sleep(2)
    def on_announce_start_checklist(self):
        print("Action: Announcing start checklist...")
        speak("Announcing start checklist")
        time.sleep(2)
    def on_retrieve_checklist_start(self):
        print("Action: Retrieving start checklist...")
        speak("Retrieving start checklist")
        time.sleep(2)
    def on_landing_gear_up(self):
        print("Action: Landing gear up...")
        speak("Landing gear up")
        time.sleep(2)
    def on_flap_handle_up(self):
        print("Action: Flap handle up...")
        speak("Flap handle up")
        time.sleep(2)
    def on_throttles_clb_detent(self):
        print("Action: Throttles CLB detent...")
        speak("Throttles CLB detent")
        time.sleep(2)
    def on_yaw_damper_as_desired(self):
        print("Action: Yaw damper as desired...")
        speak("Yaw damper as desired")
        time.sleep(2)
    def on_deice_as_required(self):
        print("Action: Deice as required...")
        speak("Deice as required")
        time.sleep(2)
    def on_pax_safety_switch_as_required(self):
        print("Action: Pax safety switch as required...")
        speak("Pax safety switch as required")
        time.sleep(2)
    def on_pressurization_check(self):
        print("Action: Pressurization check...")
        speak("Pressurization check")
        time.sleep(2)
    def on_alti_set_std(self):
        print("Action: Alti set STD...")
        speak("Alti set STD")
        time.sleep(2)
    def on_crosscheck_alti(self):
        print("Action: Crosscheck alti...")
        speak("Crosscheck alti")
        time.sleep(2)
    def on_announce_checklist_completed(self):
        print("Action: Announce checklist completed...")
        speak("Announce checklist completed")
        time.sleep(2)
    def on_announce_start_checklist_retrieve(self):
        print("Action: Announce start checklist retrieve...")
        speak("Announce start checklist retrieve")
        time.sleep(2)
    def on_retrieve_checklist_start_checklist(self):
        print("Action: Retrieve checklist start checklist...")
        speak("Retrieve checklist start checklist")
        time.sleep(2)
    def on_throttle_affected_engine_cutoff(self):
        print("Action: Throttle affected engine cutoff...")
        speak("Throttle affected engine cutoff")
        time.sleep(2)
    def on_caution_text_readout(self):
        print("Action: Caution text readout...")
        speak("Caution text readout")
    def on_gen_switch_affected_side_off(self):
        print("Action: Gen switch affected side OFF...")
        speak("Gen switch affected side OFF")
    def on_ignition_switch_affected_side_norm(self):
        print("Action: Ignition switch affected side NORM...")
        speak("Ignition switch affected side NORM")
    def on_electrical_load_reduce_as_required(self):
        print("Action: Electrical load reduce as required...")
        speak("Electrical load reduce as required")
    def on_fuel_transfer_knob_as_required(self):
        print("Action: Fuel transfer knob as required...")
        speak("Fuel transfer knob as required")
    def on_verify_engine_fire_switch_affected_side(self):
        print("Action: Verify engine fire switch affected side is pushed...")
        speak("Verify engine fire switch affected side is pushed")
    def on_announce_current_checklist_completed(self):
        print("Action: Announce current checklist completed, Checklist to refer next: single engine approach and landing")
        speak("Announce current checklist completed, Checklist to refer next: single engine approach and landing")
    def on_finished(self):
        print("Action: Finished...")
        speak("Finished")
        time.sleep(2)

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
        agent_object = my_data
        assert isinstance(agent_object, Echo)

    def integer_input_callback(self, io_type, name, value_type, value, my_data):
        igs.info(f"Input {name} written to {value}")
        agent_object = my_data
        assert isinstance(agent_object, Echo)

    def double_input_callback(self, io_type, name, value_type, value, my_data):
        igs.info(f"Input {name} written to {value}")
        agent_object = my_data
        assert isinstance(agent_object, Echo)

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

        igs.input_create("airspeed", igs.DOUBLE_T, None)
        igs.input_create("pitch", igs.DOUBLE_T, None)
        igs.input_create("roll", igs.DOUBLE_T, None)
        igs.input_create("heading", igs.DOUBLE_T, None)
        igs.input_create("verticalSpeed", igs.DOUBLE_T, None)
        igs.input_create("altitude", igs.DOUBLE_T, None)
        igs.input_create("controlThrottle", igs.DOUBLE_T, None)
        igs.input_create("controlFlaps", igs.DOUBLE_T, None)
        igs.input_create("controlGear", igs.DOUBLE_T, None)
        igs.input_create("speedBrakes", igs.DOUBLE_T, None)
        igs.input_create("parkBrake", igs.DOUBLE_T, None)
        igs.input_create("l_throttle", igs.DOUBLE_T, None)
        igs.input_create("r_throttle", igs.DOUBLE_T, None)
        igs.input_create("cas", igs.DOUBLE_T, None)
        igs.input_create("n1_match_bug", igs.DOUBLE_T, None)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.input_create("n1_percent", igs.DOUBLE_T, None)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.input_create("slip", igs.DOUBLE_T, None)  # positive is right, negative is left
        igs.input_create("engine_fires", igs.DOUBLE_T, None)  # [0, 0] first means E1, second means E2
        igs.input_create("generators_off", igs.DOUBLE_T, None)  # [0, 0] first means L generator, second means R generator
        igs.input_create("pax_safety", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("master_warning", igs.DOUBLE_T, None)  # readonly 0 is off, 1 is on
        igs.input_create("master_caution", igs.DOUBLE_T, None)  # readonly 0 is off, 1 is on
        igs.input_create("flight_director", igs.DOUBLE_T, None)  # Not sure how to set FD up using a comm
        igs.input_create("speed_mode", igs.DOUBLE_T, None)  # Mustang/airspeedmach
        igs.input_create("heading_mode", igs.DOUBLE_T, None)  # Mustang/heading
        igs.input_create("autopilot_master", igs.DOUBLE_T, None)  # 0 is off, 1 is FD 2 is AP + FD
        igs.input_create("fuel_boost_l", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("fuel_boost_r", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("test_knob", igs.DOUBLE_T, None)  # 0 to 11 for each test position
        igs.input_create("autopilot_heading_set", igs.DOUBLE_T, None)  # 0 to 360
        igs.input_create("autopilot_state", igs.DOUBLE_T, None)  # need to understand this seems to be an integer that represents the state of the autopilot
        igs.input_create("yaw_damper", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("l_ign_switch", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("r_ign_switch", igs.DOUBLE_T, None)  # 0 is off, 1 is on
        igs.input_create("l_gen_switch", igs.DOUBLE_T, None)  # 0 is reset, 1 is off 2 is on
        igs.input_create("r_gen_switch", igs.DOUBLE_T, None)  # 0 is reset, 1 is off 2 is on
        igs.input_create("transfer_knob", igs.DOUBLE_T, None)  # 0 is left, 1 is off 2 is right


        igs.observe_input("airspeed", self.double_input_callback, self.agent)
        igs.observe_input("pitch", self.double_input_callback, self.agent)
        igs.observe_input("roll", self.double_input_callback, self.agent)
        igs.observe_input("heading", self.double_input_callback, self.agent)
        igs.observe_input("verticalSpeed", self.double_input_callback, self.agent)
        igs.observe_input("altitude", self.double_input_callback, self.agent)
        igs.observe_input("controlThrottle", self.double_input_callback, self.agent)
        igs.observe_input("controlFlaps", self.double_input_callback, self.agent)
        igs.observe_input("controlGear", self.double_input_callback, self.agent)
        igs.observe_input("speedBrakes", self.double_input_callback, self.agent)
        igs.observe_input("parkBrake", self.double_input_callback, self.agent)
        igs.observe_input("l_throttle", self.double_input_callback, self.agent)
        igs.observe_input("r_throttle", self.double_input_callback, self.agent)
        igs.observe_input("cas", self.double_input_callback, self.agent)
        igs.observe_input("n1_match_bug", self.double_input_callback, self.agent)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.observe_input("n1_percent", self.double_input_callback, self.agent)  # [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        igs.observe_input("slip", self.double_input_callback, self.agent)  # positive is right, negative is left
        igs.observe_input("engine_fires", self.double_input_callback, self.agent)  # [0, 0] first means E1, second means E2
        igs.observe_input("generators_off", self.double_input_callback, self.agent)  # [0, 0] first means L generator, second means R generator
        igs.observe_input("pax_safety", self.double_input_callback, self.agent)  # 0 is off, 1 is on
        igs.observe_input("master_warning", self.double_input_callback, self.agent)  # readonly 0 is off, 1 is on
        igs.observe_input("master_caution", self.double_input_callback, self.agent)  # readonly 0 is off, 1 is on
        igs.observe_input("flight_director", self.double_input_callback, self.agent)  # Not sure how to set FD up using a comm
        igs.observe_input("speed_mode", self.double_input_callback, self.agent)  # Mustang/airspeedmach
        igs.observe_input("heading_mode", self.double_input_callback, self.agent)  # Mustang/heading
        igs.observe_input("autopilot_master", self.double_input_callback, self.agent)  # 0 is off, 1 is FD 2 is AP + FD
        igs.observe_input("fuel_boost_l", self.double_input_callback, self.agent)  # 0 is off, 1 is on
        igs.observe_input("fuel_boost_r", self.double_input_callback, self.agent)  # 0 is off, 1 is on
        igs.observe_input("test_knob", self.double_input_callback, self.agent)  # 0 to 11 for each test position
        igs.observe_input("autopilot_heading_set", self.double_input_callback, self.agent)  # 0 to 360
        igs.observe_input("autopilot_state", self.double_input_callback, self.agent)  # need to understand this seems to be an integer that represents the state of the autopilot
        igs.observe_input("yaw_damper", self.double_input_callback, self.agent)  # 0 is off, 1 is on
        igs.observe_input("l_ign_switch", self.double_input_callback, self.agent)  # 0 is off, 1 is on
        igs.observe_input("r_ign_switch", self.double_input_callback, self.agent)  # 0 is off, 1 is on
        igs.observe_input("l_gen_switch", self.double_input_callback, self.agent)  # 0 is reset, 1 is off 2 is on
        igs.observe_input("r_gen_switch", self.double_input_callback, self.agent)  # 0 is reset, 1 is off 2 is on
        igs.observe_input("transfer_knob", self.double_input_callback, self.agent)  # 0 is left, 1 is off 2 is right

        igs.log_set_console(True)
        igs.log_set_console_level(igs.LOG_INFO)

        igs.start_with_device(self.device, self.port)

        # Loop to advance FSM every 3 seconds
        print(f"Current state: {self.fsm.current_state.name}")
        self.should_run[0] = True
        self.fsm.run()
        print("FSM finished.")
# Example usage
if __name__ == "__main__":
    agent = TarsAgent()
    agent.start()