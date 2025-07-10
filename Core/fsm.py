import time

# Finite State Machine (FSM) implementation in Python
# This code defines a simple FSM with states, transitions, and actions.

class State:
    def __init__(self, name, procedure_name, delay_before_action, delay_after_action):
        """ Initializes a state in the FSM.
        :param name: Name of the state
        :param procedure_name: Optional name of the procedure associated with this state
        :param delay_before_action: Optional delay before performing the action associated with this state
        """
        self.name = name
        self.procedure_name = procedure_name  # name of the procedure associated with this state
        self.delay_before_action = delay_before_action  # seconds before action is performed
        self.delay_after_action = delay_after_action

    def __repr__(self):
        return f"State({self.name})"

class Transition:
    def __init__(self, from_state, to_state, condition, action=None):
        self.from_state = from_state
        self.to_state = to_state
        self.condition = condition  # function returning True/False
        self.action = action        # function to call on transition
        self.action_performed = False  # NEW: track if action has been performed

class FiniteStateMachine:
    def __init__(self, initial_state):
        self.current_state = initial_state
        self.transitions = []

    def add_transition(self, transition):
        self.transitions.append(transition)