"""SPARK Live configuration and safe user-facing status (stdlib only).

Never log API keys or raw provider exception bodies. Free-tier supported
Live model defaults to gemini-3.8-live, independent of ARKUS Flash settings.
"""
import os

_SUPPORTED = frozenset(("gemini-3.8-live", "gemini-3.1-flash-live-preview"))


def live_model():
    candidate = os.environ.get("SPARK_LIVE_MODEL", "gemini-3.8-live").strip()
    return candidate if candidate in _SUPPORTED else "gemini-3.8-live"


def live_status(configured, model=None):
    chosen = model or live_model()
    if not configured:
        return {
            "state": "setup_required",
            "model": chosen,
            "message": "SPARK Gemini key missing. Configure backend/.env or start with -UseArkusGeminiKey.",
        }
    return {"state": "idle", "model": chosen, "message": "SPARK ready to open a Gemini Live voice session."}


def live_error_message(error):
    """Classify errors without showing provider stack traces, key or query."""
    value = str(error).lower()
    if "429" in value or "quota" in value or "resource_exhausted" in value:
        return "Gemini Live rate limit or quota reached (429). Check AI Studio usage; do not retry repeatedly."
    if "401" in value or "403" in value or "permission" in value or "unauthorized" in value:
        return "Gemini Live permission or API key error (401/403). Check the configured Google project."
    if "404" in value or "not_found" in value:
        return "Gemini Live model or endpoint unavailable (404). Check model availability in AI Studio."
    return "Gemini Live connection or audio session failed. Check the SPARK terminal and audio devices."


def live_status_report(state, message=""):
    """Safe /status snapshot: categorical error, never arbitrary provider text."""
    if state == "connected":
        return {"live_state": "connected",
                "live_message": "SPARK Core connected to Gemini Live.",
                "live_error_code": None}
    if state == "error":
        # The backend supplies classified messages, not raw exception bodies.
        # Only recognize known, constant prefixes; never include untrusted text.
        if isinstance(message, str) and message.startswith("Gemini Live rate limit or quota reached (429)."):
            return {"live_state": "error",
                    "live_message": "Gemini Live rate limit or quota reached (429). Check AI Studio usage.",
                    "live_error_code": 429}
        if isinstance(message, str) and message.startswith("Gemini Live permission or API key error (401/403)."):
            return {"live_state": "error",
                    "live_message": "Gemini Live authentication/permission rejected (401/403).",
                    "live_error_code": 401}
        if isinstance(message, str) and message.startswith("Gemini Live model or endpoint unavailable (404)."):
            return {"live_state": "error",
                    "live_message": "Gemini Live model or endpoint unavailable (404).",
                    "live_error_code": 404}
        return {"live_state": "error",
                "live_message": "Gemini Live session failed; inspect the SPARK launch terminal.",
                "live_error_code": None}
    states = {"idle": "SPARK Core idle.", "connecting": "Connecting to Gemini Live...",
              "disconnected": "Gemini Live disconnected.",
              "setup_required": "Configure the SPARK Gemini key.",
              "audio_error": "Audio device failed; inspect microphone selection."}
    safe_state = state if state in states else "error"
    return {"live_state": safe_state,
            "live_message": states.get(safe_state, "Gemini Live session status unknown."),
            "live_error_code": None}
