import threading
import queue
import re
import hashlib
import time
from pathlib import Path
from typing import Any
import sounddevice as sd
import numpy as np
import torch

# Initialize Silero TTS
try:
    print("🔊 Initializing Silero TTS...")
    
    # Load Silero TTS model from torch hub
    _device = torch.device('cpu')  # Use CPU for compatibility
    _tts_model, _example_text = torch.hub.load(
        repo_or_dir='snakers4/silero-models',
        model='silero_tts',
        language='en',
        speaker='v3_en'
    )
    _tts_model.to(_device)
    
    # Silero speakers - Available voices:
    # 'en_0' - Female voice (medium pitch)
    # 'en_1' - Female voice (higher pitch) 
    # 'en_2' - Male voice (lower pitch) - DEFAULT for ATC/pilot
    # 'en_3' - Male voice (higher pitch)
    # 'en_4' - Male voice (very deep)
    # More info: https://github.com/snakers4/silero-models
    _speaker = 'en_0'  # Change this to use a different voice
    _sample_rate = 48000
    
    print("✅ Silero TTS initialized successfully")
except Exception as e:
    print(f"❌ Failed to initialize Silero TTS: {e}")
    print("   Please install: pip install torch sounddevice")
    raise

# ---------------------------------------------------------------------------
# Audio cache
# ---------------------------------------------------------------------------
# Cache lives at  tts/cache/  relative to this file.
# Each entry is a <md5-of-processed-text>.npy file storing a float32 array.
# The cache key is derived from the *fully-processed* text (after variable
# interpolation, acronym expansion and letter/digit conversion) so that
# identical spoken sentences always hit the same cache entry regardless of
# the raw caller text.

