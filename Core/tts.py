import pyttsx3
import threading
import queue

_engine = pyttsx3.init()
_engine.setProperty('rate', 155)
_engine.setProperty('volume', 0.9)
voices = _engine.getProperty('voices')
if len(voices) > 1:
    _engine.setProperty('voice', voices[3].id)

# Warm up the engine with a dummy call to avoid first-call initialization delay
_engine.say("")
_engine.runAndWait()

_speech_queue = queue.Queue()

# Callbacks for speech events
_speak_callbacks = []  # Called when speech starts
_finished_callbacks = []  # Called when speech finishes

def _tts_worker():
    while True:
        text = _speech_queue.get()
        if text is None:
            break  # Exit signal
        
        # Fire speaking callbacks right before speaking
        for cb in _speak_callbacks:
            try:
                cb(text)
            except Exception as e:
                print(f"Error in TTS speak callback: {e}")
        
        # Speak the text
        _engine.say(text)
        _engine.runAndWait()
        
        # Mark task as done (for queue.join() synchronization)
        _speech_queue.task_done()
        
        # Fire finished callbacks
        for cb in _finished_callbacks:
            try:
                cb(text)
            except Exception as e:
                print(f"Error in TTS finished callback: {e}")

_thread = threading.Thread(target=_tts_worker, daemon=True)
_thread.start()

def register_speak_callback(cb):
    """Register a callback that fires when TTS starts speaking"""
    _speak_callbacks.append(cb)

def register_finished_callback(cb):
    """Register a callback that fires when TTS finishes speaking
    
    Args:
        cb: Callable that takes one argument (the text that was spoken)
    """
    _finished_callbacks.append(cb)

def speak_wait(text: str):
    """Queue text to be spoken."""
    _speech_queue.put("TARS -" + text)

def shutdown():
    """Call this on program exit to cleanly stop the TTS thread."""
    _speech_queue.put(None)
    _thread.join()