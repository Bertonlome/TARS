"""
Ingescape Message Protocol
Defines all I/O for communication between TARS Agent and GUI Agent

This protocol specifies the message format and semantics for decoupled communication
between the TARS automation agent and the GUI interface via Ingescape bus.
"""

from enum import Enum
from typing import Dict, List, Any


class MessageType(Enum):
    """Message type categories"""
    STATE = "state"
    ACTION = "action"
    ALERT = "alert"
    TTS = "tts"
    APPROVAL = "approval"
    CONTROL = "control"


# ============================================================================
# TARS AGENT → GUI AGENT (Outputs from TARS)
# ============================================================================

TARS_OUTPUTS = {
    # FSM State Updates
    "current_state": {
        "type": "string",  # JSON encoded
        "description": "Current FSM state with all attributes",
        "format": {
            "procedure": "str - Procedure name (e.g., 'BEFORE TAKEOFF')",
            "classification": "str - NORM, EMER, or ABNORM",
            "type": "str - Task type",
            "category": "str - Task category",
            "task_object": "str - Task object description",
            "value": "str - Expected value/action",
            "human_role": "str - Human's role for this task",
            "autonomy_role": "str - Automation's role (performer/supporter/monitor)",
            "delay_before_action": "float/str - Seconds before action or 'is_acked'",
            "delay_after_action": "float/str - Seconds after action or 'is_acked'",
            "callout": "str - TTS callout text (may contain {interpolation} markers)",
            "interaction": "str - UI interaction type (optional)",
            "condition_type": "str - 'continuous' or 'transition' (optional)",
            "condition_function": "str - Name of condition function (optional)",
        },
        "example": '{"procedure": "BEFORE TAKEOFF", "task_object": "Pitot Heat", "value": "ON", "autonomy_role": "performer", ...}'
    },
    
    "next_state": {
        "type": "string",  # JSON encoded
        "description": "Upcoming FSM state (for preview/timeline)",
        "format": "Same as current_state",
    },
    
    "previous_state": {
        "type": "string",  # JSON encoded
        "description": "Previous FSM state (for history tracking)",
        "format": "Same as current_state",
    },
    
    # Countdown Timers
    "countdown_current": {
        "type": "integer",
        "description": "Current task countdown value in seconds (delay_before_action)",
        "range": "0-600",
    },
    
    "countdown_next": {
        "type": "integer",
        "description": "Next task countdown value in seconds (estimated)",
        "range": "0-3600",
    },
    
    "countdown_max_current": {
        "type": "integer",
        "description": "Maximum value for current countdown (for progress calculation)",
        "range": "0-600",
    },
    
    "countdown_max_next": {
        "type": "integer",
        "description": "Maximum value for next countdown (for progress calculation)",
        "range": "0-3600",
    },
    
    # Alerts and Notifications
    "alert": {
        "type": "string",  # JSON encoded
        "description": "Alert message with severity",
        "format": {
            "message": "str - Alert text",
            "color": "str - Alert color (red/yellow/blue/green)",
            "severity": "str - critical/warning/info",
            "timestamp": "float - Unix timestamp",
        },
        "example": '{"message": "Engine Fire Detected", "color": "red", "severity": "critical"}'
    },
    
    "alert_clear": {
        "type": "impulsion",
        "description": "Clear current alert display",
    },
    
    # Condition Monitoring
    "condition_violated": {
        "type": "string",  # JSON encoded
        "description": "Continuous condition no longer met",
        "format": {
            "procedure": "str",
            "task_object": "str",
            "value": "str",
            "condition_name": "str - Name of violated condition function",
            "timestamp": "float",
        },
    },
    
    "condition_restored": {
        "type": "string",  # JSON encoded
        "description": "Previously violated condition now restored",
        "format": "Same as condition_violated",
    },
    
    # TTS Status
    "tts_speaking": {
        "type": "bool",
        "description": "True when TTS is actively speaking, False when finished",
    },
    
    "tts_text": {
        "type": "string",
        "description": "Current TTS text being spoken (for display)",
    },
    
    # Action Notifications
    "action_about_to_fire": {
        "type": "string",  # JSON encoded
        "description": "Action is about to execute (after countdown, before execution)",
        "format": "Same as current_state",
    },
    
    # Checklist Progress
    "checklist_item_complete": {
        "type": "string",  # JSON encoded
        "description": "Checklist item marked complete",
        "format": {
            "procedure": "str",
            "task_object": "str",
            "value": "str",
        },
    },
    
    # Emergency Procedure Injection
    "emergency_procedure_inject": {
        "type": "string",
        "description": "Emergency procedure name to inject into timeline",
        "example": "ENGINE FIRE L"
    },
    
    # Interaction Panel Messages
    "interaction_message": {
        "type": "string",  # JSON encoded
        "description": "Message and optional TARS input for interaction panel with button configuration",
        "format": {
            "message": "str - Main message text",
            "tars_input": "str - Optional TARS reasoning/input (default empty)",
            "left_button": "str - Left button text (None=hide, empty string=no change, text=show with text)",
            "right_button": "str - Right button text (None=hide, empty string=no change, text=show with text)",
        },
    },
}


