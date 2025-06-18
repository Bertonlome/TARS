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
        self.state_entry_time = time.monotonic()
        self.task_done_human = [False]

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
        self.speed_mode_flc_v2_heading_mode = State("Set speed mode, heading mode")
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
        self.fsm.add_transition(Transition(self.idle, self.confirm_takeoff_clearance, self.can_start_timeout, self.on_confirm_takeoff_clearance))
        self.fsm.add_transition(Transition(self.confirm_takeoff_clearance, self.ali_run_cen, self.can_start_timeout, self.on_ali_run_cen))
        self.fsm.add_transition(Transition(self.ali_run_cen, self.check_winds, self.can_start_timeout, self.on_check_winds))
        self.fsm.add_transition(Transition(self.check_winds, self.hold_brakes, self.is_acked, self.on_hold_brakes))
        self.fsm.add_transition(Transition(self.hold_brakes, self.check_cas_clear, self.can_start_timeout, self.on_check_cas_clear))
        self.fsm.add_transition(Transition(self.check_cas_clear, self.set_thrust, self.can_start_timeout, self.on_set_thrust))
        self.fsm.add_transition(Transition(self.set_thrust, self.check_fadec_bug_to, self.is_thrust_sensed, self.on_check_fadec_bug_to))
        self.fsm.add_transition(Transition(self.check_fadec_bug_to, self.check_engine_spool_evenly, self.can_start_timeout, self.on_check_engine_spool_evenly))
        self.fsm.add_transition(Transition(self.check_engine_spool_evenly, self.check_n1_percent, self.can_start_timeout, self.on_thrust_set))
        self.fsm.add_transition(Transition(self.check_n1_percent, self.release_brakes, self.can_start_timeout, self.on_release_brakes))
        self.fsm.add_transition(Transition(self.release_brakes, self.airspeed_alive, self.is_brake_released_sensed, self.on_airspeed_alive))
        self.fsm.add_transition(Transition(self.airspeed_alive, self.seventy_kts, self.is_airspeed_alive, self.on_seventy_kts))
        self.fsm.add_transition(Transition(self.seventy_kts, self.v1, self.is_seventy_kts, self.on_v1))
        self.fsm.add_transition(Transition(self.v1, self.rotate, self.is_v_one , self.on_rotate))
        self.fsm.add_transition(Transition(self.rotate, self.maintain_pitch, self.is_v_rotate , self.on_maintain_pitch))
        self.fsm.add_transition(Transition(self.maintain_pitch, self.check_positive_rate, self.is_pitch_maintained, self.on_check_positive_rate))
        #self.fsm.add_transition(Transition(self.scan_slip_skid, self.check_positive_rate, self.can_start_timeout, self.on_check_positive_rate))
        self.fsm.add_transition(Transition(self.check_positive_rate, self.gear_up, self.is_positive_rate, self.on_positive_rate_gear_up))
        self.fsm.add_transition(Transition(self.gear_up, self.announce_alarm, self.is_alarm, self.on_announce_alarm))
        #self.fsm.add_transition(Transition(self.apply_rudder, self.trim_rudder, self.can_start_timeout, self.on_trim_rudder))
        #self.fsm.add_transition(Transition(self.trim_rudder, self.announce_alarm, self.can_start_timeout, self.on_announce_alarm))
        self.fsm.add_transition(Transition(self.announce_alarm, self.reset_master_warning, self.can_start_timeout, self.on_reset_master_warning))
        self.fsm.add_transition(Transition(self.reset_master_warning, self.set_fd_to_mode, self.is_master_warning_reset, self.on_set_fd_to_mode))
        self.fsm.add_transition(Transition(self.set_fd_to_mode, self.check_lg_up, self.can_start_timeout, self.on_maintain_pitch_after_fd))
        self.fsm.add_transition(Transition(self.check_lg_up, self.check_airspeed_v2, self.is_gear_up, self.on_check_airspeed_v2))
        self.fsm.add_transition(Transition(self.check_airspeed_v2, self.speed_mode_flc_v2_heading_mode, self.is_airspeed_v_two, self.on_say_speed_mode_flc_v2_heading_mode))
        self.fsm.add_transition(Transition(self.speed_mode_flc_v2_heading_mode, self.contact_atc_emergency, self.can_start_timeout, self.on_contact_atc_emergency))
        self.fsm.add_transition(Transition(self.contact_atc_emergency, self.listen_atc, self.is_acked, self.on_listen_atc))
        self.fsm.add_transition(Transition(self.listen_atc, self.engage_autopilot, self.is_ap_altitude, self.on_seven_hundred_ft_engage_ap))
        self.fsm.add_transition(Transition(self.engage_autopilot, self.check_v2_plus_twelve, self.is_v2_plus_12 , self.on_check_v2_plus_twelve))
        self.fsm.add_transition(Transition(self.check_v2_plus_twelve, self.retract_flaps, self.can_start_timeout, self.on_say_retract_flaps))
        self.fsm.add_transition(Transition(self.retract_flaps, self.throttle_affected_idle, self.is_flaps_retracted, self.on_affected_thrust_lever_confirm_idle))
        self.fsm.add_transition(Transition(self.throttle_affected_idle, self.start_chrono, self.is_throttle_idle, self.on_top))
        self.fsm.add_transition(Transition(self.start_chrono, self.check_light_after_15_seconds, self.can_start_timeout, self.on_check_light_after_15_seconds))
        self.fsm.add_transition(Transition(self.check_light_after_15_seconds, self.eng_fire_switch_lift_cover_push, self.can_start_timeout, self.on_eng_fire_switch_lift_cover_push))
        self.fsm.add_transition(Transition(self.eng_fire_switch_lift_cover_push, self.cutoff, self.can_start_timeout, self.on_affected_thrust_lever_confirm_cutoff))
        self.fsm.add_transition(Transition(self.cutoff, self.affected_engine_fuel_boost_confirm_off_then_norm, self.is_throttle_cutoff, self.on_affected_engine_fuel_boost_confirm_off_then_norm))
        self.fsm.add_transition(Transition(self.affected_engine_fuel_boost_confirm_off_then_norm, self.fuel_boost_off, self.can_start_timeout, self.on_fuel_boost_off))
        self.fsm.add_transition(Transition(self.fuel_boost_off, self.fuel_boost_norm, self.is_fuel_boost_off, self.on_fuel_boost_norm))
        self.fsm.add_transition(Transition(self.fuel_boost_norm, self.check_light_after_30_seconds, self.is_fuel_boost_norm, self.on_check_light_after_30_seconds))
        self.fsm.add_transition(Transition(self.check_light_after_30_seconds, self.thirty_seconds_light_remains_on_bottle_discharge, self.can_start_timeout, self.on_thirty_seconds_light_remains_on_bottle_discharge))
        self.fsm.add_transition(Transition(self.thirty_seconds_light_remains_on_bottle_discharge, self.discharge, self.can_start_timeout, self.on_discharge))
        self.fsm.add_transition(Transition(self.discharge, self.illuminated_bottle_armed_switch_push, self.can_start_timeout, self.on_illuminated_bottle_armed_switch_push))
        self.fsm.add_transition(Transition(self.illuminated_bottle_armed_switch_push, self.turn_rotary_test_knob, self.can_start_timeout, self.on_turn_rotary_test_knob))
        self.fsm.add_transition(Transition(self.turn_rotary_test_knob, self.check_engine_fire_lights, self.is_test_knob_turned, self.on_check_engine_fire_lights))
        self.fsm.add_transition(Transition(self.check_engine_fire_lights, self.order_start_checklist, self.can_start_timeout, self.on_order_start_checklist))
        self.fsm.add_transition(Transition(self.order_start_checklist, self.allocate_radio, self.can_start_timeout, self.on_allocate_radio))
        self.fsm.add_transition(Transition(self.allocate_radio, self.retrieve_checklist, self.can_start_timeout, self.on_retrieve_checklist))
        self.fsm.add_transition(Transition(self.retrieve_checklist, self.check_immediate_action_items_done, self.can_start_timeout, self.on_check_immediate_action_items_done))
        self.fsm.add_transition(Transition(self.check_immediate_action_items_done, self.contact_atc_vector, self.can_start_timeout, self.on_immediate_action_checked))
        self.fsm.add_transition(Transition(self.contact_atc_vector, self.announce_start_checklist, self.can_start_timeout, self.on_listen_atc_vector))
        self.fsm.add_transition(Transition(self.announce_start_checklist, self.retrieve_checklist_start, self.can_start_timeout, self.on_retrieve_checklist_start))
        self.fsm.add_transition(Transition(self.retrieve_checklist_start, self.landing_gear_up, self.is_gear_up, self.on_landing_gear_up))
        self.fsm.add_transition(Transition(self.landing_gear_up, self.flap_handle_up, self.is_flaps_retracted, self.on_flap_handle_up))
        self.fsm.add_transition(Transition(self.flap_handle_up, self.throttles_clb_detent, self.is_throttle_clb, self.on_throttles_clb_detent))
        self.fsm.add_transition(Transition(self.throttles_clb_detent, self.yaw_damper_as_desired, self.can_start_timeout, self.on_yaw_damper_as_desired))
        self.fsm.add_transition(Transition(self.yaw_damper_as_desired, self.deice_as_required, self.can_start_timeout, self.on_deice_as_required))
        self.fsm.add_transition(Transition(self.deice_as_required, self.pax_safety_switch_as_required, self.can_start_timeout, self.on_pax_safety_switch_as_required))
        self.fsm.add_transition(Transition(self.pax_safety_switch_as_required, self.pressurization_check, self.can_start_timeout, self.on_pressurization_check))
        self.fsm.add_transition(Transition(self.pressurization_check, self.alti_set_std, self.can_start_timeout, self.on_alti_set_std))
        self.fsm.add_transition(Transition(self.alti_set_std, self.crosscheck_alti, self.can_start_timeout, self.on_crosscheck_alti))
        self.fsm.add_transition(Transition(self.crosscheck_alti, self.announce_checklist_completed, self.can_start_timeout, self.on_announce_checklist_completed))
        self.fsm.add_transition(Transition(self.announce_checklist_completed, self.announce_start_checklist_retrieve, self.can_start_timeout, self.on_announce_start_checklist_retrieve))
        self.fsm.add_transition(Transition(self.announce_start_checklist_retrieve, self.retrieve_checklist_start_checklist, self.can_start_timeout, self.on_retrieve_checklist_start_checklist))
        self.fsm.add_transition(Transition(self.retrieve_checklist_start_checklist, self.throttle_affected_engine_cutoff, self.can_start_timeout, self.on_throttle_affected_engine_cutoff))
        self.fsm.add_transition(Transition(self.throttle_affected_engine_cutoff, self.caution_text_readout, self.is_throttle_cutoff, self.on_caution_text_readout))
        self.fsm.add_transition(Transition(self.caution_text_readout, self.gen_switch_affected_side_off, self.can_start_timeout, self.on_gen_switch_affected_side_off))
        self.fsm.add_transition(Transition(self.gen_switch_affected_side_off, self.ignition_switch_affected_side_norm, self.is_gen_switch_off, self.on_ignition_switch_affected_side_norm))
        self.fsm.add_transition(Transition(self.ignition_switch_affected_side_norm, self.electrical_load_reduce_as_required, self.is_ignition_switch_norm, self.on_electrical_load_reduce_as_required))
        self.fsm.add_transition(Transition(self.electrical_load_reduce_as_required, self.fuel_transfer_knob_as_required, self.can_start_timeout, self.on_fuel_transfer_knob_as_required))
        self.fsm.add_transition(Transition(self.fuel_transfer_knob_as_required, self.verify_engine_fire_switch_affected_side, self.can_start_timeout, self.on_verify_engine_fire_switch_affected_side))
        self.fsm.add_transition(Transition(self.verify_engine_fire_switch_affected_side, self.announce_current_checklist_completed, self.can_start_timeout, self.on_announce_current_checklist_completed))
        self.fsm.add_transition(Transition(self.announce_current_checklist_completed, self.finished, self.can_start_timeout, self.on_finished))
        
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
    def can_start_timeout(self):
        if self.state_entry_time is None:
            return False #Not ready yet
        required = self.get_time_end_action_for_state(self.fsm.current_state)
        elapsed = time.monotonic() - self.state_entry_time
        return elapsed >= required
    
    def is_acked(self):
        if self.task_done_human[0]:
            self.task_done_human[0] = False
            return True
        return False

    def is_thrust_sensed(self):
        if self.agent.control_throttle_i is not None and self.agent.control_throttle_i == 1:
            return True
        return False

    def is_brake_released_sensed(self):
        if self.agent.park_brakes_i is not None and self.agent.park_brakes_i == 0:
            return True
        return False

    def is_airspeed_alive(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i > 30:
            speak("Airspeed's alive")
            return True
        return False

    def is_seventy_kts(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 70:
            speak("Seventy Knots")
            return True
        return False

    def is_v_one(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 90:
            speak("Rotate")
            return True
        return False

    def is_v_rotate(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 91:
            return True
        return False

    def is_pitch_maintained(self):
        if self.agent.pitch_i is not None and self.agent.pitch_i >= 7:
            time.sleep(1)  # Simulate time to maintain pitch
            if self.agent.pitch_i >= 8:
                return True
        return False

    def is_positive_rate(self):
        if self.agent.vertical_sped_i is not None and self.agent.vertical_sped_i > 100:
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
    
    def is_master_warning_reset(self):
        print("Resetting Master Warning")
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
        print(f"Checking if test knob is turned - Value: {self.agent.test_knob_i}")
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
        
    def get_time_init_action_for_state(self, state_name):
        seconds = 0
        task = next((task for task in self.tasks if task.get("task_name", "").strip() == state_name.name), None)
        if task is not None:
            try:
                seconds = int(task.get("time_init_action")) +1 
            except (TypeError, ValueError):
                seconds = 0
        #print(seconds)
        return seconds

    def get_time_end_action_for_state(self, state_name):
        seconds = 0
        task = next((task for task in self.tasks if task.get("task_name", "").strip() == state_name.name), None)
        if task is not None:
            try:
                seconds = int(task.get("time_end_action")) +1 
            except(TypeError, ValueError):
                seconds = 2
                if task.get("time_end_action") in ("ack", "sense", "until_new"):
                    seconds = 1000
        #print(seconds)
        return seconds

    def on_confirm_takeoff_clearance(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Confirming takeoff clearance...")
    def on_ali_run_cen(self):
        self.state_entry_time = time.monotonic()
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Aligning with runway centerline...")
    def on_check_winds(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking winds...")
        speak("wind report Wind calm  zero two 6 degrees at 3 knots")
    def on_hold_brakes(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Holding brakes...")
    def on_check_cas_clear(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking CAS clear...")
        speak("CAS is clear")
    def on_set_thrust(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Setting thrust...")
    def on_check_fadec_bug_to(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking FADEC bug TO...")
    def on_check_engine_spool_evenly(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking engine spool evenly...")
    def on_thrust_set(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Thrust set...")
    def on_check_n1_percent(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking N1% matches command bug...")
    def on_release_brakes(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Releasing brakes...")
    def on_airspeed_alive(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Airspeed's alive...")
    def on_seventy_kts(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Seventy knots...")
    def on_v1(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: V1...")
    def on_rotate(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Rotate...")
    def on_maintain_pitch(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Maintaining 10 degrees pitch...")
    def on_scan_slip_skid(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Scanning slip/skid indicator...")
    def on_check_positive_rate(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking positive rate...")
    def on_positive_rate_gear_up(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Positive rate, gear up...")
        speak("Positive rate, gear up")
    def on_gear_up(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Gear up...")
    def on_apply_rudder(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Applying rudder...")
    def on_trim_rudder(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Trimming rudder...")
        speak("Trimming rudder")
    def on_announce_alarm(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Announcing alarm...")
        speak("Alarm Engine fire, Low oil pressure")
    def on_reset_master_warning(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Resetting Master Warning...")
    def on_set_fd_to_mode(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Setting FD TO Mode...")
        #speak("Flight Director set to Takeoff mode")
    def on_maintain_pitch_after_fd(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Maintaining 10 degrees pitch after FD...")
    def on_check_lg_up(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking Landing Gear up...")
    def on_check_airspeed_v2(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking Airspeed V2...")
    def on_say_speed_mode_flc_v2_heading_mode(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Speed mode FLC V2, heading mode...")
        #speak("Speed mode FLC V2, heading mode")
    def on_set_speed_mode_heading_mode(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Set speed mode, heading mode...")
    def on_contact_atc_emergency(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Contacting ATC to announce emergency...")
    def on_listen_atc(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Listening ATC...")
    def on_seven_hundred_ft_engage_ap(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Seven hundred feet, engage autopilot...")
        speak("Seven hundred feet, engage autopilot")
    def on_engage_autopilot(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Engaging autopilot...")
    def on_check_v2_plus_twelve(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking V2+12...")
    def on_say_retract_flaps(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Retract flaps...")
        speak("Retract flaps")
    def on_retract_flaps(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Retracting flaps...")
    def on_affected_thrust_lever_confirm_idle(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Affected thrust lever, confirm and idle...")
        speak("Affected thrust lever, confirm and idle")
    def on_throttle_affected_idle(self):
        self.state_entry_time = time.monotonic()
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Throttle affected idle...")
    def on_top(self):
        self.state_entry_time = time.monotonic()
        speak("TOP")
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: TOP...")
    def on_start_chrono(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Starting chrono...")
    def on_check_light_after_15_seconds(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking light after 15 seconds...")
    def on_eng_fire_switch_lift_cover_push(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("ENG FIRE switch lift cover and push")
        print("Action: ENG FIRE switch lift cover and push...")
    def on_affected_thrust_lever_confirm_cutoff(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("Affected thrust lever, confirm and cutoff")
        print("Action: Affected thrust lever, confirm and cutoff...")
    def on_cutoff(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Cutoff...")
    def on_affected_engine_fuel_boost_confirm_off_then_norm(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("Affected engine fuel boost confirm off then norm")
        print("Action: Affected engine fuel boost confirm off then norm...")
    def on_off_then_norm(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("Off then norm")
        print("Action: Off then norm...")
    def on_fuel_boost_off(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("Fuel boost off")
        print("Action: Fuel boost off...")
    def on_fuel_boost_norm(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("Fuel boost norm")
        print("Action: Fuel boost norm...")
    def on_check_light_after_30_seconds(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking light after 30 seconds...")
    def on_thirty_seconds_light_remains_on_bottle_discharge(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("Thirty seconds, light remains on, bottle discharge")
        print("Action: Thirty seconds, light remains on, bottle discharge...")
    def on_discharge(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Discharge...")
    def on_illuminated_bottle_armed_switch_push(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Illuminated bottle armed switch push...")
    def on_turn_rotary_test_knob(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Turning rotary test knob...")
    def on_check_engine_fire_lights(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking engine fire lights both illuminate...")
    def on_order_start_checklist(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Ordering start checklist...")
    def on_allocate_radio(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Allocating radio...")
    def on_retrieve_checklist(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Retrieving checklist...")
    def on_check_immediate_action_items_done(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Checking immediate action items done...")
    def on_immediate_action_checked(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Immediate action checked, Current checklist completed, Checklist to refer next: precautionary shutdown")
        speak("Immediate action checked, Current checklist completed, Checklist to refer next: precautionary shutdown")
    def on_contact_atc_vector(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Contacting ATC to announce emergency and request vector...")
    def on_listen_atc_vector(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Listening ATC for vector...")
    def on_acknowledge_transmission(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Acknowledging transmission...")
    def on_set_heading_accordingly(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Setting heading accordingly...")
    def on_set_flc_accordingly(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Setting FLC accordingly...")
    def on_announce_start_checklist(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Announcing start checklist...")
    def on_retrieve_checklist_start(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Retrieving start checklist...")
    def on_landing_gear_up(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Landing gear up...")
    def on_flap_handle_up(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Flap handle up...")
    def on_throttles_clb_detent(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Throttles CLB detent...")
    def on_yaw_damper_as_desired(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Yaw damper as desired...")
    def on_deice_as_required(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Deice as required...")
    def on_pax_safety_switch_as_required(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Pax safety switch as required...")
    def on_pressurization_check(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Pressurization check...")
    def on_alti_set_std(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("Alti set Standard")
        print("Action: Alti set STD...")
    def on_crosscheck_alti(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Crosscheck alti...")
    def on_announce_checklist_completed(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("checklist completed")
        print("Action: Announce checklist completed...")
    def on_announce_start_checklist_retrieve(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Announce start checklist retrieve...")
    def on_retrieve_checklist_start_checklist(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Retrieve checklist start checklist...")
    def on_throttle_affected_engine_cutoff(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("Throttle affected engine cutoff")
        print("Action: Throttle affected engine cutoff...")
    def on_caution_text_readout(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Caution text readout...")
    def on_gen_switch_affected_side_off(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("Gen switch affected side OFF")
        print("Action: Gen switch affected side OFF...")
    def on_ignition_switch_affected_side_norm(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("Ignition switch affected side NORM")
        print("Action: Ignition switch affected side NORM...")
    def on_electrical_load_reduce_as_required(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Electrical load reduce as required...")
    def on_fuel_transfer_knob_as_required(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Fuel transfer knob as required...")
    def on_verify_engine_fire_switch_affected_side(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Verify engine fire switch affected side is pushed...")
    def on_announce_current_checklist_completed(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        speak("checklist completed, Checklist to refer next: single engine approach and landing")
        print("Action: Announce current checklist completed, Checklist to refer next: single engine approach and landing")
    def on_finished(self):
        self.state_entry_time = time.monotonic()
        time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print("Action: Finished...")

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
        elif name == "verticalSpeed":
            agent_object.vertical_sped_i = value
        elif name == "altitude":
            agent_object.altitude_i = value
        elif name == "controlThrottle":
            agent_object.control_throttle_i = value
        elif name == "controlFlaps":
            agent_object.control_flaps_i = value
        elif name == "controlGear":
            agent_object.control_gear_i = value
        elif name == "speedBrakes":
            agent_object.speed_brakes_i = value
        elif name == "parkBrake":
            agent_object.park_brakes_i = value
        elif name == "l_throttle":
            agent_object.l_throttle_i = value
        elif name == "r_throttle":
            agent_object.r_throttle_i = value
        elif name == "cas":
            agent_object.cas_i = value
        elif name == "n1_match_bug":
            agent_object.n1_match_bug_i = value
        elif name == "n1_percent":
            agent_object.n1_percent_i = value
        elif name == "slip":
            agent_object.slip_i = value
        elif name == "engine_fires":
            agent_object.engine_fires_i = value
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
        elif name == "autopilot_master":
            agent_object.autopilot_master_i = value
        elif name == "autopilot_heading_set":
            agent_object.autopilot_heading_set_i = value
        elif name == "autopilot_state":
            agent_object.autopilot_state_i = value
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
# Example usage
if __name__ == "__main__":
    agent = TarsAgent()
    agent.start()