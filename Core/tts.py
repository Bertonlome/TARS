import pyttsx3
import threading
import queue
import re
from typing import Any

_engine = pyttsx3.init()
_engine.setProperty('rate', 155)
_engine.setProperty('volume', 0.9)
voices: Any = _engine.getProperty('voices')  # Type is a list-like object from pyttsx3
if voices and len(voices) > 1:
    _engine.setProperty('voice', voices[1].id)

# Warm up the engine with a dummy call to avoid first-call initialization delay
_engine.say("")
_engine.runAndWait()

_speech_queue = queue.Queue()

# Reference to agent for variable interpolation
_agent_ref = None

# Callbacks for speech events
_speak_callbacks = []  # Called when speech starts
_finished_callbacks = []  # Called when speech finishes

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
    while True:
        text = _speech_queue.get()
        if text is None:
            break  # Exit signal
        
        # Format the text with variable interpolation
        formatted_text = format_callout(text)
        
        # Fire speaking callbacks right before speaking
        for cb in _speak_callbacks:
            try:
                cb(formatted_text)
            except Exception as e:
                print(f"Error in TTS speak callback: {e}")
        
        # Speak the formatted text
        _engine.say(formatted_text)
        _engine.runAndWait()
        
        # Mark task as done (for queue.join() synchronization)
        _speech_queue.task_done()
        
        # Fire finished callbacks
        for cb in _finished_callbacks:
            try:
                cb(formatted_text)
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
    _speech_queue.put(text)

def shutdown():
    """Call this on program exit to cleanly stop the TTS thread."""
    _speech_queue.put(None)
    _thread.join()