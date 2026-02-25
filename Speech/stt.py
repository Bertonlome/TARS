import signal as sig_module
from vosk import Model, KaldiRecognizer
import sounddevice as sd
import soundfile as sf
import json
import time
import sys
import os
import threading
from echo_speech import *

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Core.igs_utils import start_with_device_fallback

import platform
if platform.system() == "Linux":
    DEFAULT_DEVICE = "wlp0s20f3"
elif platform.system() == "Windows":
    DEFAULT_DEVICE = "Wi-Fi"
else:
    DEFAULT_DEVICE = "wlps"

SAMPLE_RATE = 16000
port = 5670
agent_name = "Speech_to_Text_Agent"
device = DEFAULT_DEVICE
verbose = False
is_interrupted = False

# Load offline model - use absolute path
script_dir = os.path.dirname(os.path.abspath(__file__))
model_path = os.path.join(script_dir, "model", "vosk-model-en-us-0.22")
model = Model(model_path)

# Global state for push-to-talk
is_recording = False
stream = None
has_audio_data = False  # Track if any audio was processed
audio_frame_count = 0  # Track number of frames processed
current_recognizer = None  # Current active recognizer instance
recognizer_lock = threading.Lock()  # Thread safety for recognizer access
ptt_start_time = None  # Track when PTT was pressed
MIN_PTT_DURATION = 1.0  # Minimum 1 second PTT press
MAX_RECORDING_DURATION = 5.0  # Maximum 5 second recording timeout
timeout_timer = None  # Timer for automatic timeout

def play_sound_async(sound_filename):
    """Play a sound effect asynchronously (non-blocking)"""
    def _play():
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            sound_path = os.path.join(project_root, "sounds", sound_filename)
            if os.path.exists(sound_path):
                data, samplerate = sf.read(sound_path)
                sd.play(data, samplerate)
        except Exception:
            pass  # Silently ignore audio errors
    
    threading.Thread(target=_play, daemon=True).start()

def signal_handler(signal_received, frame):
    global is_interrupted
    print("\n", sig_module.strsignal(signal_received), sep="")
    is_interrupted = True

def on_agent_event_callback(event, uuid, name, event_data, my_data):
    agent_object = my_data
    assert isinstance(agent_object, Echo)
    # add code here if needed

def on_freeze_callback(is_frozen, my_data):
    agent_object = my_data
    assert isinstance(agent_object, Echo)
    # add code here if needed

def stop_recording():
    """Stop recording and process results"""
    global is_recording, ptt_start_time, current_recognizer, timeout_timer
    
    # Cancel timeout timer if active
    if timeout_timer is not None:
        timeout_timer.cancel()
        timeout_timer = None
    
    # Check minimum duration
    elapsed_time = time.time() - ptt_start_time if ptt_start_time else 0
    
    if elapsed_time < MIN_PTT_DURATION:
        wait_time = MIN_PTT_DURATION - elapsed_time
        time.sleep(wait_time)
        elapsed_time = MIN_PTT_DURATION
    
    # Stop recording and get final result
    is_recording = False
    ptt_start_time = None
    igs.output_set_bool("is_listening", False)  # Signal that STT stopped listening
    
    with recognizer_lock:
        if current_recognizer is None:
            print("⚠️  No recognizer available")
            return
        
        if audio_frame_count > 0:
            # Try to get any recognized text
            try:
                # Try FinalResult first
                final_result = json.loads(current_recognizer.FinalResult())
                text = final_result.get("text", "").strip()
                
                if text:
                    print(f"📝 Recognized: {text}")
                    igs.output_set_string("speech_output", text)
                else:
                    # No final text, try partial
                    partial_result = json.loads(current_recognizer.PartialResult())
                    text = partial_result.get("partial", "").strip()
                    if text:
                        print(f"📝 Recognized (partial): {text}")
                        igs.output_set_string("speech_output", text)
                    else:
                        print("⚠️  No speech detected")
                        
            except Exception as vosk_error:
                # FinalResult failed, try partial
                print(f"⚠️  Using partial result due to: {vosk_error}")
                try:
                    partial_result = json.loads(current_recognizer.PartialResult())
                    text = partial_result.get("partial", "").strip()
                    if text:
                        print(f"📝 Recognized (partial): {text}")
                        igs.output_set_string("speech_output", text)
                    else:
                        print("⚠️  No speech in partial result")
                except Exception as partial_error:
                    print(f"❌ Partial result error: {partial_error}")
        else:
            print("⚠️  No audio data received")
        
        # Clear recognizer reference after use
        current_recognizer = None

