"""
FSM Worker
Handles Finite State Machine execution in a separate thread
Manages state transitions, condition monitoring, and action execution
"""

import time
import traceback
from typing import Callable, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from Core.agent import TarsAgent

class FSMWorker:
    """
    Worker class for FSM execution
    Uses callback pattern instead of Qt Signals for decoupling from UI framework
    """
    
    def __init__(self, agent: 'TarsAgent'):
        """
        Initialize FSM Worker
        
        Args:
            agent: TarsAgent instance containing the FSM
        """
        self.agent = agent
        self.current_state = None
        
        # Performance monitoring
        self.performance_metrics = {}
        self.loop_count = 0
        self.last_performance_report = time.perf_counter()
        
        # Action inhibition flag
        self.skip_current_action = False
        
        # Active condition monitoring registry
        # Dict: state_key -> monitoring_info
        self.active_monitored_conditions = {}
        self.current_procedure = None  # Track current procedure for scope management
        
        # Control flags
        self.should_stop = False
        
        # Track task_acked state for detecting check button presses
        self.last_task_acked_state = False
        
        # Callbacks for UI updates (replaces Qt Signals)
        self._state_changed_callback: Optional[Callable] = None
        self._action_about_to_fire_callback: Optional[Callable] = None
        self._condition_violated_callback: Optional[Callable] = None
        self._condition_restored_callback: Optional[Callable] = None
    
    # Callback registration methods
    def set_state_changed_callback(self, callback: Callable[[Any], None]):
        """Register callback for state changes"""
        self._state_changed_callback = callback
    
    def set_action_about_to_fire_callback(self, callback: Callable[[Any], None]):
        """Register callback for action about to fire"""
        self._action_about_to_fire_callback = callback
    
    def set_condition_violated_callback(self, callback: Callable[[Any, str], None]):
        """Register callback for condition violations"""
        self._condition_violated_callback = callback
    
    def set_condition_restored_callback(self, callback: Callable[[Any, str], None]):
        """Register callback for condition restorations"""
        self._condition_restored_callback = callback
    
    # Performance monitoring
    def start_performance_timer(self, action_name: str) -> float:
        """Start timing for a specific action"""
        return time.perf_counter()

    def stop_performance_timer(self, action_name: str, start_time: float) -> float:
        """Stop timing and record the result"""
        elapsed = time.perf_counter() - start_time
        if action_name not in self.performance_metrics:
            self.performance_metrics[action_name] = []
        self.performance_metrics[action_name].append(elapsed)
        return elapsed

    def print_performance_report(self):
        """Print performance report every 10 seconds"""
        print(f"\n=== FSM Performance Report (Loops: {self.loop_count}) ===")
        for action, times in self.performance_metrics.items():
            if times:
                avg_time = sum(times) / len(times)
                print(f"{action}: avg={avg_time*1000:.2f}ms, count={len(times)}, min={min(times)*1000:.2f}ms, max={max(times)*1000:.2f}ms")
        
        # Reset counters
        self.performance_metrics.clear()
        self.loop_count = 0
    
    def cancel_current_action(self):
        """Cancel/skip the current action execution"""
        self.skip_current_action = True
    
    def stop(self):
        """Stop the FSM worker loop"""
        self.should_stop = True
    
    # Condition monitoring
    def add_to_monitoring(self, state):
        """Add state to continuous condition monitoring"""
        # Only monitor states with 'continuous' condition type
        if state.condition_type != 'continuous' or not state.condition_function:
            return
        
        state_key = (state.procedure, state.task_object, state.value)
        
        # Get condition function by name from agent
        try:
            condition_func = getattr(self.agent, state.condition_function)
        except AttributeError:
            print(f"Warning: Condition function '{state.condition_function}' not found in agent")
            return
        
        # Evaluate initial value
        try:
            initial_value = condition_func()
        except Exception as e:
            print(f"Error evaluating initial condition {state.condition_function}: {e}")
            initial_value = None
        
        # Set state.condition to initial value
        state.condition = initial_value
        
        self.active_monitored_conditions[state_key] = {
            'state': state,
            'condition_func_name': state.condition_function,
            'condition_func': condition_func,
            'last_value': initial_value,
            'monitor_scope': state.monitor_scope,
            'procedure': state.procedure
        }
        
        print(f"📊 Monitoring: {state.procedure} - {state.task_object} - {state.condition_function} = {initial_value}")
    
    def remove_from_monitoring(self, state_key):
        """Stop monitoring a condition"""
        if state_key in self.active_monitored_conditions:
            monitor_info = self.active_monitored_conditions[state_key]
            print(f"🛑 Stop monitoring: {monitor_info['procedure']} - {monitor_info['state'].task_object}")
            del self.active_monitored_conditions[state_key]
    
    def cleanup_monitoring_for_scope(self, scope_type, current_state):
        """Remove conditions from monitoring based on scope"""
        to_remove = []
        
        for state_key, monitor_info in self.active_monitored_conditions.items():
            monitor_scope = monitor_info['monitor_scope']
            
            if scope_type == 'next_task' and monitor_scope == 'next_task':
                # Remove conditions that should only be monitored until next task
                to_remove.append(state_key)
            
            elif scope_type == 'procedure_change':
                # Remove conditions when procedure changes
                if monitor_scope == 'end_of_procedure' and monitor_info['procedure'] != current_state.procedure:
                    to_remove.append(state_key)
        
        for state_key in to_remove:
            self.remove_from_monitoring(state_key)

    def run(self):
        """
        Main FSM execution loop
        This method runs continuously until stopped
        """
        fsm = self.agent.fsm
        
        while not self.should_stop and not self.agent.is_interrupted:
            # Performance monitoring
            self.loop_count += 1
            current_time = time.perf_counter()
            
            # Print performance report every 10 seconds
            if current_time - self.last_performance_report >= 10.0:
                #self.print_performance_report()
                self.last_performance_report = current_time

            # Check transitions with performance timing
            transition_start = self.start_performance_timer("transition_check")
            transition_found = False
            
            for t in fsm.transitions:
                if t.from_state == fsm.current_state:
                    # Time the condition check
                    condition_start = self.start_performance_timer("condition_check")
                    condition_result = t.condition()
                    condition_time = self.stop_performance_timer("condition_check", condition_start)
                    
                    # Log slow conditions
                    if condition_time > 0.1:  # 100ms threshold
                        print(f"WARNING: Slow condition check for {t.from_state.procedure} {t.from_state.task_object} {t.from_state.value} -> {t.to_state.procedure} {t.to_state.task_object} {t.to_state.value}: {condition_time*1000:.2f}ms")
                    
                    if condition_result:
                        # State transition
                        transition_time = self.stop_performance_timer("transition_check", transition_start)
                        print(f"State transition: {fsm.current_state.procedure} {fsm.current_state.task_object} {fsm.current_state.value} -> {t.to_state.procedure} {t.to_state.task_object} {t.to_state.value} (check took {transition_time*1000:.2f}ms)")
                        
                        # CONDITION MONITORING: Cleanup for 'next_task' scope
                        self.cleanup_monitoring_for_scope('next_task', t.to_state)
                        
                        # CONDITION MONITORING: Check if procedure changed
                        if self.current_procedure and self.current_procedure != t.to_state.procedure:
                            self.cleanup_monitoring_for_scope('procedure_change', t.to_state)
                        
                        self.current_procedure = t.to_state.procedure
                        
                        # === Execute transition_action IMMEDIATELY (before state change, no delays) ===
                        if hasattr(t, 'transition_action') and t.transition_action and not getattr(t, 'action_performed', False):
                            print(f"⚡ Executing transition_action (immediate)")
                            trans_action_start = self.start_performance_timer("transition_action")
                            try:
                                t.transition_action()
                            except Exception as e:
                                print(f"ERROR in transition_action: {e}")
                                traceback.print_exc()
                            trans_action_time = self.stop_performance_timer("transition_action", trans_action_start)
                            print(f"  → transition_action took {trans_action_time*1000:.2f}ms")
                        
                        # Change state
                        fsm.current_state = t.to_state
                        self.current_state = fsm.current_state
                        
                        # Reset acknowledgment and approval flags after successful transition
                        # This prevents conditions from being stuck True across multiple states
                        if hasattr(self.agent, 'task_acked'):
                            self.agent.task_acked[0] = False
                        
                        # Reset single approval flag (consumed by the transition)
                        if hasattr(self.agent, 'task_approval_status'):
                            from Core.agent import ApprovalStatus
                            self.agent.task_approval_status[0] = ApprovalStatus.NOT_ANSWERED
                        
                        # Notify via callback instead of Qt Signal
                        if self._state_changed_callback:
                            self._state_changed_callback(fsm.current_state)
                        
                        # CONDITION MONITORING: Add new state to monitoring if it has continuous condition
                        self.add_to_monitoring(fsm.current_state)
                        
                        # === Only handle delays if there's an action ===
                        if t.action:
                            # Wait before action - use agent's event for synchronization
                            delay = self.get_delay_before_action(fsm.current_state)
                            if delay > 0:
                                print(f"⏳ Waiting {delay}s before action (delay_before_action)")
                                # Use agent's countdown event for waiting
                                if hasattr(self.agent, 'countdown_completion_event') and self.agent.countdown_completion_event is not None:
                                    self.agent.countdown_completion_event.clear()
                                    self.agent.countdown_completion_event.wait(timeout=delay + 2)
                                else:
                                    # Fallback to simple sleep
                                    time.sleep(delay)
                            
                            # Only emit callback if action is not being skipped
                            if not self.skip_current_action:
                                # Notify right before action fires (after countdown completes)
                                if self._action_about_to_fire_callback:
                                    self._action_about_to_fire_callback(fsm.current_state)
                            
                            # Check if action should be skipped (user cancelled)
                            if self.skip_current_action:
                                print(f"⏭️ Skipping action for {fsm.current_state.task_object} - user reclaimed task")
                                self.skip_current_action = False  # Reset flag
                                action_result = False  # No TTS to wait for
                            else:
                                print(f"🎬 Executing action (with delays)")
                                action_start = self.start_performance_timer("action_execution")
                                try:
                                    action_result = t.action()
                                except Exception as e:
                                    print(f"ERROR in action: {e}")
                                    traceback.print_exc()
                                    action_result = False
                                action_time = self.stop_performance_timer("action_execution", action_start)
                                print(f"  → action took {action_time*1000:.2f}ms")
                            
                            # If it was a speech action, wait for TTS to complete
                            if action_result is True and self.agent.tts_completion_event:
                                print(f"⏳ Waiting for TTS to complete...")
                                wait_start = time.time()
                                self.agent.tts_completion_event.wait(timeout=30)  # Block until TTS finishes (30s max)
                                wait_time = time.time() - wait_start
                                print(f"✅ TTS completed after {wait_time:.2f}s")
                            
                            # Wait after action
                            delay = self.get_delay_after_action(fsm.current_state)
                            if delay and delay > 0:
                                print(f"⏳ Waiting {delay}s after action (delay_after_action)")
                                time.sleep(delay + 0.2)  # + 0.2 delay for UI
                        
                        # Reset action_performed flag for next use
                        if hasattr(t, 'action_performed'):
                            t.action_performed = False
                        
                        transition_found = True
                        break
            
            if not transition_found:
                self.stop_performance_timer("transition_check", transition_start)
                
                # Check if user just pressed "check" but conditions not satisfied
                current_acked = self.agent.task_acked[0] if hasattr(self.agent, 'task_acked') else False
                
                if current_acked and not self.last_task_acked_state:
                    # User just pressed check! But we didn't transition - conditions not satisfied
                    self._handle_failed_acknowledgment(fsm.current_state)
                
                self.last_task_acked_state = current_acked
            
            # Small sleep to prevent tight loop (allows other operations to run)
            time.sleep(0.05)  # 50ms sleep = 20 checks per second
            
    def _handle_failed_acknowledgment(self, current_state):
        """
        Called when user presses check but transition condition is not satisfied.
        Analyzes the transition condition and sends feedback to user.
        """
        fsm = self.agent.fsm
        
        # Find the expected transition from current state
        expected_transition = None
        for t in fsm.transitions:
            if t.from_state == current_state:
                expected_transition = t
                break
        
        if not expected_transition:
            return  # No transition defined, nothing to check
        
        # Check if to_state has a condition_function defined
        to_state = expected_transition.to_state
        
        try:
            if to_state.condition_function:
                # Try to evaluate the condition function
                condition_func = getattr(self.agent, to_state.condition_function, None)
                if condition_func:
                    try:
                        condition_result = condition_func()
                        if not condition_result:
                            # Found it! The condition function is not satisfied
                            # Format condition name nicely for user
                            condition_name = to_state.condition_function.replace('is_', '').replace('_', ' ')
                            message = f"Cannot proceed: {condition_name} not satisfied yet."
                            self._send_interaction_message(message)
                            print(f"ℹ️  User checked but condition '{to_state.condition_function}' = False")
                            return
                    except Exception as e:
                        print(f"Error evaluating condition {to_state.condition_function}: {e}")
            
            # Generic message if we can't determine specific condition
            message = "Task acknowledged, but transition conditions not yet satisfied. Please verify requirements."
            self._send_interaction_message(message)
            print(f"ℹ️  User checked but conditions not satisfied for transition")
            
        except Exception as e:
            print(f"Error in _handle_failed_acknowledgment: {e}")
    
    def _send_interaction_message(self, message: str):
        """Send interaction message to GUI via Ingescape"""
        try:
            from Core.message_protocol import create_interaction_message
            import ingescape as igs
            
            msg = create_interaction_message("", message)
            igs.output_set_string("interaction_message", msg)
        except Exception as e:
            print(f"Error sending interaction message: {e}")
    
    def get_delay_before_action(self, state) -> float:
        """Get delay before action from state"""
        delay = getattr(state, "delay_before_action", 0)
        if delay is None:
            delay = 0
        elif isinstance(delay, str):
            if delay.lower() in ['is_acked', 'is_sensed']:
                # Acknowledgment-based or condition-based waiting
                delay = 0
            else:
                try:
                    delay = float(delay)
                except ValueError:
                    delay = 0
        if delay and delay > 0:
            print(f"waiting for {delay} seconds before executing action for state ({state.procedure}, {state.task_object}, {state.value})")
        return delay
    
    def get_delay_after_action(self, state) -> float:
        """Get delay after action from state"""
        delay = getattr(state, "delay_after_action", 0)
        if delay is None:
            delay = 0
        elif isinstance(delay, str):
            if delay.lower() in ['is_acked', 'is_sensed']:
                # Acknowledgment-based or condition-based waiting
                delay = 0
            else:
                try:
                    delay = float(delay)
                except ValueError:
                    delay = 0
        if delay and delay > 0:
            print(f"waiting for {delay} seconds after executing action for state ({state.procedure}, {state.task_object}, {state.value})")
        return delay
