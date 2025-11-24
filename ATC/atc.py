import signal as sig_module
import time
import sys
import os
import threading
import soundfile as sf
import sounddevice as sd
from echo_atc import *

port = 5670
agent_name = "ATC_Agent"
device = "wlp0s20f3" 
verbose = False
is_interrupted = False

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

def play_audio_file(file_path):
    """Play audio file (blocking)"""
    try:
        # Get absolute path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs_path = os.path.join(script_dir, file_path)
        
        if not os.path.exists(abs_path):
            print(f"⚠️  Audio file not found: {abs_path}")
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

def play_audio_async(file_path):
    """Play audio file in background thread (non-blocking)"""
    def _play():
        try:
            # Get absolute path
            script_dir = os.path.dirname(os.path.abspath(__file__))
            abs_path = os.path.join(script_dir, file_path)
            
            if not os.path.exists(abs_path):
                print(f"⚠️  Audio file not found: {abs_path}")
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
    
    thread = threading.Thread(target=_play, daemon=True)
    thread.start()

def impulsion_input_callback(io_type, name, value_type, value, my_data):
    agent_object = my_data
    assert isinstance(agent_object, Echo)
    
    try:
        if name == "request_ATIS":
            agent_object.speech_output_o = "Montreal Trudeau International Airport Information Alpha. One five zero zero Zulu. Wind zero nine zero at four knots. Visibility one statute mile in fog. Ceiling one thousand five hundred overcast. Temperature five, dewpoint four. Altimeter two niner niner two. Runway surfaces dry. Departing and arriving runway in use is zero six left. Advise on initial contact you have Information Alpha."
            print(f"📡 Received: {name}")
            play_audio_file("audio/atis_alpha.mp3")
        if name == "request_takeoff_clearance":
            agent_object.speech_output_o = "C-POLY, Montréal Tower, wind zero-niner-zero at four, runway zero-six left, cleared for takeoff. Maintain runway heading, climb to 5000ft, Proceed direct AGMEB then OMEKI. Departure on one-one-eight decimal niner. Good flight."
            print(f"📡 Received: {name}")
            play_audio_file("audio/takeoff_clearance.mp3")
        elif name == "declare_mayday":
            time.sleep(15) # Simulate delay before responding
            agent_object.speech_output_o = "C-POLY, Montréal Tower, roger Mayday. Continue runway heading. You are cleared to return runway zero-six left to land. Emergency vehicles are standing by."
            print(f"📡 Received: {name}")
            play_audio_async("audio/roger_mayday.mp3")
        elif name == "declare_panpan":
            time.sleep(15) # Simulate delay before responding
            agent_object.speech_output_o = "C-POLY, Montréal Tower, roger Pan-Pan. Continue runway heading. Advise if you require vectors for an approach to runway zero-six left."
            print(f"📡 Received: {name}")
            play_audio_async("audio/panpan_no_vectors.mp3")
        elif name == "request_vectors":
            time.sleep(15) # Simulate delay before responding
            agent_object.speech_output_o = "C-POLY, Montréal Tower, roger. Turn right heading one-five-zero, descend and maintain three thousand feet. Expect ILS approach runway zero-six left."
            print(f"📡 Received: {name}")
            play_audio_async("audio/first_vectors.mp3")
            time.sleep(60 * 5)  # Simulate delay for vectoring
            agent_object.speech_output_o = "C-POLY, Montréal Tower, turn right heading three-three-zero, when established, cleared ILS runway zero-six left."
            play_audio_async("audio/second_vectors.mp3")
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

    igs.input_create("request_ATIS", igs.IMPULSION_T, None)
    igs.input_create("request_takeoff_clearance", igs.IMPULSION_T, None)
    igs.input_create("declare_mayday", igs.IMPULSION_T, None)
    igs.input_create("declare_panpan", igs.IMPULSION_T, None)
    igs.input_create("request_vectors", igs.IMPULSION_T, None)
    igs.output_create("speech_output", igs.STRING_T, None)
    igs.observe_input("request_takeoff_clearance", impulsion_input_callback, agent)
    igs.observe_input("declare_mayday", impulsion_input_callback, agent)
    igs.observe_input("declare_panpan", impulsion_input_callback, agent)
    igs.observe_input("request_vectors", impulsion_input_callback, agent)
    igs.observe_input("request_ATIS", impulsion_input_callback, agent)
    igs.log_set_console(True)
    igs.log_set_console_level(igs.LOG_INFO)

    try:
        igs.start_with_device(device, port)
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