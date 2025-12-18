# coding: utf-8

# =========================================================================
# echo_example.py
#
# Copyright (c) the Contributors as noted in the AUTHORS file.
# This file is part of Ingescape, see https://github.com/zeromq/ingescape.
# 
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
# =========================================================================
import ingescape as igs

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class Echo(metaclass=Singleton):
    def __init__(self):
        # inputs
        self.is_on_off_i = None
        self.airspeed_i = None
        self.altitude_i = None
        self.pitch_i = None
        self.roll_i = None
        self.heading_i = None
        self.control_rudder_i = None
        self.vertical_speed_i = None
        self.control_throttle_i = None
        self.control_flaps_i = None
        self.control_gear_i = None
        self.speed_brakes_i = None
        self.park_brakes_i = None
        self.l_throttle_i = None
        self.r_throttle_i = None
        self.cas_i = None
        self.n1_match_bug_i = None
        self.e1_n1_percent_i = None
        self.e2_n1_percent_i = None
        self.slip_i = None
        self.engine_fire_l_i = None
        self.engine_fire_r_i = None
        self.pax_safety_i = None
        self.master_warning_i = None
        self.master_caution_i = None
        self.flight_director_i = None
        self.speed_mode_i = None
        self.heading_mode_i = None
        self.fuel_boost_l_i = None
        self.fuel_boost_r_i = None
        self.test_knob_i = None
        self.autopilot_heading_set_i = None
        self.yaw_damper_i = None
        self.l_ign_switch_i = None
        self.r_ign_switch_i = None
        self.l_gen_switch_i = None
        self.r_gen_switch_i = None
        self.transfer_knob_i = None
        self.trim_rudder_i = None
        self.cabin_altitude_i = None
        self.l_gen_load_i = None
        self.r_gen_load_i = None
        self.l_bottle_arm_i = None
        self.r_bottle_arm_i = None
        self.speech_input_i = None  # For speech recognition input
        self.pitot_heat_i = None  # Pitot heat on/off
        self.latitude_i = None  # Latitude
        self.longitude_i = None  # Longitude
        self.anti_coll_lights_i = None  # Anti-collision lights on/off

        # outputs
        self.pax_safety_o = None
        self.flight_director_o = None
        self.speed_mode_o = None
        self.heading_mode_o = None
        self.autopilot_master_o = None
        self.autopilot_heading_set_o = None
        self.autopilot_state_o = None
        self.yaw_damper_o = None
        self.trim_rudder_o = None
        self.request_takeoff_clearance_o = None
        self.declare_mayday_o = None
        self.declare_pan_o = None
        self.request_vectors_o = None
        self.tts_request_o = None  # Text to send to TTS agent
        self.alt_sel_o = None  # Altitude select in feet
        
        # TTS agent status (only need is_speaking to know when speech finishes)
        self.tts_is_speaking_i = None
        
    # outputs
    @property
    def pax_safetyO(self):
        return self._pax_safetyO
    @pax_safetyO.setter
    def pax_safetyO(self, value):
        self._pax_safetyO = value
        if self._pax_safetyO is not None:
            igs.output_set_double("pax_safety", self._pax_safetyO)
            
    @property
    def flight_directorO(self):
        return self._flight_directorO
    @flight_directorO.setter
    def flight_directorO(self, value):
        self._flight_directorO = value
        if self._flight_directorO is not None:
            print(f"Setting flight_director to {self._flight_directorO}")
            igs.output_set_double("flight_director", self._flight_directorO)
    
    @property
    def speed_modeO(self):
        return self._speed_modeO
    @speed_modeO.setter
    def speed_modeO(self, value):
        self._speed_modeO = value
        if self._speed_modeO is not None:
            igs.output_set_double("speed_mode", self._speed_modeO)
    
    @property
    def heading_modeO(self):
        return self._heading_modeO
    @heading_modeO.setter
    def heading_modeO(self, value):
        self._heading_modeO = value
        if self._heading_modeO is not None:
            igs.output_set_double("heading_mode", self._heading_modeO)
            
    @property
    def autopilot_masterO(self):
        return self._autopilot_masterO
    @autopilot_masterO.setter
    def autopilot_masterO(self, value):
        self._autopilot_masterO = value
        if self._autopilot_masterO is not None:
            igs.output_set_double("autopilot_master", self._autopilot_masterO)
    
    @property
    def autopilot_heading_setO(self):
        return self._autopilot_heading_setO
    @autopilot_heading_setO.setter
    def autopilot_heading_setO(self, value):
        self._autopilot_heading_setO = value
        if self._autopilot_heading_setO is not None:
            igs.output_set_double("autopilot_heading_set", self._autopilot_heading_setO)
    
    @property
    def autopilot_stateO(self):
        return self._autopilot_stateO
    @autopilot_stateO.setter
    def autopilot_stateO(self, value):
        self._autopilot_stateO = value
        if self._autopilot_stateO is not None:
            igs.output_set_double("autopilot_state", self._autopilot_stateO)
    
    @property
    def yaw_damperO(self):
        return self._yaw_damperO
    @yaw_damperO.setter
    def yaw_damperO(self, value):
        self._yaw_damperO = value
        if self._yaw_damperO is not None:
            igs.output_set_double("yaw_damper", self._yaw_damperO)

    @property
    def trim_rudderO(self):
        return self._trim_rudderO
    @trim_rudderO.setter
    def trim_rudderO(self, value):
        self._trim_rudderO = value
        if self._trim_rudderO is not None:
            igs.output_set_double("trim_rudder", self._trim_rudderO)
    
    @property
    def request_takeoff_clearanceO(self):
        return self._request_takeoff_clearanceO
    @request_takeoff_clearanceO.setter
    def request_takeoff_clearanceO(self, value):
        self._request_takeoff_clearanceO = value
        if self._request_takeoff_clearanceO is not None:
            igs.output_set_impulsion("request_takeoff_clearance")
    
    @property
    def declare_maydayO(self):
        return self._declare_maydayO
    @declare_maydayO.setter
    def declare_maydayO(self, value):
        self._declare_maydayO = value
        if self._declare_maydayO is not None:
            igs.output_set_impulsion("declare_mayday")
            
    @property
    def declare_panO(self):
        return self._declare_panO
    @declare_panO.setter
    def declare_panO(self, value):
        self._declare_panO = value
        if self._declare_panO is not None:
            igs.output_set_impulsion("declare_pan")
            
    @property
    def request_vectorsO(self):
        return self._request_vectorsO
    @request_vectorsO.setter
    def request_vectorsO(self, value):
        self._request_vectorsO = value
        if self._request_vectorsO is not None:
            igs.output_set_impulsion("request_vectors")
    
    @property
    def alt_selO(self):
        return self._alt_selO
    @alt_selO.setter
    def alt_selO(self, value):
        self._alt_selO = value
        if self._alt_selO is not None:
            igs.output_set_int("alt_sel", self._alt_selO)

    # services
    def receive_values(self, sender_agent_name, sender_agent_uuid, boolV, integer, double, string, data, token, my_data):
        igs.info(f"Service receive_values called by {sender_agent_name} ({sender_agent_uuid}) with argument_list {boolV, integer, double, string, data} and token '{token}''")

    #def send_values(self, sender_agent_name, sender_agent_uuid, token, my_data):
        #print(f"Service send_values called by {sender_agent_name} ({sender_agent_uuid}), token '{token}' sending values : {self.boolO, self.integerO, self.doubleO, self.stringO, self.dataO}")
        #igs.service_call(sender_agent_uuid, "receive_values", self.boolO, self.integerO, self.doubleO, self.stringO, self.dataO, token)