# coding: utf-8

# =========================================================================
# echo_tts.py
#
# TTS Agent Echo Class for Ingescape Integration
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
        self.text_to_speak_i = None

        # outputs
        self._is_speaking_o = None
        self._current_text_o = None
        
    # outputs
    @property
    def is_speaking_o(self):
        return self._is_speaking_o
    
    @is_speaking_o.setter
    def is_speaking_o(self, value):
        self._is_speaking_o = value
        if self._is_speaking_o is not None:
            igs.output_set_bool("is_speaking", self._is_speaking_o)
    
    @property
    def current_text_o(self):
        return self._current_text_o
    
    @current_text_o.setter
    def current_text_o(self, value):
        self._current_text_o = value
        if self._current_text_o is not None:
            igs.output_set_string("current_text", self._current_text_o)
