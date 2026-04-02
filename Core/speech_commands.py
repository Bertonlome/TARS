"""
Speech command definitions and matching logic for TARS agent.
"""

from typing import Optional, List
from dataclasses import dataclass


@dataclass
class Command:
    """Speech command configuration"""
    action: str  # Action identifier (e.g., "next_step", "approve")
    keywords: List[str]  # Trigger phrases
    requires_exact: bool = False  # True = exact match, False = contains
    answer: str = ""  # Optional spoken answer
    description: str = ""  # Human-readable description


# Define all speech commands
COMMANDS = [
    # Dev mode navigation
    Command(
        action="next_step",
        keywords=["next", "next step"],
        requires_exact=False,
        description="Advance FSM to next state"
    ),
    Command(
        action="previous_step",
        keywords=["previous", "previous step", "back", "go back", "rewind"],
        requires_exact=False,
        description="Return to previous FSM state"
    ),
    
    # Approvals (exact match for safety-critical operations)
    Command(
        action="approve",
        keywords=["approve", "approved", "affirmative", "confirm", "roger", "accept", "yes"],
        requires_exact=False,
        answer = "Action approved.",
        description="Approve pending action or request"
    ),
    Command(
        action="deny",
        keywords=["cancel", "canceled", "deny", "denied", "negative", "abort", "no"],
        requires_exact=False,
        answer = "Action denied.",
        description="Deny pending action or request"
    ),
    
    # Task acknowledgment
    Command(
        action="acknowledge",
        keywords=["check", "checked", "chick", "shake", "jack", "okay", "done", "complete", "completed", "pic", "cig", "confirm", "confirmed"],
        requires_exact=False,
        description="Acknowledge task completion"
    ),
]


def match_command(text: str) -> Optional[Command]:
    """
    Match recognized speech text to a command.
    Returns the FIRST matching command only.
    
    Args:
        text: Recognized speech text from STT
        
    Returns:
        Matched Command object or None if no match found
        
    Example:
        >>> cmd = match_command("yes")
        >>> if cmd:
        ...     print(cmd.action)  # "approve"
    """
    if not text:
        return None
    
    text_lower = text.lower().strip()
    
    for cmd in COMMANDS:
        if cmd.requires_exact:
            # Exact match required - text must be exactly one of the keywords
            if text_lower in cmd.keywords:
                return cmd
        else:
            # Partial match - any keyword present in text
            if any(keyword in text_lower for keyword in cmd.keywords):
                return cmd
    
    return None


def match_all_commands(text: str) -> List[Command]:
    """
    Match recognized speech text to ALL matching commands.
    Returns list of all commands that match (useful for multi-action words like "confirm").
    
    Args:
        text: Recognized speech text from STT
        
    Returns:
        List of matched Command objects (empty list if no matches)
        
    Example:
        >>> cmds = match_all_commands("confirm")
        >>> for cmd in cmds:
        ...     print(cmd.action)  # May print both "approve" and "acknowledge"
    """
    if not text:
        return []
    
    text_lower = text.lower().strip()
    matched_commands = []
    
    for cmd in COMMANDS:
        if cmd.requires_exact:
            # Exact match required - text must be exactly one of the keywords
            if text_lower in cmd.keywords:
                matched_commands.append(cmd)
        else:
            # Partial match - any keyword present in text
            if any(keyword in text_lower for keyword in cmd.keywords):
                matched_commands.append(cmd)
    
    return matched_commands
    for cmd in COMMANDS:
        if cmd.requires_exact:
            # Exact match required - text must be exactly one of the keywords
            if text_lower in cmd.keywords:
                return cmd
        else:
            # Partial match - any keyword present in text
            if any(keyword in text_lower for keyword in cmd.keywords):
                return cmd
    
    return None


def get_action(text: str) -> Optional[str]:
    """
    Quick helper to get just the action name from text.
    
    Args:
        text: Recognized speech text
        
    Returns:
        Action name string or None
    """
    cmd = match_command(text)
    return cmd.action if cmd else None


def list_all_commands() -> List[Command]:
    """Return all defined commands (useful for debugging/UI display)"""
    return COMMANDS.copy()
