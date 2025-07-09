import time

# Finite State Machine (FSM) implementation in Python
# This code defines a simple FSM with states, transitions, and actions.


class State:
    def __init__(self, name, procedure_name, delay_before_action):
        """ Initializes a state in the FSM.
        :param name: Name of the state
        :param procedure_name: Optional name of the procedure associated with this state
        :param delay_before_action: Optional delay before performing the action associated with this state
        """
        self.name = name
        self.procedure_name = procedure_name  # name of the procedure associated with this state
        self.delay_before_action = delay_before_action  # seconds before action is performed

    def __repr__(self):
        return f"State({self.name})"

class Transition:
    def __init__(self, from_state, to_state, condition, action=None):
        self.from_state = from_state
        self.to_state = to_state
        self.condition = condition  # function returning True/False
        self.action = action        # function to call on transition

class FiniteStateMachine:
    def __init__(self, initial_state):
        self.current_state = initial_state
        self.transitions = []
        self.state_action_performed = {}

    def add_transition(self, transition):
        self.transitions.append(transition)

    def run(self):
        print(f"Starting FSM in state: {self.current_state}")
        while True:
            transitioned = False
            for t in self.transitions:
                if t.from_state == self.current_state and t.condition() and not self.state_action_performed.get(self.current_state, False):
                        self.state_action_performed[self.current_state] = True
                        print(f"Transition: {t.from_state} -> {t.to_state}")
                        if t.action:
                            t.action()
                        self.current_state = t.to_state
                        transitioned = True
                        break
            if not transitioned:
                print(f"No transition from {self.current_state}, stopping.")
                time.sleep(3)
                break
        print(f"FSM ended in state: {self.current_state}")