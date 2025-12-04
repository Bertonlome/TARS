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
    
    # Set up FSM worker callbacks to publish via Ingescape
    def on_state_changed(state):
        """Publish state change via Ingescape"""
        from Core.message_protocol import encode_state_to_json
        try:
            state_json = encode_state_to_json(state)
            import ingescape as igs
            igs.output_set_string("current_state", state_json)
            print(f"📤 Published state change: {state.procedure} - {state.task_object}")
        except Exception as e:
            print(f"Error publishing state: {e}")
    
    # Start FSM worker in background thread  
    fsm_worker = FSMWorkerCore(tars_agent)
    fsm_worker.set_state_changed_callback(on_state_changed)
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