_CACHE_DIR = Path(__file__).parent / "cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_MP3_CACHE_DIR = Path(__file__).parent / "mp3_cache"
_MP3_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(text: str) -> str:
    """Return a hex digest that uniquely identifies *text*."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _cache_path(text: str) -> Path:
    """Return the .npy cache file path for *text*."""
    return _CACHE_DIR / f"{_cache_key(text)}.npy"


def _load_from_cache(text: str) -> "np.ndarray | None":
    """Load cached audio for *text*, or return None if not cached."""
    path = _cache_path(text)
    if path.exists():
        try:
            return np.load(str(path))
        except Exception as e:
            print(f"⚠️  TTS cache read error ({path.name}): {e}")
    return None


def _save_to_cache(text: str, audio: np.ndarray) -> None:
    """Persist *audio* to the cache directory for later retrieval."""
    path = _cache_path(text)
    try:
        np.save(str(path), audio)
        print(f"💾 TTS cached: {path.name}")
    except Exception as e:
        print(f"⚠️  TTS cache write error ({path.name}): {e}")


_speech_queue = queue.Queue()

# Reference to agent for variable interpolation
_agent_ref = None

# Last raw text that was queued for speaking (used by repeat_last)
_last_queued_text: "str | None" = None

# Stop-generation counter — incremented by stop() so the worker detects
# mid-sentence interrupts.  Protected by _stop_generation_lock.
_stop_generation: int = 0
_stop_generation_lock = threading.Lock()

# Mute flag — when True, incoming sentences are silently discarded unless
# they are ATC bypass sentences (contain specific callsign keywords).
_muted: bool = False
_muted_lock = threading.Lock()

# ATC-speaking gate — cleared while ATC is playing audio so the TTS worker
# blocks before starting playback; set (clear path) when ATC is idle.
# Initialised to set so TTS plays immediately when ATC is idle at startup.
_atc_clear_event = threading.Event()
_atc_clear_event.set()  # ATC is idle at startup


def set_atc_speaking(is_speaking: bool) -> None:
    """Called by the TTS agent when ATC_Agent.is_speaking changes.

    Blocks the TTS worker while ATC is playing, releases it when ATC stops.
    """
    if is_speaking:
        _atc_clear_event.clear()   # TTS worker will block at the gate
        print("📵 ATC speaking — TTS playback gated")
    else:
        _atc_clear_event.set()     # Wake any waiting TTS worker
        print("📵 ATC done — TTS playback gate released")

# Keywords that cause a sentence to bypass the mute and always play.
# These are pilot ATC readbacks that must be audible regardless of mute state.
_ATC_BYPASS_KEYWORDS = ["C-POLY", "Cessna Charlie Papa Oscar Lima Yankee"]


def _is_atc_bypass(text: str) -> bool:
    """Return True if *text* contains an ATC callsign keyword and must bypass mute."""
    tl = text.lower()
    return any(kw.lower() in tl for kw in _ATC_BYPASS_KEYWORDS)



# Callbacks for speech events
_speak_callbacks = []  # Called when speech starts
_finished_callbacks = []  # Called when speech finishes

# Digit to word mapping for aviation-style number reading
_DIGIT_MAP = {
    '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
    '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'niner'
}

# Letter pronunciation mapping for aviation callouts
_LETTER_MAP = {
    'A': 'ay', 'B': 'bee', 'C': 'see', 'D': 'dee', 'E': 'ee',
    'F': 'eff', 'G': 'jee', 'H': 'aych', 'I': 'eye', 'J': 'jay',
    'K': 'kay', 'L': 'ell', 'M': 'emm', 'N': 'enn', 'O': 'oh',
    'P': 'pee', 'Q': 'queue', 'R': 'arr', 'S': 'ess', 'T': 'tee',
    'U': 'you', 'V': 'vee', 'W': 'double you', 'X': 'ecks', 'Y': 'why', 'Z': 'zee'
}

# Acronym translations - add custom acronyms here that need special pronunciation
_ACRONYM_MAP = {
    'ATC': 'ay tee cee',
    'FLC': 'eff ell see',
    'ILS': 'eye ell ess',
    'VOR': 'vee oh arr',
    # Add more acronyms as needed, e.g.:
    # 'FLC': 'eff ell see',
    # 'ILS': 'eye ell ess',
    # 'VOR': 'vee oh arr',
}

def convert_acronyms(text: str) -> str:
    """Convert known acronyms to their phonetic pronunciation
    
    Args:
        text: Text with potential acronyms
        
    Returns:
        Text with acronyms replaced
    """
    result = text
    for acronym, pronunciation in _ACRONYM_MAP.items():
        # Use word boundaries to avoid partial matches
        import re
        pattern = r'\b' + re.escape(acronym) + r'\b'
        result = re.sub(pattern, pronunciation, result, flags=re.IGNORECASE)
    return result

def convert_letters_and_numbers(text: str) -> str:
    """Convert standalone letters and numbers to proper pronunciation
    
    Handles aviation callouts like:
        "V1" -> "vee one"
        "V2" -> "vee two"
        "VR" -> "vee arr"
        "FLC V two" -> "eff ell see vee two"
    
    Args:
        text: Text with letters and numbers
        
    Returns:
        Text with letters and numbers converted to words
    """
    result = []
    i = 0
    
    while i < len(text):
        char = text[i]
        
        # Check if it's a letter (uppercase or lowercase standalone)
        if char.isalpha():
            # Check if it's a standalone letter or part of a word
            # Standalone if: start of string, preceded by space/punctuation, or followed by digit/space/punctuation
            is_standalone = False
            
            # Check previous character
            prev_ok = (i == 0) or (not text[i-1].isalpha())
            
            # Check next character  
            next_ok = (i == len(text) - 1) or (not text[i+1].isalpha())
            
            # If both conditions met, it's a standalone letter
            if prev_ok and next_ok:
                is_standalone = True
            
            if is_standalone and char.upper() in _LETTER_MAP:
                # Add space before if previous character was alphanumeric
                if result and result[-1] not in (' ', '-', '.', ','):
                    result.append(' ')
                result.append(_LETTER_MAP[char.upper()])
                # Add space after if next character is alphanumeric
                if i + 1 < len(text) and (text[i+1].isalnum()):
                    result.append(' ')
            else:
                result.append(char)
            i += 1
            
        # Handle numbers - convert digit by digit
        elif char.isdigit():
            # Add space before if previous character was alphanumeric
            if result and result[-1] not in (' ', '-', '.', ','):
                result.append(' ')
            result.append(_DIGIT_MAP[char])
            # Add space after if next character is alphanumeric
            if i + 1 < len(text) and (text[i+1].isalnum()):
                result.append(' ')
            i += 1
            
        else:
            result.append(char)
            i += 1
    
    return ''.join(result)

def set_agent_reference(agent):
    """Set reference to agent for variable interpolation in callouts
    
    Args:
        agent: TarsAgent instance with attributes to interpolate
    """
    global _agent_ref
    _agent_ref = agent

def format_callout(text: str) -> str:
    """Format callout text by replacing {variable_name} with agent attribute values
    
    Examples:
        "FLC V two {V_TWO}" -> "FLC V two 97 knots"
        "Heading {heading_i}" -> "Heading 057"
        
    Args:
        text: Callout text with optional {variable_name} placeholders
        
    Returns:
        Formatted text with variables replaced by their values
    """
    if not _agent_ref:
        return text
    
    # Find all {variable_name} patterns
    pattern = r'\{([^}]+)\}'
    matches = re.findall(pattern, text)
    
    for var_name in matches:
        var_name_stripped = var_name.strip()
        
        # Try to get the value from agent or global variables
        value = None
        
        # First, try agent attributes (lowercase with _i suffix for inputs)
        if hasattr(_agent_ref, var_name_stripped):
            value = getattr(_agent_ref, var_name_stripped)
        # Try with _i suffix (common for inputs like heading_i)
        elif hasattr(_agent_ref, f"{var_name_stripped}_i"):
            value = getattr(_agent_ref, f"{var_name_stripped}_i")
        # Try global variables in agent module (like V_TWO, V_ONE)
        elif hasattr(_agent_ref, var_name_stripped.upper()):
            value = getattr(_agent_ref, var_name_stripped.upper())
        else:
            # Check if it's a module-level constant (V_TWO, etc)
            try:
                import Core.agent as agent_module
                if hasattr(agent_module, var_name_stripped.upper()):
                    value = getattr(agent_module, var_name_stripped.upper())
            except:
                pass
        
        # Format the value if found
        if value is not None:
            # Format numbers nicely
            if isinstance(value, float):
                if value.is_integer():
                    formatted_value = str(int(value))
                else:
                    formatted_value = f"{value:.1f}"
            elif isinstance(value, int):
                # Format heading/angles with leading zeros (e.g., 057)
                if 'heading' in var_name_stripped.lower() or 'runway' in var_name_stripped.lower():
                    formatted_value = f"{value:03d}"
                else:
                    formatted_value = str(value)
            else:
                formatted_value = str(value)
            
            # Replace the placeholder
            text = text.replace(f"{{{var_name}}}", formatted_value)
        else:
            # Variable not found - leave placeholder or remove it
            print(f"⚠️  TTS variable not found: {var_name_stripped}")
            text = text.replace(f"{{{var_name}}}", f"[{var_name_stripped}]")
    
    return text

def _tts_worker():
    """Worker thread that processes TTS queue and plays audio"""
    while True:
        text = _speech_queue.get()
        if text is None:
            break  # Exit signal
        
        try:
            # Format the text with variable interpolation
            display_text = format_callout(text)

            # ---------------------------------------------------------------
            # Mute check: silently discard non-ATC sentences when muted.
            # ATC bypass sentences (pilot readbacks) always play.
            # ---------------------------------------------------------------
            with _muted_lock:
                is_muted = _muted
            if is_muted and not _is_atc_bypass(display_text):
                print(f"🔇 TTS muted: discarding '{display_text[:50]}'")
                _speech_queue.task_done()
                continue

            # ---------------------------------------------------------------
            # ATC gate: if ATC is currently broadcasting, wait until it stops
            # before starting our own audio (avoids simultaneous playback).
            # ---------------------------------------------------------------
            if not _atc_clear_event.is_set():
                print("⏳ TTS waiting for ATC to finish...")
                _atc_clear_event.wait()
                print("▶️ ATC finished — resuming TTS")

            # Convert acronyms first (for audio only)
            formatted_text = convert_acronyms(display_text)
            
            # Convert letters and numbers to proper pronunciation (for audio only)
            formatted_text = convert_letters_and_numbers(formatted_text)
            
            # Fire speaking callbacks with the human-readable text (pre-pronunciation transforms)
            # so the UI displays "ATC" instead of "ay tee cee"
            # (identical behaviour whether audio comes from cache or the model)
            for cb in _speak_callbacks:
                try:
                    cb(display_text)
                except Exception as e:
                    print(f"Error in TTS speak callback: {e}")
            
            # ------------------------------------------------------------------
            # Cache lookup
            # ------------------------------------------------------------------
            audio = _load_from_cache(formatted_text)
            if audio is not None:
                print(f"🎵 TTS cache hit: playing cached audio")
            else:
                # Generate speech with Silero
                print(f"🔊 TTS generating: {formatted_text[:60]}...")
                audio = _tts_model.apply_tts(
                    text=formatted_text,
                    speaker=_speaker,
                    sample_rate=_sample_rate
                )
                
                # Convert to numpy array if it's a tensor
                if torch.is_tensor(audio):
                    audio = audio.cpu().numpy()
                
                # Ensure audio is in correct format (float32, values between -1 and 1)
                if audio.dtype != np.float32:
                    audio = audio.astype(np.float32)
                
                # Add silence padding at the end to prevent truncation (300ms)
                silence_duration = 0.3  # seconds
                silence_samples = int(_sample_rate * silence_duration)
                silence = np.zeros(silence_samples, dtype=np.float32)
                audio = np.concatenate([audio, silence])
                
                # Persist to cache so future calls skip the model
                _save_to_cache(formatted_text, audio)
            
            # Play audio — mutable via stop().
            # Each sentence gets its own OutputStream so there is no shared
            # stream state that can be corrupted.  When stop() is called the
            # generation counter changes; the callback detects this, outputs
            # silence and raises CallbackStop to end the stream cleanly.
            with _stop_generation_lock:
                my_generation = _stop_generation

            audio_pos = 0
            stopped_early = False
            playback_done = threading.Event()

            def _audio_cb(outdata, frames, time_info, status,
                          _gen=my_generation):
                nonlocal audio_pos, stopped_early
                with _stop_generation_lock:
                    should_mute = _stop_generation != _gen
                if should_mute:
                    stopped_early = True
                    outdata[:] = 0
                    raise sd.CallbackStop()
                remaining = len(audio) - audio_pos
                chunk = min(frames, remaining)
                if chunk > 0:
                    outdata[:chunk, 0] = audio[audio_pos:audio_pos + chunk]
                    audio_pos += chunk
                if chunk < frames:
                    outdata[chunk:] = 0
                if audio_pos >= len(audio):
                    raise sd.CallbackStop()

            with sd.OutputStream(
                samplerate=_sample_rate,
                channels=1,
                dtype='float32',
                callback=_audio_cb,
                finished_callback=playback_done.set
            ):
                playback_done.wait()

            # Mark task as done (for queue.join() synchronization)
            _speech_queue.task_done()

            # Fire finished callbacks only if the sentence played to completion
            # (stopped_early sentences are silently discarded so the next
            # queued item resumes immediately without a spurious is_speaking
            # flip-flop)
            if not stopped_early:
                for cb in _finished_callbacks:
                    try:
                        cb(formatted_text)
                    except Exception as e:
                        print(f"Error in TTS finished callback: {e}")
            else:
                print(f"⏹️  TTS sentence interrupted — skipping finished callbacks")
                    
        except Exception as e:
            print(f"❌ TTS error: {e}")
            import traceback
            traceback.print_exc()
            _speech_queue.task_done()  # Still mark as done to prevent blocking

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
    global _last_queued_text
    _last_queued_text = text
    _speech_queue.put(text)

def stop():
    """Interrupt the currently playing sentence (one-shot, does not mute future sentences).

    Increments the stop-generation counter so the audio callback outputs
    silence and ends the stream cleanly.  Does NOT call sd.stop() — that
    would corrupt the PortAudio device state and prevent subsequent
    sentences from playing.
    """
    global _stop_generation
    with _stop_generation_lock:
        _stop_generation += 1


def mute():
    """Persistently mute TTS: discard all future sentences until unmute() is called.

    Also interrupts the currently playing sentence immediately.
    ATC bypass sentences (pilot readbacks) will still play through the mute.
    """
    global _muted
    with _muted_lock:
        _muted = True
    stop()  # Interrupt the current sentence


def unmute():
    """Re-enable TTS playback after a previous mute() call."""
    global _muted
    with _muted_lock:
        _muted = False
    print("🔊 TTS unmuted — playback re-enabled")


def _drain_queue():
    """Discard all pending items from the speech queue."""
    drained = 0
    while True:
        try:
            _speech_queue.get_nowait()
            _speech_queue.task_done()
            drained += 1
        except queue.Empty:
            break
    if drained:
        print(f"🗑️  TTS queue drained: {drained} item(s) discarded")


def repeat_last():
    """Replay the last spoken sentence from cache.

    Clears any pending queued items so the repeat plays immediately, then
    re-queues the last sentence.  Does NOT call stop() — the generation
    counter is left unchanged so the worker's polling loop is not
    disturbed.  If the user pressed tts_stop before calling this, the
    worker has already exited its polling loop and is idle at queue.get();
    calling stop() again here would only corrupt the audio device state
    with a redundant sd.stop() on an already-closed stream.
    """
    if _last_queued_text is None:
        print("⚠️  TTS repeat: nothing has been spoken yet")
        return
    print(f"🔁 TTS repeat: replaying last sentence")
    _drain_queue()  # Clear any pending items so repeat plays next
    speak_wait(_last_queued_text)


def save_as_mp3(text: str) -> Path | None:
    """Synthesise *text* with TTS and save the result as an MP3 in tts/mp3_cache/.

    The output filename is ``<text>.mp3``.  Characters that are illegal in
    file names are replaced with underscores so the name is always valid.
    The function is synchronous and returns the saved :class:`~pathlib.Path`,
    or *None* on failure.
    """
    import subprocess
    import tempfile
    import soundfile as sf

    if not text or not text.strip():
        print("⚠️  save_as_mp3: empty text — skipping")
        return None

    # Build a safe filename from the raw text.
    safe_name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", text.strip())
    safe_name = safe_name[:200]  # cap length
    mp3_path = _MP3_CACHE_DIR / f"{safe_name}.mp3"

    print(f"💾 save_as_mp3: synthesising '{text[:60]}...' → {mp3_path.name}")

    try:
        # Apply the same text processing pipeline used by the TTS worker.
        processed = convert_letters_and_numbers(convert_acronyms(text))

        # Fetch from .npy cache or synthesise fresh.
        audio = _load_from_cache(processed)
        if audio is None:
            audio = _tts_model.apply_tts(
                text=processed,
                speaker=_speaker,
                sample_rate=_sample_rate
            )
            if torch.is_tensor(audio):
                audio = audio.cpu().numpy()
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)
            # Add 300 ms silence tail (matches worker behaviour).
            silence = np.zeros(int(_sample_rate * 0.3), dtype=np.float32)
            audio = np.concatenate([audio, silence])
            _save_to_cache(processed, audio)

        # Write a temporary WAV file and convert to MP3 with ffmpeg.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = Path(tmp.name)

        sf.write(str(tmp_wav), audio, _sample_rate, subtype="PCM_16")

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp_wav), "-codec:a", "libmp3lame",
             "-qscale:a", "2", str(mp3_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tmp_wav.unlink(missing_ok=True)

        if result.returncode != 0:
            print(f"❌ save_as_mp3: ffmpeg conversion failed (exit {result.returncode})")
            return None

        print(f"✅ save_as_mp3: saved {mp3_path}")
        return mp3_path

    except Exception as exc:
        print(f"❌ save_as_mp3: {exc}")
        import traceback
        traceback.print_exc()
        return None


def shutdown():
    """Call this on program exit to cleanly stop the TTS thread."""
    _speech_queue.put(None)
    _thread.join()