#!/usr/bin/env python3
"""
TARS Agent Runner - Standalone process for TARS Agent
Runs independently of the GUI to allow separate Ingescape agent registration
"""

import signal
import sys
import os
import time
import threading
import inspect
import re
from pathlib import Path
import soundfile as sf
import sounddevice as sd

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


# ---------------------------------------------------------------------------
# Transition-kind inference
# Determines whether the outgoing transition condition, evaluated for the
# current autonomy_role, resolves to only is_acked() ("waiting") or requires
# a real environmental/sensor check ("sensing").
# ---------------------------------------------------------------------------

def _expr_is_acked_only(expr: str) -> bool:
    """Return True if *expr* contains only is_acked() and/or allow_transition()."""
    cleaned = re.sub(r'self\.is_acked\s*\(\s*\)', '', expr)
    cleaned = re.sub(r'self\.allow_transition\s*\(\s*\)', '', cleaned)
    cleaned = re.sub(r'\b(?:and|or|not|if|else)\b', '', cleaned)
    # Any remaining `word(` means a real sensor/check function — do NOT strip
    # parentheses before this check, otherwise the search always misses.
    return not bool(re.search(r'\w+\s*\(', cleaned))


def _extract_ternary_true_expr(body: str):
    """
    Extract the true-expression from a Python ternary  TRUE_EXPR if COND else FALSE_EXPR.
    Returns the substring before the first top-level ' if ', or None if not found.
    """
    depth = 0
    for i, ch in enumerate(body):
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        elif depth == 0 and body[i:i + 4] == ' if ':
            return body[:i].strip()
    return None


def _role_satisfies_if_branch(body: str, role) -> bool:
    """
    Return True if *role* would evaluate the "if" (true) branch of the ternary
    in *body*, i.e. the autonomy_role check in the lambda is True for this role.
    """
    if role == "performer":
        if '== "performer"' in body or "== 'performer'" in body:
            return True
        if '"performer", "supporter"' in body or '"supporter", "performer"' in body:
            return True
    if role == "supporter":
        if '== "supporter"' in body or "== 'supporter'" in body:
            return True
        if '"performer", "supporter"' in body or '"supporter", "performer"' in body:
            return True
    return False


def _classify_condition_source(src: str, role) -> str:
    """
    Given the raw source text of a transition condition and the current
    autonomy_role, return 'waiting' or 'sensing'.
    """
    # Collapse multi-line / indentation noise
    body_line = ' '.join(src.split())

    # Strip everything up to 'lambda:'
    m = re.search(r'lambda\s*:\s*(.*)', body_line)
    if not m:
        return "waiting"
    body = m.group(1).strip().rstrip(',').rstrip(')')

    # No autonomy_role branching — evaluate the whole expression
    if 'autonomy_role' not in body:
        return _classify_expr(body)

    # Role does NOT satisfy the if-condition → else branch applies.
    # In every pattern used in this codebase the else branch is self.is_acked().
    if not _role_satisfies_if_branch(body, role):
        return "waiting"

    # Role takes the if-branch — extract the true-expression and analyse it
    true_expr = _extract_ternary_true_expr(body)
    if true_expr is None:
        # No top-level ternary found: 'autonomy_role' appears inside data lookups
        # (e.g. self.states[...].autonomy_role == "x") rather than as a ternary
        # guard.  Classify the whole body expression directly.
        return _classify_expr(body)
    return _classify_expr(true_expr)


def _classify_expr(expr: str) -> str:
    """Return 'waiting', 'sensing', or 'sensing_ack' for a single expression.

    - 'waiting'     : only is_acked / allow_transition
    - 'sensing_ack' : a real sensor function AND is_acked() as a fallback
    - 'sensing'     : a real sensor function with no is_acked() fallback
    """
    if _expr_is_acked_only(expr):
        return "waiting"
    has_acked = bool(
        re.search(r'self\.is_acked\s*\(', expr)
        or re.search(r'self\.allow_transition\s*\(', expr)
    )
    return "sensing_ack" if has_acked else "sensing"


def determine_transition_kind(agent, state) -> str:
    """
    Return 'waiting' if the only way out of *state* (for its current
    autonomy_role) is pilot acknowledgment (is_acked), or 'sensing' if TARS
    must poll an environmental condition.
    """
    if agent is None:
        return "waiting"

    role = state.autonomy_role

    for transition in agent.fsm.transitions:
        if transition is None or transition.from_state is not state:
            continue

        condition = transition.condition

        # Direct bound-method references (not wrapped in a lambda)
        if condition is agent.is_acked or condition is agent.allow_transition:
            return "waiting"

        # Lambda / other callable — inspect source
        try:
            src = inspect.getsource(condition).strip()
        except (OSError, TypeError):
            # Cannot inspect: conservative — performers/supporters get 'sensing'
            return "sensing" if role in ("performer", "supporter") else "waiting"

        return _classify_condition_source(src, role)

    return "waiting"

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
            # Play swipe sound effect asynchronously
            def play_swipe_sound():
                try:
                    sound_path = os.path.join(project_root, "sounds", "swipe_sfx.mp3")
                    if os.path.exists(sound_path):
                        data, samplerate = sf.read(sound_path)
                        sd.play(data, samplerate)
                except Exception as e:
                    pass  # Silently ignore audio errors
            
            threading.Thread(target=play_swipe_sound, daemon=True).start()
            
            # Publish current state
            # Determine transition condition kind: 'waiting' if the only exit is
            # is_acked() for the current autonomy_role, else 'sensing'.
            transition_kind = determine_transition_kind(tars_agent, state)
            
            state_json = encode_state_to_json(state, transition_kind=transition_kind)
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
            # Determine transition condition kind: 'waiting' if the only exit is
            # is_acked() for the current autonomy_role, else 'sensing'.
            transition_kind = determine_transition_kind(tars_agent, state)
            
            state_json = encode_state_to_json(state, transition_kind=transition_kind)
            import ingescape as igs
            igs.output_set_string("action_about_to_fire", state_json)
            print(f"📤 Published action about to fire: {state.procedure} - {state.task_object} (transition_kind={transition_kind})")
        except Exception as e:
            print(f"Error publishing action about to fire: {e}")
    
    # Start FSM worker in background thread  
    fsm_worker = FSMWorkerCore(tars_agent)
    fsm_worker.set_state_changed_callback(on_state_changed)
    fsm_worker.set_action_about_to_fire_callback(on_action_about_to_fire)
    
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
