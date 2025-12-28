import time

# Finite State Machine (FSM) implementation in Python
# This code defines a simple FSM with states, transitions, and actions.

class State:
    def __init__(self, procedure, classification, type, category, task_object, value, human_role=None, autonomy_role=None, information_requirement=None, interaction=None, delay_before_action: int | float | str = 0, delay_after_action: int | float | str = 0, callout=None, condition=None, condition_type=None, condition_function=None, monitor_scope=None):
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
        self.condition = condition  # None, False, or True
        self.condition_type = condition_type  # 'continuous', 'transition', or None
        self.condition_function = condition_function  # Name of condition function (string)
        self.monitor_scope = monitor_scope  # 'end_of_procedure', 'next_task', or None

    def __repr__(self):
        return f"State({self.procedure}, {self.classification}, {self.task_object}, {self.value}, condition={self.condition})"
    
    def __eq__(self, other):
        """Two states are equal if they have the same procedure, task_object, and value"""
        if not isinstance(other, State):
            return False
        return (self.procedure == other.procedure and 
                self.task_object == other.task_object and 
                self.value == other.value)
    
    def __hash__(self):
        """Hash based on procedure, task_object, and value for use in sets/dicts"""
        return hash((self.procedure, self.task_object, self.value))

class Transition:
    def __init__(self, from_state, to_state, condition, action=None, transition_action=None):
        self.from_state = from_state
        self.to_state = to_state
        self.condition = condition  # function returning True/False
        self.action = action        # function to call in next State (delay before/after handled in to_state)
        self.transition_action = transition_action  # function to call during transition (i.e. on entering to_state)
        self.action_performed = False  # track if action has been performed

class FiniteStateMachine:
    def __init__(self, initial_state):
        self.current_state = initial_state
        self.transitions = []
        self.dev_mode = False  # Flag to enable dev mode
        self.state_history = []  # Track state history for going back

    def add_transition(self, transition):
        if transition is None:
            print("WARNING: Attempted to add None transition to FSM!")
            import traceback
            traceback.print_stack()
            return
        if transition.from_state is None or transition.to_state is None:
            print(f"WARNING: Transition with None state detected! from_state={transition.from_state}, to_state={transition.to_state}")
            import traceback
            traceback.print_stack()
            return
        self.transitions.append(transition)
    
    def force_next_state(self):
        """
        DEV MODE: Force transition to the next state without checking conditions.
        Used for testing/debugging FSM flow.
        Returns True if transition occurred, False if no valid next state found.
        """
        # Find first transition from current state (regardless of condition)
        for transition in self.transitions:
            if transition.from_state == self.current_state:
                print(f"🔧 DEV MODE: Forcing transition from {self.current_state.procedure} {self.current_state.task_object} {self.current_state.value} to {transition.to_state.procedure} {transition.to_state.task_object} {transition.to_state.value}")
                
                # Save current state to history before changing
                self.state_history.append(self.current_state)
                
                # Execute transition_action if present (immediate)
                if hasattr(transition, 'transition_action') and transition.transition_action:
                    try:
                        print(f"  → Executing transition_action")
                        transition.transition_action()
                    except Exception as e:
                        print(f"ERROR in transition_action during force: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Change state
                old_state = self.current_state
                self.current_state = transition.to_state
                
                # Execute action if present (no delays in dev mode)
                if transition.action:
                    try:
                        print(f"  → Executing action")
                        transition.action()
                    except Exception as e:
                        print(f"ERROR in action during force: {e}")
                        import traceback
                        traceback.print_exc()
                
                print(f"✅ DEV MODE: Successfully forced to {self.current_state.procedure} {self.current_state.task_object} {self.current_state.value}")
                return True  # Successfully forced transition
        
        print(f"⚠️  DEV MODE: No transition found from {self.current_state.procedure} {self.current_state.task_object} {self.current_state.value}")
        return False  # No transition available
    
    def force_previous_state(self):
        """
        DEV MODE: Go back to the previous state in history.
        Does NOT execute any actions, just restores the state.
        Returns True if went back, False if no history available.
        """
        if not self.state_history:
            print(f"⚠️  DEV MODE: No previous state available (at beginning)")
            return False
        
        previous_state = self.state_history.pop()
        print(f"🔙 DEV MODE: Going back from {self.current_state.procedure} {self.current_state.task_object} {self.current_state.value} to {previous_state.procedure} {previous_state.task_object} {previous_state.value}")
        
        self.current_state = previous_state
        print(f"✅ DEV MODE: Successfully returned to {self.current_state.procedure} {self.current_state.task_object} {self.current_state.value}")
        return True
    
    def get_next_state_preview(self):
        """
        Get the next state that would be transitioned to (for UI preview).
        Returns the next state object or None.
        """
        for transition in self.transitions:
            if transition.from_state == self.current_state:
                return transition.to_state
        return None