def on_recording_timeout():
    """Called when recording timeout expires"""
    global is_recording
    if is_recording:
        print("⏱️  Recording timeout reached (5s), stopping...")
        stop_recording()

def bool_input_callback(io_type, name, value_type, value, my_data):
    global is_recording, stream, current_recognizer, has_audio_data, audio_frame_count, recognizer_lock, ptt_start_time, timeout_timer
    agent_object = my_data
    assert isinstance(agent_object, Echo)
    
    if name == "push_to_talk":
        agent_object.push_to_talk_i = value
        
        try:
            if value and not is_recording:
                # Play listening sound effect
                play_sound_async("STT_listening.mp3")
                
                # Start recording - create NEW recognizer for this session
                print("🎤 Recording started...")
                ptt_start_time = time.time()  # Record start time
                igs.output_set_bool("is_listening", True)  # Signal that STT is listening
                
                with recognizer_lock:
                    # Create fresh recognizer instance
                    current_recognizer = KaldiRecognizer(model, SAMPLE_RATE)
                    is_recording = True
                    has_audio_data = False
                    audio_frame_count = 0
                
                # Start timeout timer
                timeout_timer = threading.Timer(MAX_RECORDING_DURATION, on_recording_timeout)
                timeout_timer.start()
                
            elif not value and is_recording:
                # User manually stopped recording
                stop_recording()
                    
        except Exception as e:
            print(f"❌ Error in push_to_talk callback: {e}")
            import traceback
            traceback.print_exc()
            is_recording = False
            igs.output_set_bool("is_listening", False)  # Ensure listening is off on error
            if timeout_timer is not None:
                timeout_timer.cancel()
                timeout_timer = None
            with recognizer_lock:
                current_recognizer = None

def callback(indata, frames, time_info, status):
    global is_recording, current_recognizer, has_audio_data, audio_frame_count, recognizer_lock
    
    if status:
        print(f"⚠️  Audio status: {status}")
    
    # Only process audio when recording is active
    if is_recording:
        try:
            with recognizer_lock:
                if current_recognizer is None:
                    return  # No recognizer available
                
                has_audio_data = True
                audio_frame_count += 1  # Increment frame counter
                
                # Convert audio to bytes and feed recognizer
                if current_recognizer.AcceptWaveform(bytes(indata)):
                    result = json.loads(current_recognizer.Result())
                    text = result.get("text", "").strip()
                    if text:
                        print(f">> Partial: {text}")
        except Exception as e:
            print(f"❌ Error in audio callback: {e}")

def main():
    global stream, is_interrupted
    
    print("Speech recognition ready. Waiting for push_to_talk signal...")
    print("Press Ctrl+C to quit.")
    
    try:
        # Keep audio stream always open
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=8000,
            dtype="int16",
            channels=1,
            callback=callback,
        ):
            while not is_interrupted:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"❌ Error in audio stream: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("Shutting down...")
        igs.stop()

if __name__ == "__main__":
    sig_module.signal(sig_module.SIGINT, signal_handler)

    print("=" * 50)
    print("Starting Speech-to-Text Agent")
    print("=" * 50)
    
    # Check available audio devices
    try:
        devices = sd.query_devices()
        print("\n📟 Available audio devices:")
        print(devices)
        print()
    except Exception as e:
        print(f"⚠️  Could not query audio devices: {e}")

    igs.agent_set_name(agent_name)
    igs.definition_set_version("1.0")
    igs.log_set_console(verbose)
    igs.log_set_file(True, None)
    igs.log_set_stream(verbose)
    igs.set_command_line(sys.executable + " " + " ".join(sys.argv))

    agent = Echo()

    igs.observe_agent_events(on_agent_event_callback, agent)
    igs.observe_freeze(on_freeze_callback, agent)

    igs.input_create("push_to_talk", igs.BOOL_T, None)
    igs.output_create("speech_output", igs.STRING_T, None)
    igs.output_create("is_listening", igs.BOOL_T, False)
    igs.observe_input("push_to_talk", bool_input_callback, agent)
    igs.mapping.add("push_to_talk", "Aircraft", "ptt")
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