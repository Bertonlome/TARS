import time

# Finite State Machine (FSM) implementation in Python
# This code defines a simple FSM with states, transitions, and actions.

class State:
    def __init__(self, procedure, classification, type, category, task_object, value, human_role=None, autonomy_role=None, information_requirement=None, interaction=None, delay_before_action=0, delay_after_action=0, callout=None):
        self.procedure = procedure
        self.classification = classification
        self.type = type
        self.category = category
        self.task_object = task_object
        self.value = value
        self.human_role = human_role
        self.autonomy_role = autonomy_role
        self.information_requirement = information_requirement
        self.interaction = interaction
        self.delay_before_action = delay_before_action
        self.delay_after_action = delay_after_action
        self.callout = callout

    def __repr__(self):
        return f"State({self.procedure}, {self.classification}, {self.type}, {self.category}, {self.task_object}, {self.value}, {self.human_role}, {self.autonomy_role}, {self.information_requirement}, {self.interaction}, {self.delay_before_action}, {self.delay_after_action}, {self.callout})"

class Transition:
    def __init__(self, from_state, to_state, condition, action=None):
        self.from_state = from_state
        self.to_state = to_state
        self.condition = condition  # function returning True/False
        self.action = action        # function to call on transition
        self.action_performed = False  # track if action has been performed

class FiniteStateMachine:
    def __init__(self, initial_state):
        self.current_state = initial_state
        self.transitions = []

    def add_transition(self, transition):
        self.transitions.append(transition)