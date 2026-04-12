import signal as sig_module
import time
import sys
import os
import threading
import tempfile
import soundfile as sf
import sounddevice as sd
import pyttsx3
import numpy as np
from echo_atc import *

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Core.igs_utils import start_with_device_fallback

# Choose sensible default network device name depending on host OS.
# Linux typically uses interface names like 'wlp0s20f3'; Windows GUI name is 'Wi-Fi'.
import platform
if platform.system() == "Linux":
    DEFAULT_DEVICE = "wlp0s20f3"
elif platform.system() == "Windows":
    DEFAULT_DEVICE = "Wi-Fi"
else:
    DEFAULT_DEVICE = "wlps"

port = 5670
agent_name = "ATC_Agent"
device = DEFAULT_DEVICE
verbose = False
is_interrupted = False

# Cancellation event — set by Reset to abort any pending delayed messages
_cancel_delayed = threading.Event()

# Active runway received from TARS Agent
active_runway = "24R"

# Audio files keyed by runway (fallback to 24R if unknown)
_ATIS_AUDIO = {
    "24R": "audio/ATIS_Victor_290_04_24R.mp3",
    "24L": "audio/ATIS_Bravo_190_04_24L.mp3",
    "06R": "audio/ATIS_Golf_090_04_06R.mp3",
}
_TAKEOFF_CLEARANCE_AUDIO = {
    "24R": "audio/takeoff_clearance_290_04_RWY_24R_5000.mp3",
    "24L": "audio/takeoff_clearance_190_04_RWY_24L_5000.mp3",
    "06R": "audio/takeoff_clearance_090_04_RWY_06R_5000.mp3",
}
_MAYDAY_AUDIO = {
    "24R": "audio/mayday_24R.mp3",
    "24L": "audio/mayday_24L.mp3",
    "06R": "audio/mayday_06R.mp3",
}
_VECTORS_AUDIO = {
    "24R": "audio/panpan_turn_right_vectors_330_24R.mp3",
    "24L": "audio/panpan_turn_left_vectors_150_24L.mp3",
    "06R": "audio/panpan_turn_right_vector_150_06R.mp3",
}

# Initialize TTS engine
tts_engine = pyttsx3.init()
tts_engine.setProperty('rate', 150)  # Slightly slower for ATC clarity
tts_engine.setProperty('volume', 0.9)

# Try to set a more professional voice if available
voices = tts_engine.getProperty('voices')
for voice in voices:
    # Prefer male voices for ATC realism
    if 'male' in voice.name.lower() or 'david' in voice.name.lower():
        tts_engine.setProperty('voice', voice.id)
        break

def apply_radio_effect(audio_data, samplerate):
    """Apply radio-static effect to simulate ATC communication"""
    try:
        # Add slight high-pass filter effect (remove low frequencies)
        # Simple approximation: reduce amplitude at low frequencies
        filtered = audio_data.copy()
        
        # Add subtle white noise (radio static)
        noise_level = 0.01  # Very subtle static
        noise = np.random.normal(0, noise_level, filtered.shape)
        filtered = filtered + noise
        
        # Slight compression (reduce dynamic range for radio effect)
        filtered = np.tanh(filtered * 1.2) * 0.9
        
        # Band-pass filter simulation: attenuate very low and very high frequencies
        # This gives it that "compressed" radio sound
        filtered = filtered * 0.95  # Slight overall reduction
        
        return filtered
    except Exception as e:
        print(f"⚠️  Could not apply radio effect: {e}")
        return audio_data

