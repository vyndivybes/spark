"""Strict speech intents and per-session Groq camera authorization.

Only exact, self-contained utterances may become local desktop actions.
No model output can select executables, parameters or file paths.
"""
import re


def parse_desktop_command(value):
    if not isinstance(value, str) or len(value) > 160:
        return None
    speech = re.sub(r"\s+", " ", value.strip().lower()).rstrip(".?!")
    match = re.fullmatch(
        r"(?:spark,? )?(?:please )?(?:can you )?(?:open|launch|start) "
        r"(calculator|notepad|paint)",
        speech,
    )
    return match.group(1) if match else None


def vision_requested(value):
    if not isinstance(value, str) or len(value) > 160:
        return False
    speech = re.sub(r"\s+", " ", value.strip().lower()).rstrip(".?!")
    return bool(re.fullmatch(
        r"(?:spark,? )?(?:please )?"
        r"(?:what (?:do|can) you see|describe what you see|"
        r"what(?:'s| is) in front of (?:the )?camera|"
        r"what(?:'s| is) in (?:the )?(?:camera|image|picture|frame))",
        speech,
    ))


def can_groq_vision_frame(*, provider, owner_sid, sender_sid, sharing_sid,
                          session_ready, authenticated):
    return bool(
        provider == "groq"
        and owner_sid
        and sender_sid == owner_sid
        and sharing_sid == owner_sid
        and session_ready
        and authenticated
    )
