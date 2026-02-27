import threading
import queue
import re
import hashlib
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
            
            # Play audio (blocking) — same for both cached and freshly generated
            sd.play(audio, _sample_rate)
            sd.wait()
            
            # Mark task as done (for queue.join() synchronization)
            _speech_queue.task_done()
            
            # Fire finished callbacks
            for cb in _finished_callbacks:
                try:
                    cb(formatted_text)
                except Exception as e:
                    print(f"Error in TTS finished callback: {e}")
                    
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
    _speech_queue.put(text)

def stop():
    """Immediately stop current TTS playback and discard any queued speech."""
    # Stop sounddevice audio stream immediately
    try:
        sd.stop()
    except Exception:
        pass

    # Drain all pending items from the queue
    drained = 0
    while True:
        try:
            _speech_queue.get_nowait()
            _speech_queue.task_done()
            drained += 1
        except queue.Empty:
            break

    if drained:
        print(f"🛑 TTS stop: drained {drained} queued item(s)")

    # Fire finished callbacks so is_speaking resets to False
    for cb in _finished_callbacks:
        try:
            cb("")
        except Exception:
            pass

def shutdown():
    """Call this on program exit to cleanly stop the TTS thread."""
    _speech_queue.put(None)
    _thread.join()