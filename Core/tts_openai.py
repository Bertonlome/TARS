import threading
import queue
import asyncio

from openai import AsyncOpenAI
from openai.helpers import LocalAudioPlayer

openai = AsyncOpenAI(api_key="")
_speech_done_event = threading.Event()
_speech_queue = queue.Queue()
_speak_callbacks = []


def register_speak_callback(cb):
    _speak_callbacks.append(cb)

def speak(text: str):
    """Queue text to be spoken."""
    for cb in _speak_callbacks:
        cb(text)
    _speech_queue.put(text)

def speak_wait(text: str):
    """Queue text to be spoken and wait for it to finish."""
    speak(text)
    _speech_done_event.wait()
    _speech_done_event.clear()

def shutdown():
    """Call this on program exit to cleanly stop the TTS thread."""
    _speech_queue.put(None)
    _thread.join()

async def _openai_tts(text: str):
    async with openai.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="ash",
        input=text,
        instructions="speak in a monotonous robotic voice but not slow and a bit cheerful.",
        response_format="pcm",
    ) as response:
        await LocalAudioPlayer().play(response)

def _tts_worker():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        text = _speech_queue.get()
        if text is None:
            break  # Exit signal
        _speech_done_event.clear()
        try:
            loop.run_until_complete(_openai_tts(text))
        except Exception as e:
            print(f"TTS error: {e}")
        _speech_done_event.set()
        _speech_queue.task_done()
    loop.close()

_thread = threading.Thread(target=_tts_worker, daemon=True)
_thread.start()