import time
import signal
from Core.echo import *
from Core.fsm import FiniteStateMachine, State, Transition
from Core.tts import speak_wait
import csv

# Agent Class
class TarsAgent:
    def __init__(self, agent_name="TARS Agent", device="wlp0s20f3", port=5670, verbose=False):
        self.agent_name = agent_name
        self.device = device
        self.port = port
        self.verbose = verbose
        self.is_interrupted = False
        self.impulsion_count = 0
        self.state_entry_time = time.monotonic()
        self.task_done_human = [False]

        self.states = {}
        # FSM setup

        #conditions
        self.is_on_off = [False]
        self.should_run = [False]
        self.should_finish = [False]

        self.states = self.create_states_from_csv("Core/task_allocation.csv")
        self.fsm = FiniteStateMachine(self.states["idle"])

        
        self.fsm.add_transition(Transition(self.states["idle"], self.states["confirm_takeoff_clearance"], self.is_started, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["confirm_takeoff_clearance"], self.states["ali_run_cen"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["ali_run_cen"], self.states["check_winds"], self.can_transition_timeout, lambda: self.on_speak_action("Wind report, wind calm, zero two six degrees at three knots")))
        self.fsm.add_transition(Transition(self.states["check_winds"], self.states["hold_brakes"], self.is_acked, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["hold_brakes"], self.states["check_cas_clear"], self.can_transition_timeout, lambda: self.on_speak_action("C A S is clear")))
        self.fsm.add_transition(Transition(self.states["check_cas_clear"], self.states["set_thrust"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["set_thrust"], self.states["check_fadec_bug_to"], self.is_thrust_sensed, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["check_fadec_bug_to"], self.states["check_engine_spool_evenly"], self.is_fadec_bug_to, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["check_engine_spool_evenly"], self.states["check_n1_percent"], self.is_engine_spool_even, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["check_n1_percent"], self.states["release_brakes"], self.is_n1_percent_above_90, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["release_brakes"], self.states["acceleration"], self.is_brake_released_sensed, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["acceleration"], self.states["airspeed_alive"], self.is_airspeed_alive, lambda: self.on_speak_action("Airspeed's alive")))
        self.fsm.add_transition(Transition(self.states["airspeed_alive"], self.states["seventy_kts"], self.is_seventy_kts, lambda: self.on_speak_action("seventy knots")))
        self.fsm.add_transition(Transition(self.states["seventy_kts"], self.states["v1"], self.is_v_one, lambda: self.on_speak_action("V one")))
        self.fsm.add_transition(Transition(self.states["v1"], self.states["rotate"], self.is_v_rotate, lambda: self.on_speak_action("Rotate")))
        self.fsm.add_transition(Transition(self.states["rotate"], self.states["maintain_pitch"], self.is_pitch_maintained, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["maintain_pitch"], self.states["check_positive_rate"], self.is_positive_rate, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["check_positive_rate"], self.states["gear_up"], self.is_positive_rate, lambda: self.on_speak_action("Positive rate, gear up")))
        self.fsm.add_transition(Transition(self.states["gear_up"], self.states["announce_start_checklist_aft_to_norm_proc"], self.is_400_ft, self.on_speak_action))
        

        # IF ALARM
        self.fsm.add_transition(Transition(self.states["gear_up"], self.states["announce_alarm"], self.is_alarm, lambda: self.on_speak_action("Alarm Engine fire, low oil pressure")))
        #self.fsm.add_transition(Transition(self.apply_rudder, self.trim_rudder, self.can_start_timeout, self.on_trim_rudder))
        #self.fsm.add_transition(Transition(self.trim_rudder, self.announce_alarm, self.can_start_timeout, self.on_announce_alarm))
        self.fsm.add_transition(Transition(self.states["announce_alarm"], self.states["reset_master_warning"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["reset_master_warning"], self.states["set_fd_to_mode"], self.is_master_warning_reset, lambda: self.on_speak_action("Flight Director on, takeoff mode")))
        self.fsm.add_transition(Transition(self.states["set_fd_to_mode"], self.states["check_lg_up"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["check_lg_up"], self.states["check_airspeed_v2"], self.is_gear_up, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["check_airspeed_v2"], self.states["speed_mode_flc_v2_heading_mode"], self.is_airspeed_v_two, lambda: self.on_speak_action("V two, speed mode FLC, heading mode can be engaged")))
        self.fsm.add_transition(Transition(self.states["speed_mode_flc_v2_heading_mode"], self.states["contact_atc_emergency"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["contact_atc_emergency"], self.states["listen_atc"], self.is_acked, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["listen_atc"], self.states["engage_autopilot"], self.is_ap_altitude, lambda: self.on_speak_action("Seven hundred feet, autopilot ready to engage")))
        self.fsm.add_transition(Transition(self.states["engage_autopilot"], self.states["check_v2_plus_twelve"], self.is_v2_plus_12, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["check_v2_plus_twelve"], self.states["retract_flaps_emer"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["retract_flaps_emer"], self.states["throttle_affected_idle"], self.is_flaps_retracted, lambda: self.on_speak_action("Affected thrust lever, confirm and idle")))
        self.fsm.add_transition(Transition(self.states["throttle_affected_idle"], self.states["start_chrono"], self.is_throttle_idle, lambda: self.on_speak_action("Chronometer started, fifteen seconds to check light")))
        self.fsm.add_transition(Transition(self.states["start_chrono"], self.states["check_light_after_15_seconds"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["check_light_after_15_seconds"], self.states["eng_fire_switch_lift_cover_and_push"], self.can_transition_timeout, lambda: self.on_speak_action("Engine fire switch, lift cover and push")))
        self.fsm.add_transition(Transition(self.states["eng_fire_switch_lift_cover_and_push"], self.states["cutoff"], self.can_transition_timeout, lambda: self.on_speak_action("Affected thrust leve, confirm and cutoff")))
        self.fsm.add_transition(Transition(self.states["cutoff"], self.states["affected_engine_fuel_boost_confirm_off_then_norm"], self.is_throttle_cutoff, lambda: self.on_speak_action("Affected engine fuel boost, confirm off then norm")))
        self.fsm.add_transition(Transition(self.states["affected_engine_fuel_boost_confirm_off_then_norm"], self.states["fuel_boost_off"], self.can_transition_timeout, lambda: self.on_speak_action("Fuel boost off")))
        self.fsm.add_transition(Transition(self.states["fuel_boost_off"], self.states["fuel_boost_norm"], self.is_fuel_boost_off, lambda: self.on_speak_action("Fuel boost norm")))
        self.fsm.add_transition(Transition(self.states["fuel_boost_norm"], self.states["check_light_after_30_seconds"], self.is_fuel_boost_norm, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["check_light_after_30_seconds"], self.states["thirty_seconds_light_remains_on_bottle_discharge"], self.can_transition_timeout, lambda: self.on_speak_action("Thirty seconds light remains on, bottle discharge")))
        self.fsm.add_transition(Transition(self.states["thirty_seconds_light_remains_on_bottle_discharge"], self.states["discharge"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["discharge"], self.states["illuminated_bottle_armed_switch_push"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["illuminated_bottle_armed_switch_push"], self.states["turn_rotary_test_knob"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["turn_rotary_test_knob"], self.states["check_engine_fire_lights"], self.is_test_knob_turned, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["check_engine_fire_lights"], self.states["order_start_checklist"], self.can_transition_timeout, lambda: self.on_speak_action("Start checklist : Engine Fire Emergency Checklist")))
        self.fsm.add_transition(Transition(self.states["order_start_checklist"], self.states["allocate_radio"], self.is_acked, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["allocate_radio"], self.states["retrieve_checklist"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["retrieve_checklist"], self.states["check_immediate_action_items_done"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["check_immediate_action_items_done"], self.states["contact_atc_vector"], self.can_transition_timeout, lambda: self.on_speak_action("Immediate action items checked, Current checklist completed, checklist to refer next: precautionary shutdown")))
        self.fsm.add_transition(Transition(self.states["contact_atc_vector"], self.states["announce_start_checklist_aft_to_norm_proc"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["announce_start_checklist_aft_to_norm_proc"], self.states["retrieve_checklist_start"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["retrieve_checklist_start"], self.states["landing_gear_up"], self.is_gear_up, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["landing_gear_up"], self.states["flap_handle_up"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["flap_handle_up"], self.states["throttles_clb_detent"], self.is_flaps_retracted, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["throttles_clb_detent"], self.states["yaw_damper_as_desired"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["yaw_damper_as_desired"], self.states["deice_as_required"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["deice_as_required"], self.states["pax_safety_switch_as_required"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["pax_safety_switch_as_required"], self.states["pressurization_check"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["pressurization_check"], self.states["alti_set_std"], self.can_transition_timeout, lambda: self.on_speak_action("Altimeter set to standard pressure")))
        self.fsm.add_transition(Transition(self.states["alti_set_std"], self.states["crosscheck_alti"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["crosscheck_alti"], self.states["announce_checklist_completed"], self.can_transition_timeout, self.on_speak_action))

        self.fsm.add_transition(Transition(self.states["announce_checklist_completed"], self.states["finished"], self.is_not_failed, self.on_speak_action))
        
        
        self.fsm.add_transition(Transition(self.states["announce_checklist_completed"], self.states["announce_start_checklist_retrieve"], self.is_failed, lambda: self.on_speak_action("Start checklist: Engine Failure/Precautionary Shutdown Procedure and Checklist")))
        self.fsm.add_transition(Transition(self.states["announce_start_checklist_retrieve"], self.states["retrieve_checklist_start_checklist"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["retrieve_checklist_start_checklist"], self.states["throttle_affected_engine_cutoff"], self.can_transition_timeout, lambda: self.on_speak_action("Affected thrust lever, confirm and cutoff")))
        self.fsm.add_transition(Transition(self.states["throttle_affected_engine_cutoff"], self.states["caution_text_readout"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["caution_text_readout"], self.states["gen_switch_affected_side_off"], self.can_transition_timeout, lambda: self.on_speak_action("Gen switch affected side off")))
        self.fsm.add_transition(Transition(self.states["gen_switch_affected_side_off"], self.states["ignition_switch_affected_side_norm"], self.can_transition_timeout, lambda: self.on_speak_action("Gen switch affected side norm")))
        self.fsm.add_transition(Transition(self.states["ignition_switch_affected_side_norm"], self.states["electrical_load_reduce_as_required"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["electrical_load_reduce_as_required"], self.states["fuel_transfer_knob_as_required"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["fuel_transfer_knob_as_required"], self.states["verify_engine_fire_switch_affected_side"], self.can_transition_timeout, self.on_speak_action))
        self.fsm.add_transition(Transition(self.states["verify_engine_fire_switch_affected_side"], self.states["announce_current_checklist_completed"], self.can_transition_timeout, lambda: self.on_speak_action("Current checklist completed, next: single engine approach and landing")))
        self.fsm.add_transition(Transition(self.states["announce_current_checklist_completed"], self.states["finished"], self.can_transition_timeout, self.on_speak_action))
        # Adding transitions to the FSM
        
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

    def create_states_from_csv(self, csv_path):
        states = {}
        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                task_name = row['task_name'].strip()
                procedure_name = row['procedure_name'].strip()
                delay_before_action = row['time_init_action'].strip()
                delay_after_action = row['time_end_action'].strip()
                if task_name and task_name not in states:
                    states[task_name] = State(task_name, procedure_name, delay_before_action, delay_after_action)
        return states
    
    def is_started(self):
        if self.is_on_off[0]:
            return True
        return False
    
    
    def can_transition_timeout(self):
        if self.state_entry_time is None:
            return False #Not ready yet
        required = 0#float(self.fsm.current_state.delay_before_action) #get_time_end_action_for_state(self.fsm.current_state)
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
            #speak_wait("Airspeed's alive")
            return True
        return False

    def is_seventy_kts(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 70:
            #speak_wait("Seventy Knots")
            return True
        return False

    def is_v_one(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 90:
            #speak_wait("Rotate")
            return True
        return False

    def is_v_rotate(self):
        if self.agent.airspeed_i is not None and self.agent.airspeed_i >= 100:
            return True
        return False
    
    def is_pitch_maintained(self):
        if self.agent.pitch_i is not None and self.agent.pitch_i >= 7:
            #time.sleep(1)  # Simulate time to maintain pitch
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



    def can_finish(self):
        return self.should_finish[0]

    def on_start(self):
        print("Action: Starting...")
        current_state_name = self.fsm.current_state.name
        self.current_task = next(
            (task for task in self.tasks if task.get("task_name") == current_state_name), None
        )
        if self.current_task:
            speak_wait(f"{self.current_task['task_name']}")
        else:
            print(f"No task found for state: {current_state_name}")
        time.sleep(3)  # Simulate some startup delay
        
    def get_time_init_action_for_state(self, state_name):
        seconds = 1
        task = next((task for task in self.tasks if task.get("task_name", "").strip() == state_name.name), None)
        if task is not None:
            try:
                seconds = int(task.get("time_init_action")) +1 
            except (TypeError, ValueError):
                seconds = 1
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
            #print(f"Input {name} written to {value}")
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
            #print(f"Input {name} written to {value}")
            agent_object.l_throttle_i = value
        elif name == "r_throttle":
            #print(f"Input {name} written to {value}")
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
        #end_time = time.perf_counter()
        #elapsed_time = end_time - start_time
        #print(f"Elapsed time for processing {name}: {elapsed_time:.4f} seconds")

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

        # Loop to advance FSM every 3 seconds
        print(f"Current state: {self.fsm.current_state.name}")
        self.should_run[0] = True

    def on_speak_action(self, speak_message=None, sleep=True):
        self.state_entry_time = time.monotonic()
        #if sleep:
        #    time.sleep(self.get_time_init_action_for_state(self.fsm.current_state))
        print(f"Action: {self.fsm.current_state}")
        if speak_message:
            speak_wait(speak_message)
# Example usage
if __name__ == "__main__":
    agent = TarsAgent()
    agent.start()