# ============================================================================
# GUI AGENT → TARS AGENT (Inputs to TARS)
# ============================================================================

TARS_INPUTS = {
    # Task Approvals
    "task_approval": {
        "type": "bool",
        "description": "User approved/denied current task (True=approved, False=denied)",
    },
    
    "task_acknowledged": {
        "type": "impulsion",
        "description": "User acknowledged completion of current task",
    },
    
    "task_cancelled": {
        "type": "impulsion",
        "description": "User cancelled current action (reclaim authority)",
    },
    
    # FSM Control
    "start_procedure": {
        "type": "impulsion",
        "description": "Start FSM execution",
    },
    
    "stop_procedure": {
        "type": "impulsion",
        "description": "Stop/pause FSM execution",
    },
    
    "emergency_inject": {
        "type": "string",
        "description": "Emergency procedure name to inject (e.g., 'ENGINE FIRE L')",
    },
    
    "force_state_jump": {
        "type": "string",  # JSON encoded
        "description": "Force FSM to jump to specific state (from checklist/timeline clicks)",
        "format": {
            "procedure": "str - Target procedure name",
            "task_object": "str - Target task object",
            "value": "str - Target value",
        },
        "example": '{"procedure": "BEFORE TAKEOFF", "task_object": "Pitot Heat", "value": "ON"}'
    },
    
    # Countdown Synchronization
    "countdown_complete": {
        "type": "impulsion",
        "description": "Countdown timer reached zero (signals FSM to continue)",
    },
    
    # Speech Commands
    "speech_command": {
        "type": "string",
        "description": "Voice command from STT (e.g., 'start engine', 'abort')",
    },
}


# ============================================================================
# ATC AGENT ↔ TARS AGENT (Existing - for reference)
# ============================================================================

