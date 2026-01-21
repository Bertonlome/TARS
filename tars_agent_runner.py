#!/usr/bin/env python3
"""
TARS Agent Runner - Standalone process for TARS Agent
Runs independently of the GUI to allow separate Ingescape agent registration
"""

import signal
import sys
import os
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from Core.agent import TarsAgent
import platform

# Choose sensible default network device name depending on host OS
if platform.system() == "Linux":
    DEFAULT_DEVICE = "wlp0s20f3"
elif platform.system() == "Windows":
    DEFAULT_DEVICE = "Wi-Fi"
else:
    DEFAULT_DEVICE = "wlps"

# Global agent instance for signal handling
tars_agent = None
is_interrupted = False

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global is_interrupted, tars_agent
    print("\n🛑 TARS Agent interrupted by user (Ctrl+C)")
    is_interrupted = True
    if tars_agent:
        tars_agent.is_interrupted = True

def main():
    global tars_agent, is_interrupted
    
    print("==================================================")
    print("Starting TARS Agent (Standalone Process)")
    print("==================================================")
    
    # Parse command-line arguments
    agent_name = "TARS Agent"
    device = DEFAULT_DEVICE
    port = 5670
    verbose = False
    
    if len(sys.argv) > 1:
        device = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    if len(sys.argv) > 3:
        agent_name = sys.argv[3]
    if len(sys.argv) > 4:
        verbose = sys.argv[4].lower() in ('true', '1', 'yes')
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start TARS Agent
    tars_agent = TarsAgent(
        agent_name=agent_name,
        device=device,
        port=port,
        verbose=verbose
    )
    
    print(f"📡 Starting TARS Agent on {device}:{port}")
    tars_agent.start()
    
    print("✅ TARS Agent is running. Press Ctrl+C to exit.")
    
    # Create FSMWorker to run the FSM
    from Core.fsm_worker import FSMWorker as FSMWorkerCore
    import threading
    
    # Set up threading events for FSM synchronization
    countdown_event = threading.Event()
    countdown_event.set()  # Initially set (no countdown in progress)
    tars_agent.countdown_completion_event = countdown_event
    
    tts_event = threading.Event()
    tts_event.set()  # Initially set (no TTS in progress)
    tars_agent.tts_completion_event = tts_event

    # Set up observer for TTS speaking status from TTS agent
    import ingescape as igs
    
    def on_tts_speaking_changed(ioType, name, valueType, value, myData):
        """Called when TTS agent's is_speaking output changes"""
        if tars_agent is None:
            return
            
        # Track when TTS speaking transitions from True to False
        was_speaking = tars_agent.tts_speaking_before
        is_speaking = value
        
        tars_agent.tts_speaking_before = is_speaking
        
        # If transitioned from speaking to not speaking, signal completion
        if was_speaking and not is_speaking:
            print(f"📥 TTS finished (detected via Ingescape)")
            if tars_agent.tts_completion_event:
                tars_agent.tts_completion_event.set()
    
    igs.observe_input("tts_is_speaking", on_tts_speaking_changed, None)
    
    # Initialize outputs after a short delay to ensure agent is fully started
    def initialize_outputs():
        """Initialize Ingescape outputs once agent is ready"""
        igs.output_set_string("current_procedure", "IDLE")
        igs.output_set_string("current_task_object", "Idle")
        igs.output_set_string("current_task_value", "Waiting")
        igs.output_set_string("current_task_autonomy_role", "None")
        igs.output_set_string("current_task_human_role", "None")
        print(f"📤 Published current_state: IDLE - Idle")
    
    # Schedule output initialization for 1 second after agent start
    timer = threading.Timer(1.0, initialize_outputs)
    timer.start()
    
    # Set up FSM worker callbacks to publish via Ingescape
    def on_state_changed(state):
        """Publish state change via Ingescape"""
        from Core.message_protocol import encode_state_to_json
        import ingescape as igs
        
        try:
            # Publish current state
            state_json = encode_state_to_json(state)
            igs.output_set_string("current_state", state_json)
            igs.output_set_string("current_procedure", state.procedure)
            igs.output_set_string("interaction_message", "")
            igs.output_set_string("current_task_object", state.task_object)
            igs.output_set_string("current_task_value", str(state.value))
            igs.output_set_string("current_task_autonomy_role", str(state.autonomy_role))
            igs.output_set_string("current_task_human_role", str(state.human_role))
            print(f"📤 Published current_state: {state.procedure} - {state.task_object}")
            
            # Publish previous state (from FSM history)
            if tars_agent is not None:
                if hasattr(tars_agent.fsm, 'state_history') and len(tars_agent.fsm.state_history) > 0:
                    previous_state = tars_agent.fsm.state_history[-1]
                    previous_json = encode_state_to_json(previous_state)
                    igs.output_set_string("previous_state", previous_json)
                    print(f"📤 Published previous_state: {previous_state.procedure} - {previous_state.task_object}")
            
            # Publish next state (find transition from current state)
            next_state = None
            if tars_agent is not None:
                for transition in tars_agent.fsm.transitions:
                    if transition is None:  # Skip None transitions
                        continue
                    if transition.from_state == state:
                        next_state = transition.to_state
                        break
            
            if next_state:
                next_json = encode_state_to_json(next_state)
                igs.output_set_string("next_state", next_json)
                print(f"📤 Published next_state: {next_state.procedure} - {next_state.task_object}")
                
                # Publish countdown values
                # Current countdown: delay_before_action
                try:
                    current_delay = state.delay_before_action
                    if current_delay and str(current_delay).replace('.','',1).isdigit():
                        current_seconds = int(float(current_delay))
                        igs.output_set_int("countdown_current", current_seconds)
                        igs.output_set_int("countdown_max_current", current_seconds)
                        print(f"📤 Published countdown_current: {current_seconds}s")
                except (ValueError, TypeError, AttributeError):
                    igs.output_set_int("countdown_current", 0)
                    igs.output_set_int("countdown_max_current", 0)
                
                # Next countdown: current delay_after + next delay_before
                try:
                    current_delay_after = state.delay_after_action
                    next_delay_before = next_state.delay_before_action
                    
                    # Calculate total if numeric
                    current_after = int(float(current_delay_after)) if current_delay_after and str(current_delay_after).replace('.','',1).isdigit() else 0
                    next_before = int(float(next_delay_before)) if next_delay_before and str(next_delay_before).replace('.','',1).isdigit() else 0
                    total_next = current_after + next_before
                    
                    igs.output_set_int("countdown_next", total_next)
                    igs.output_set_int("countdown_max_next", total_next)
                    print(f"📤 Published countdown_next: {total_next}s")
                except (ValueError, TypeError, AttributeError):
                    igs.output_set_int("countdown_next", 0)
                    igs.output_set_int("countdown_max_next", 0)
            
        except Exception as e:
            print(f"Error publishing state: {e}")
            import traceback
            traceback.print_exc()
    
    def on_action_about_to_fire(state):
        """Publish action about to fire notification via Ingescape"""
        from Core.message_protocol import encode_state_to_json
        try:
            state_json = encode_state_to_json(state)
            import ingescape as igs
            igs.output_set_string("action_about_to_fire", state_json)
            print(f"📤 Published action about to fire: {state.procedure} - {state.task_object}")
        except Exception as e:
            print(f"Error publishing action about to fire: {e}")
    
    def on_condition_violated(state, condition_name):
        """Publish condition violation via Ingescape"""
        from Core.message_protocol import create_condition_message
        try:
            import ingescape as igs
            condition_json = create_condition_message(
                state.procedure,
                state.task_object,
                state.value,
                condition_name
            )
            igs.output_set_string("condition_violated", condition_json)
            print(f"📤 Published condition violated: {state.procedure} - {state.task_object} - {condition_name}")
        except Exception as e:
            print(f"Error publishing condition violated: {e}")
    
    def on_condition_restored(state, condition_name):
        """Publish condition restoration via Ingescape"""
        from Core.message_protocol import create_condition_message
        try:
            import ingescape as igs
            condition_json = create_condition_message(
                state.procedure,
                state.task_object,
                state.value,
                condition_name
            )
            igs.output_set_string("condition_restored", condition_json)
            print(f"📤 Published condition restored: {state.procedure} - {state.task_object} - {condition_name}")
        except Exception as e:
            print(f"Error publishing condition restored: {e}")
    
    # Start FSM worker in background thread  
    fsm_worker = FSMWorkerCore(tars_agent)
    fsm_worker.set_state_changed_callback(on_state_changed)
    fsm_worker.set_action_about_to_fire_callback(on_action_about_to_fire)
    fsm_worker.set_condition_violated_callback(on_condition_violated)
    fsm_worker.set_condition_restored_callback(on_condition_restored)
    
    # Store fsm_worker reference on agent for task cancellation
    tars_agent.fsm_worker = fsm_worker
    
    fsm_thread = threading.Thread(target=fsm_worker.run, daemon=True)
    fsm_thread.start()
    print("✅ FSM Worker started in background thread")
    
    # Keep the process alive
    try:
        while not is_interrupted:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n🛑 TARS Agent shutting down...")
    
    print("👋 TARS Agent stopped")
    return 0

if __name__ == "__main__":
    sys.exit(main())
