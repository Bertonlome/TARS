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
        keywords=["yes", "approved", "affirmative", "confirm", "roger", "accept", "accepted",  "allow", "continue", "proceed", "go ahead", "by all means", "certainly", "definitely", "of course", "sure thing", "you bet", "absolutely", "without a doubt", "gladly", "willingly", "indeed", "naturally", "positively", "unquestionably", "beyond any doubt", "most assuredly", "surely", "undoubtedly", "unhesitatingly", "with pleasure", "it is so", "as you wish", "consider it done", "no problem", "no worries", "not a problem", "not an issue", "go for it", "make it so", "by all means go ahead", "feel free to proceed", "authorize", "authorized"],
        requires_exact=False,
        answer = "Understood, action approved.",
        description="Approve pending action or request"
    ),
    Command(
        action="deny",
        keywords=["no", "deny", "cancer", "can", "kansas", "canceled", "denied", "negative", "cancel", "abort", "reject", "stop", "hold", "disallow", "wait", "halt", "terminate", "cease", "not", "never", "refuse", "decline", "withdraw", "abort mission", "cut it out", "knock it off", "put a stop to it", "call it off", "shut it down", "shut it off", "pull the plug", "bring to an end", "close it down", "wind it up", "close up shop", "scrap it", "scrap that", "nix it", "nix that", "shoot it down", "shoot that down", "veto it", "veto that", "over my dead body", "not a chance", "no way", "out of the question", "by no means", "under no circumstances", "not on your life", "not in a million years", "not for all the tea in china", "not on your nelly", "not in this lifetime", "not in your wildest dreams", "when pigs fly", "over my cold dead body", "not on your tintype", "not on your life", "not in a month of sundays", "not in a blue moon", "not in a cobblers", "not in a dog's age", "not in a cat's age", "not in a jiffy", "not in a shake of a lamb's tail", "not in a twinkling", "not in a heartbeat", "not in a flash", "not in a split second", "not in a blink of an eye", "not in two shakes of a lamb's tail", "not in the twinkling of an eye", "not in the blink of an eye", "not in the snap of a finger", "not in the wink of an eye"],
        requires_exact=False,
        answer = "Understood, action denied.",
        description="Deny pending action or request"
    ),
    
    # Task acknowledgment
    Command(
        action="acknowledge",
        keywords=["check", "confirm", "Takeoff clearance confirm", "checked", "trick", "shrek", "chicken", "start", "done", "chick", "jake", "complete", "completed", "acknowledge", "acknowledged", "crosscheck", "crosschecked", "verify", "verified", "affirm", "affirmed", "confirmed", "validate", "validated", "certify", "certified", "attest", "attested", "ratify", "ratified", "endorse", "endorsed", "assent", "assented", "recognize", "recognized", "admit", "admitted", "grant", "granted", "subscribe", "subscribed"],
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
