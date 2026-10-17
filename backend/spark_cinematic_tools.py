"""Minimal Gemini Live function-call policy for SPARK's opt-in cinematic tools.

The default 'cinematic' profile remains tool-free. Only explicit
'cinematic_tools' sessions advertise these exact synchronous declarations.
Authorization is enforced again on execution, regardless of Gemini output.
"""
import datetime
import platform

CINEMATIC_FUNCTIONS = [
    {
        "name": "get_system_status",
        "description": "Report SPARK's local operating system and time. Read-only.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "launch_desktop_app",
        "description": (
            "Ask the user to approve opening one allowlisted Windows "
            "application. Only Calculator, Notepad or Paint. Never open "
            "arbitrary files, URLs or commands."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app": {
                    "type": "STRING",
                    "enum": ["calculator", "notepad", "paint"],
                    "description": "Approved app to open after user confirms in SPARK."
                }
            },
            "required": ["app"]
        }
    }
]
_ALLOWED = frozenset(x["name"] for x in CINEMATIC_FUNCTIONS)


def allowed_live_tool(profile, name):
    if profile == "cinematic_tools":
        return name in _ALLOWED
    if profile == "full":
        return True  # Legacy full profile's own permission gates remain.
    return False


def tool_confirmation_required(name, permissions):
    # Desktop activity is ALWAYS approved interactively, regardless of
    # the user's saved legacy tool permission toggles.
    if name == "launch_desktop_app":
        return True
    return bool(permissions.get(name, True))


def get_system_status(platform_name=None, clock=None):
    if platform_name is None:
        platform_name = platform.system()
    if clock is None:
        clock = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return {
        "service": "SPARK Core",
        "operating_system": platform_name,
        "local_time": clock,
    }