def speak_with_radio_effect(text):
    """Speak text using TTS with radio-static effect"""
    try:
        # Set is_speaking to true
        igs.output_set_bool("is_speaking", True)
        
        print(f"📻 ATC (TTS): {text}")
        
        # Generate TTS to temporary file (platform-independent)
        temp_file = os.path.join(tempfile.gettempdir(), "atc_tts_temp.wav")
        tts_engine.save_to_file(text, temp_file)
        tts_engine.runAndWait()
        
        # Wait a bit for file to be written
        time.sleep(0.2)
        
        # Load the audio file
        if os.path.exists(temp_file):
            data, samplerate = sf.read(temp_file)
            
            # Apply radio effect
            data = apply_radio_effect(data, samplerate)
            
            # Play the processed audio
            sd.play(data, samplerate)
            sd.wait()
            
            # Cleanup
            try:
                os.remove(temp_file)
            except:
                pass
            
            print(f"✅ TTS playback finished")
        else:
            print(f"⚠️  TTS file not generated at {temp_file}")
            
    except Exception as e:
        print(f"❌ Error in TTS with radio effect: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Set is_speaking back to false
        igs.output_set_bool("is_speaking", False)

def signal_handler(signal_received, frame):
    global is_interrupted
    # Use platform-safe signal description
    try:
        if hasattr(sig_module, 'strsignal'):
            sig_desc = sig_module.strsignal(signal_received)
        else:
            sig_desc = f"Signal {signal_received}"
    except (AttributeError, ValueError):
        sig_desc = f"Signal {signal_received}"
    print("\n", sig_desc, sep="")
    is_interrupted = True

def on_agent_event_callback(event, uuid, name, event_data, my_data):
    agent_object = my_data
    assert isinstance(agent_object, Echo)
    # add code here if needed

def on_freeze_callback(is_frozen, my_data):
    agent_object = my_data
    assert isinstance(agent_object, Echo)
    # add code here if needed

def interruptible_sleep(seconds):
    """Sleep for `seconds`. Returns True if cancelled early by Reset, False if it completed normally."""
    return _cancel_delayed.wait(timeout=seconds)


def play_audio_file(file_path):
    """Play audio file (blocking)"""
    try:
        # Set is_speaking to true
        igs.output_set_bool("is_speaking", True)
        
        # Get absolute path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs_path = os.path.join(script_dir, file_path)
        
        if not os.path.exists(abs_path):
            print(f"⚠️  Audio file not found: {abs_path}")
            igs.output_set_bool("is_speaking", False)
            return
        
        print(f"🔊 Playing: {abs_path}")
        data, samplerate = sf.read(abs_path)
        sd.play(data, samplerate)
        sd.wait()  # Wait for playback to finish
        print(f"✅ Playback finished: {os.path.basename(abs_path)}")
    except Exception as e:
        print(f"❌ Error playing audio file {file_path}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Set is_speaking back to false
        igs.output_set_bool("is_speaking", False)

def play_audio_async(file_path):
    """Play audio file in background thread (non-blocking)"""
    def _play():
        try:
            # Set is_speaking to true
            igs.output_set_bool("is_speaking", True)
            
            # Get absolute path
            script_dir = os.path.dirname(os.path.abspath(__file__))
            abs_path = os.path.join(script_dir, file_path)
            
            if not os.path.exists(abs_path):
                print(f"⚠️  Audio file not found: {abs_path}")
                igs.output_set_bool("is_speaking", False)
                return
            
            print(f"🔊 Playing (async): {abs_path}")
            data, samplerate = sf.read(abs_path)
            sd.play(data, samplerate)
            sd.wait()
            print(f"✅ Playback finished: {os.path.basename(abs_path)}")
        except Exception as e:
            print(f"❌ Error playing audio: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Set is_speaking back to false
            igs.output_set_bool("is_speaking", False)
    
    thread = threading.Thread(target=_play, daemon=True)
    thread.start()

def string_input_callback(io_type, name, value_type, value, my_data):
    global active_runway
    agent_object = my_data
    assert isinstance(agent_object, Echo)

    if name == "runway_number":
        if value:
            active_runway = value
            print(f"🛫 [ATC] Active runway updated: {active_runway}")
        return
    if name == "custom_speech":
        agent_object.custom_speech_i = value
        print(f"📻 Custom speech request: {value}")
        # Speak the custom text with radio effect in background thread
        thread = threading.Thread(target=speak_with_radio_effect, args=(value,), daemon=True)
        thread.start()

def integer_input_callback(io_type, name, value_type, value, my_data):
    agent_object = my_data
    assert isinstance(agent_object, Echo)

    def _run():
        try:
            # Clear any lingering cancel from a previous Reset before starting
            _cancel_delayed.clear()
            if name == "declare_mayday":
                print(f"📡 Received: {name} with delay={value}s (runway={active_runway})")
                if interruptible_sleep(value):
                    print("🚫 declare_mayday: initial delay cancelled by Reset")
                    return
                agent_object.speech_output_o = f"C-POLY, Montréal-Tower, roger-Mayday. Continue-runway-heading. You-are-cleared-to-return-to-runway-{active_runway}-to-land. Emergency-vehicles-are-standing-by."
                play_audio_async(_MAYDAY_AUDIO.get(active_runway, _MAYDAY_AUDIO["24R"]))
            elif name == "declare_panpan":
                print(f"📡 Received: {name} with delay={value}s (runway={active_runway})")
                if interruptible_sleep(value):
                    print("🚫 declare_panpan: initial delay cancelled by Reset")
                    return
                agent_object.speech_output_o = "C-POLY, Montréal-Tower, roger-Pan-Pan. Continue-runway-heading. what are your intentions?"
                play_audio_async("audio/panpan_no_vectors.mp3")
            elif name == "request_vectors":
                print(f"📡 Received: {name} with delay={value}s (runway={active_runway})")
                if interruptible_sleep(value):
                    print("🚫 request_vectors: initial delay cancelled by Reset")
                    return
                if active_runway == "24R":
                    agent_object.speech_output_o = f"C-POLY, Montréal-Tower, roger. Turn right heading 330 for vectors to runway {active_runway}."
                    play_audio_async(_VECTORS_AUDIO["24R"])
                elif active_runway == "24L":
                    agent_object.speech_output_o = f"C-POLY, Montréal-Tower, roger. Turn left heading 150 for vectors to runway {active_runway}."
                    play_audio_async(_VECTORS_AUDIO["24L"])
                elif active_runway == "06R":
                    agent_object.speech_output_o = f"C-POLY, Montréal-Tower, roger. Turn right heading 150 for vectors to runway {active_runway}."
                    play_audio_async(_VECTORS_AUDIO["06R"])
            elif name == "request_takeoff_clearance":
                print(f"📡 Received: {name} with delay={value}s (runway={active_runway})")
                if interruptible_sleep(value):
                    print("🚫 request_takeoff_clearance: initial delay cancelled by Reset")
                    return
                if active_runway == "24R":
                    agent_object.speech_output_o = f"C-POLY, Montreal-Tower, wind-two-niner-zero-at-four, altimeter-two-niner-niner-two, cleared-for-takeoff runway-two-four-right, climb-to-five-thousand."
                elif active_runway == "24L":
                    agent_object.speech_output_o = f"C-POLY, Montreal-Tower, wind-one-niner-zero-at-four, altimeter-two-niner-niner-two, cleared-for-takeoff runway-two-four-left, climb-to-five-thousand."
                elif active_runway == "06R":
                    agent_object.speech_output_o = f"C-POLY, Montreal-Tower, wind-zero-niner-zero-at-four, altimeter-two-niner-niner-two, cleared-for-takeoff runway-zero-six-right, climb-to-five-thousand."
                play_audio_async(_TAKEOFF_CLEARANCE_AUDIO.get(active_runway, _TAKEOFF_CLEARANCE_AUDIO["24R"]))
        except Exception as e:
            print(f"❌ Error in integer callback thread: {e}")
            import traceback
            traceback.print_exc()

    threading.Thread(target=_run, daemon=True).start()

def impulsion_input_callback(io_type, name, value_type, value, my_data):
    agent_object = my_data
    assert isinstance(agent_object, Echo)
    
    try:
        if name == "Reset":
            _cancel_delayed.set()   # unblock any interruptible_sleep
            sd.stop()               # stop any currently playing audio
            agent_object.speech_output_o = ""
            print(f"📡 Received: {name} - Resetting speech output and cancelling delayed messages")
        if name == "request_ATIS":
            print(f"📡 Received: {name} (runway={active_runway})")
            if active_runway == "24R":
                agent_object.speech_output_o = f" Montreal Trudeau International Airport Information Victor. One five zero zero Zulu. Wind two niner zero at four knots. Visibility one statute mile in fog. Ceiling two hundred feet overcast. Temperature five, dewpoint four. Altimeter two niner niner two. Runway surfaces dry. Departing and arriving runway in use is two four right. Advise on initial contact you have Information Golf."
            elif active_runway == "24L":
                agent_object.speech_output_o = f" Montreal Trudeau International Airport Information Bravo. One five zero zero Zulu. Wind one niner zero at four knots. Visibility one statute mile in fog. Ceiling two hundred feet overcast. Temperature five, dewpoint four. Altimeter two niner niner two. Runway surfaces dry. Departing and arriving runway in use is two four left. Advise on initial contact you have Information Bravo."
            elif active_runway == "06R":
                agent_object.speech_output_o = f" Montreal Trudeau International Airport Information Golf. One five zero zero Zulu. Wind zero niner zero at four knots. Visibility one statute mile in fog. Ceiling two hundred feet overcast. Temperature five, dewpoint four. Altimeter two niner niner two. Runway surfaces dry. Departing and arriving runway in use is zero six right. Advise on initial contact you have Information Golf."
            play_audio_file(_ATIS_AUDIO.get(active_runway, _ATIS_AUDIO["24R"]))
    except Exception as e:
        print(f"❌ Error in impulsion callback: {e}")
        import traceback
        traceback.print_exc()


def main():
    global is_interrupted
    print("ATC Agent is running. Press Ctrl+C to exit.")
    
    try:
        while not is_interrupted:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    finally:
        print("Shutting down ATC...")
        igs.stop()

if __name__ == "__main__":
    sig_module.signal(sig_module.SIGINT, signal_handler)

    print("=" * 50)
    print("Starting ATC Agent")
    print("=" * 50)
    
    # Check available audio devices
    igs.agent_set_name(agent_name)
    igs.definition_set_version("1.0")
    igs.log_set_console(verbose)
    igs.log_set_file(True, None)
    igs.log_set_stream(verbose)
    igs.set_command_line(sys.executable + " " + " ".join(sys.argv))

    agent = Echo()

    igs.observe_agent_events(on_agent_event_callback, agent)
    igs.observe_freeze(on_freeze_callback, agent)


    igs.input_create("Reset", igs.IMPULSION_T, None)
    igs.input_create("request_ATIS", igs.IMPULSION_T, None)
    igs.input_create("request_takeoff_clearance", igs.INTEGER_T, None)
    igs.input_create("declare_mayday", igs.INTEGER_T, None)
    igs.input_create("declare_panpan", igs.INTEGER_T, None)
    igs.input_create("request_vectors", igs.INTEGER_T, None)
    igs.input_create("custom_speech", igs.STRING_T, None)
    igs.input_create("runway_number", igs.STRING_T, None)
    igs.output_create("speech_output", igs.STRING_T, None)
    igs.output_create("is_speaking", igs.BOOL_T, False)
    igs.observe_input("Reset", impulsion_input_callback, agent)
    igs.observe_input("request_takeoff_clearance", integer_input_callback, agent)
    igs.observe_input("declare_mayday", integer_input_callback, agent)
    igs.observe_input("declare_panpan", integer_input_callback, agent)
    igs.observe_input("request_vectors", integer_input_callback, agent)
    igs.observe_input("request_ATIS", impulsion_input_callback, agent)
    igs.observe_input("custom_speech", string_input_callback, agent)
    igs.observe_input("runway_number", string_input_callback, agent)

    igs.mapping_add("request_takeoff_clearance", "TARS_Agent", "request_takeoff_clearance")
    igs.mapping_add("runway_number", "TARS_Agent", "runway_number")
    igs.log_set_console(True)
    igs.log_set_console_level(igs.LOG_INFO)

    try:
        start_with_device_fallback(igs, port)
    except Exception as e:
        print(f"❌ Failed to start Ingescape agent: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # catch SIGINT handler after starting agent
    sig_module.signal(sig_module.SIGINT, signal_handler)
    
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal error in main: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)