ATC_INTERFACE = {
    "TARS → ATC": {
        "request_takeoff_clearance": "impulsion",
        "communicate_atc": "string - ATC communication message",
        "position_report": "string - Position report message",
    },
    "ATC → TARS": {
        "atc_response": "string - ATC response message",
        "clearance_received": "impulsion",
    },
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def encode_state_to_json(state) -> str:
    """
    Encode State object to JSON string for transmission
    
    Args:
        state: State object from Core.fsm
        
    Returns:
        JSON string representation
    """
    import json
    return json.dumps({
        "procedure": state.procedure,
        "classification": state.classification,
        "type": state.type,
        "category": state.category,
        "task_object": state.task_object,
        "value": state.value,
        "human_role": state.human_role,
        "autonomy_role": state.autonomy_role,
        "information_requirement": state.information_requirement,
        "interaction": state.interaction,
        "delay_before_action": state.delay_before_action,
        "delay_after_action": state.delay_after_action,
        "callout": state.callout,
        "condition": state.condition,
        "condition_type": state.condition_type,
        "condition_function": state.condition_function,
        "monitor_scope": state.monitor_scope,
    })


def decode_json_to_dict(json_str: str) -> Dict[str, Any]:
    """
    Decode JSON string to dictionary
    
    Args:
        json_str: JSON string
        
    Returns:
        Dictionary with decoded data
    """
    import json
    return json.loads(json_str)


def create_alert_message(message: str, color: str = "red", severity: str = "warning") -> str:
    """
    Create alert message JSON
    
    Args:
        message: Alert text
        color: Alert color (red/yellow/blue/green)
        severity: critical/warning/info
        
    Returns:
        JSON string
    """
    import json
    import time
    return json.dumps({
        "message": message,
        "color": color,
        "severity": severity,
        "timestamp": time.time(),
    })


def create_condition_message(procedure: str, task_object: str, value: str, condition_name: str) -> str:
    """
    Create condition violation/restoration message
    
    Args:
        procedure: Procedure name
        task_object: Task object
        value: Task value
        condition_name: Condition function name
        
    Returns:
        JSON string
    """
    import json
    import time
    return json.dumps({
        "procedure": procedure,
        "task_object": task_object,
        "value": value,
        "condition_name": condition_name,
        "timestamp": time.time(),
    })


def create_interaction_message(message: str, tars_input: str = "", 
                              left_button: str = "", right_button: str = "",
                              middle_button: str = "",
                              extra_data: dict = None) -> str:
    """
    Create interaction panel message JSON
    
    Args:
        message: Main message text (empty string = None, preserves existing UI text)
        tars_input: Optional TARS reasoning/input (empty string = None, preserves existing UI text)
        left_button: Left button text (empty string = no change, None = hide, text = show with text)
        right_button: Right button text (empty string = no change, None = hide, text = show with text)
        extra_data: Optional dict with additional fields merged into the JSON payload (e.g. runway_heading)
        
    Returns:
        JSON string
        
    Note:
        Empty strings are converted to None to signal "no update" to GUI
        For buttons: empty string = no change, explicit None = hide, text = show with that text
    """
    import json
    payload = {
        "message": message if message else None,
        "tars_input": tars_input if tars_input else None,
    }
    
    # Only include button config if explicitly set (not empty string)
    if left_button != "":
        payload["left_button"] = left_button
    if right_button != "":
        payload["right_button"] = right_button
    if middle_button != "":
        payload["middle_button"] = middle_button

    # Merge any extra domain-specific metadata
    if extra_data:
        payload.update(extra_data)
        
    return json.dumps(payload)


# ============================================================================
# PROTOCOL SUMMARY
# ============================================================================

PROTOCOL_SUMMARY = """
TARS-GUI Ingescape Protocol Summary
====================================

Communication Pattern:
- TARS Agent: Pure Python, publishes state via Ingescape outputs
- GUI Agent: Qt-based, subscribes to TARS outputs, sends user inputs

Key Message Flows:
1. FSM State Updates: TARS → GUI (current_state, next_state JSON)
2. Countdowns: TARS → GUI (countdown values) | GUI → TARS (countdown_complete)
3. Alerts: TARS → GUI (alert JSON, alert_clear)
4. Approvals: GUI → TARS (task_approval, specific approval integers)
5. TTS Status: TARS → GUI (tts_speaking bool, tts_text)
6. Conditions: TARS → GUI (condition_violated/restored JSON)
7. Emergency: TARS → GUI (emergency_procedure_inject) | GUI → TARS (emergency_inject)

Benefits:
- Technology Independence: TARS agent has no Qt dependencies
- Distributed: Can run agents on separate machines
- Testable: Mock Ingescape messages for unit testing
- Scalable: Multiple GUIs can observe same TARS agent
- Maintainable: Clear message contracts between components
"""


if __name__ == "__main__":
    # Print protocol documentation
    print(PROTOCOL_SUMMARY)
    print("\n" + "="*60)
    print("TARS OUTPUTS (TARS → GUI):")
    print("="*60)
    for name, spec in TARS_OUTPUTS.items():
        print(f"\n{name}:")
        print(f"  Type: {spec['type']}")
        print(f"  Description: {spec['description']}")
        if 'example' in spec:
            print(f"  Example: {spec['example']}")
    
    print("\n" + "="*60)
    print("TARS INPUTS (GUI → TARS):")
    print("="*60)
    for name, spec in TARS_INPUTS.items():
        print(f"\n{name}:")
        print(f"  Type: {spec['type']}")
        print(f"  Description: {spec['description']}")
