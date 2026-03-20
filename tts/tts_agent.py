#!/usr/bin/env python3
# coding: utf-8

"""
TTS Agent - Standalone Ingescape Agent for Text-to-Speech
Receives text via Ingescape and speaks it using Silero TTS
"""

import sys
import ingescape as igs
from pathlib import Path

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
        
        # Register callbacks with TTS module to track speaking status
        tts.register_speak_callback(self._on_tts_started)
        tts.register_finished_callback(self._on_tts_finished)
        
    def _on_tts_started(self, text):
        """Called when TTS starts speaking"""
        igs.output_set_bool("is_speaking", True)
        igs.output_set_string("current_text", text)
        print(f"🔊 TTS speaking: {text[:50]}...")
        
    def _on_tts_finished(self, text):
        """Called when TTS finishes speaking"""
        igs.output_set_bool("is_speaking", False)
        igs.output_set_string("current_text", "")
        print(f"✓ TTS finished")
    
    def on_text_to_speak(self, ioType, name, valueType, value, myData):
        """Called when text_to_speak input is received"""
        if value and isinstance(value, str) and value.strip():
            print(f"📥 TTS received: {value[:50]}...")
            # Queue the text for speaking (non-blocking)
            tts.speak_wait(value)

    def on_tts_stop(self, ioType, name, valueType, value, myData):
        """Called when a stop impulsion is received - mute TTS persistently"""
        print("🔊 TTS stop received - muting playback")
        tts.mute()
        igs.output_set_bool("is_speaking", False)
        igs.output_set_string("current_text", "")

    def on_tts_unmute(self, ioType, name, valueType, value, myData):
        """Called when tts_unmute impulsion is received - re-enable TTS playback"""
        print("🔊 TTS unmute received - re-enabling playback")
        tts.unmute()

    def on_repeat_sentence(self, ioType, name, valueType, value, myData):
        """Called when repeat_sentence impulsion is received - replay last utterance"""
        print("🔁 repeat_sentence received - replaying last TTS output")
        tts.repeat_last()

    def on_is_atc_speaking(self, ioType, name, valueType, value, myData):
        """Called when ATC_Agent.is_speaking changes - gate TTS playback accordingly"""
        tts.set_atc_speaking(bool(value))
    
    def shutdown(self):
        """Clean shutdown"""
        print("Shutting down TTS agent...")
        tts.shutdown()


def main():
    """Main entry point for TTS agent"""
    
    # Default values
    agent_name = "TTS_Agent"
    network_device = "wlp0s20f3"
    port = 5670
    
    # Allow command-line override if provided
    if len(sys.argv) >= 2:
        agent_name = sys.argv[1]
    if len(sys.argv) >= 3:
        network_device = sys.argv[2]
    if len(sys.argv) >= 4:
        port = int(sys.argv[3])
    
    # Agent creation and initialization
    igs.agent_set_name(agent_name)
    igs.log_set_console(True)
    igs.log_set_file(True, None)
    igs.set_command_line(sys.executable + " " + " ".join(sys.argv))
    
    # Define inputs
    igs.input_create("text_to_speak", igs.STRING_T, None)
    igs.input_create("is_atc_speaking", igs.BOOL_T, False)
    
    # Define outputs
    igs.output_create("is_speaking", igs.BOOL_T, False)
    igs.output_create("current_text", igs.STRING_T, "")
    
    # Create agent instance
    tts_agent = TTSAgent()
    
    # Define impulsion inputs
    igs.input_create("tts_stop", igs.IMPULSION_T, None)
    igs.input_create("repeat_sentence", igs.IMPULSION_T, None)
    igs.input_create("tts_unmute", igs.IMPULSION_T, None)

    # Observe inputs
    igs.observe_input("text_to_speak", tts_agent.on_text_to_speak, None)
    igs.observe_input("tts_stop", tts_agent.on_tts_stop, None)
    igs.observe_input("repeat_sentence", tts_agent.on_repeat_sentence, None)
    igs.observe_input("tts_unmute", tts_agent.on_tts_unmute, None)
    igs.observe_input("is_atc_speaking", tts_agent.on_is_atc_speaking, None)
    igs.mapping_add("text_to_speak", "TARS_Agent", "tts_request")
    igs.mapping_add("tts_stop", "Shared Interface", "tts_stop")
    igs.mapping_add("repeat_sentence", "Shared Interface", "repeat_sentence")
    igs.mapping_add("tts_unmute", "Shared Interface", "tts_unmute")
    igs.mapping_add("is_atc_speaking", "ATC_Agent", "is_speaking")
    
    # Start Ingescape with device fallback
    start_with_device_fallback(igs, port)
    
    print(f"✓ TTS Agent '{agent_name}' started on {network_device}:{port}")
    print("  Inputs: text_to_speak, tts_stop (impulsion), repeat_sentence (impulsion)")
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
