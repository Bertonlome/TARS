import pyttsx3
import threading
import queue

_engine = pyttsx3.init()
_engine.setProperty('rate', 150)
_engine.setProperty('volume', 0.9)
voices = _engine.getProperty('voices')
if len(voices) > 1:
    _engine.setProperty('voice', voices[1].id)

_speech_queue = queue.Queue()

def _tts_worker():
    while True:
        text = _speech_queue.get()
        if text is None:
            break  # Exit signal
        _engine.say(text)
        _engine.runAndWait()
        _speech_queue.task_done()

_thread = threading.Thread(target=_tts_worker, daemon=True)
_thread.start()

def speak(text: str):
    """Queue text to be spoken."""
    _speech_queue.put(text)

def shutdown():
    """Call this on program exit to cleanly stop the TTS thread."""
    _speech_queue.put(None)
    _thread.join()