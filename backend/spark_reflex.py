"""Small, deterministic SPARK reflex actions.

Only recognized local intents are translated into tightly scoped PC actions.
No user-controlled executable, arguments, shell commands, or URLs are accepted.
The existing PcAccess permission and audit gates remain authoritative.
"""
import re

_LAUNCH = {
    "open calculator": "calc.exe",
    "launch calculator": "calc.exe",
    "open notepad": "notepad.exe",
    "launch notepad": "notepad.exe",
}
_HELP = frozenset({"reflex help", "what reflex commands can you do"})


def reflex_plan(utterance):
    """Return a bounded intent or fail closed; never execute anything."""
    if not isinstance(utterance, str) or not 1 <= len(utterance) <= 120:
        raise ValueError("Provide a short reflex command.")
    if not utterance.isascii() or any(ord(c) < 32 for c in utterance):
        raise ValueError("Unsupported reflex command.")
    phrase = re.sub(r" +", " ", utterance.strip().casefold())
    if phrase in _HELP:
        return {"kind": "help", "requires_pc_autonomy": False}
    if phrase in _LAUNCH:
        return {"kind": "launch", "program": _LAUNCH[phrase], "requires_pc_autonomy": True}
    raise ValueError("Unknown reflex command. Say 'reflex help' to list supported commands.")


def reflex_execute(utterance, pc_access=None):
    """Execute only via an already-authorized, audited PcAccess instance."""
    plan = reflex_plan(utterance)
    if plan["kind"] == "help":
        return {"ok": True, "kind": "help", "commands": sorted(set(_LAUNCH) | _HELP),
                "execution": "none"}
    if pc_access is None or not callable(getattr(pc_access, "enabled", None)) or not pc_access.enabled():
        return {"ok": False, "kind": "launch", "error": "PC autonomy is disabled or no live session is authorized."}
    result = pc_access.execute({"action": "launch", "path": plan["program"], "arguments": []})
    if not isinstance(result, dict):
        return {"ok": False, "kind": "launch", "error": "PC action returned an invalid result."}
    return {"ok": result.get("ok") is True, "kind": "launch",
            "program": plan["program"], "result": result,
            "execution": "launch_attempted"}
