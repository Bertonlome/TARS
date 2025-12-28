#!/usr/bin/env python3
# coding: utf-8

"""
TTS Agent - Standalone Ingescape Agent for Text-to-Speech
Receives text via Ingescape and speaks it using pyttsx3
"""

import sys
import ingescape as igs
from pathlib import Path
import threading
import queue

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from Core.igs_utils import start_with_device_fallback
sys.path.insert(0, str(Path(__file__).parent.parent))

from tts.echo_tts import Echo
from tts import tts


class TTSAgent:
    """Manages TTS via Ingescape interface"""
    
    def __init__(self):
        self.echo = Echo()
        self.speech_queue = queue.Queue()
        self.is_running = True
        
        # Start TTS worker thread
        self.worker_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.worker_thread.start()
        
    def _tts_worker(self):
        """Worker thread that processes TTS requests"""
        while self.is_running:
            try:
                text = self.speech_queue.get(timeout=0.1)
                if text is None:
                    break
                    
                # Set speaking status
                self.echo.is_speaking_o = True
                self.echo.current_text_o = text
                print(f"🔊 TTS speaking: {text[:50]}...")
                
                # Speak the text (blocking)
                tts.speak_wait(text)
                
                # Wait for TTS to complete
                tts._speech_queue.join()
                
                # Clear speaking status
                self.echo.is_speaking_o = False
                self.echo.current_text_o = ""
                print(f"✓ TTS finished")
                
                self.speech_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ TTS worker error: {e}")
                self.echo.is_speaking_o = False
                self.echo.current_text_o = ""
    
    def on_text_to_speak(self, ioType, name, valueType, value, myData):
        """Called when text_to_speak input is received"""
        if value and isinstance(value, str) and value.strip():
            print(f"📥 TTS received: {value[:50]}...")
            self.speech_queue.put(value)
    
    def shutdown(self):
        """Clean shutdown"""
        print("Shutting down TTS agent...")
        self.is_running = False
        self.speech_queue.put(None)
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2)
        tts.shutdown()


def main():
    """Main entry point for TTS agent"""
    
    if len(sys.argv) < 4:
        print("Usage: python tts_agent.py <agent_name> <network_device> <port>")
        print("Example: python tts_agent.py TTS_Agent en0 5670")
        sys.exit(1)
    
    agent_name = sys.argv[1]
    network_device = sys.argv[2]
    port = int(sys.argv[3])
    
    # Agent creation and initialization
    igs.agent_set_name(agent_name)
    igs.log_set_console(True)
    igs.log_set_file(True, None)
    igs.set_command_line(sys.executable + " " + " ".join(sys.argv))
    
    # Define inputs
    igs.input_create("text_to_speak", igs.STRING_T, None)
    
    # Define outputs
    igs.output_create("is_speaking", igs.BOOL_T, False)
    igs.output_create("current_text", igs.STRING_T, "")
    
    # Create agent instance
    tts_agent = TTSAgent()
    
    # Observe inputs
    igs.observe_input("text_to_speak", tts_agent.on_text_to_speak, None)
    
    # Start Ingescape with device fallback
    start_with_device_fallback(igs, port)
    
    print(f"✓ TTS Agent '{agent_name}' started on {network_device}:{port}")
    print("  Inputs: text_to_speak")
    print("  Outputs: is_speaking, current_text")
    print("  Ready to receive speech requests...")
    
    try:
        # Keep running until interrupted
        input("Press Enter to stop the agent...\n")
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        tts_agent.shutdown()
        igs.stop()
        print("TTS agent stopped")


if __name__ == "__main__":
    main()
