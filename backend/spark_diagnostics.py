"""Secret-free, bounded SPARK desktop health snapshot.

No API tokens, conversation content, user files, stack traces or network calls.
Read-only. This is not an API/agent provider manager or quota tracker.
"""
import re
from spark_host_vitals import normalize_host_vitals

SAFE_STATUSES={"idle","connected","connecting","disconnected","error","setup_required","audio_error"}
SAFE_PROVIDERS={"gemini","groq"}
SAFE_TRANSPORTS={"browser_aec","native"}
SAFE_CODES={"429","1008","401","403","404","500","503","none","unknown"}
ALLOWED_CHARACTERS=re.compile(r"^[a-zA-Z0-9._/\-]{1,72}$")


def _plain(value):
    return value if isinstance(value,str) and ALLOWED_CHARACTERS.fullmatch(value) else "unknown"


def safe_diagnostics(status,uptime_seconds=0):
    """Return only known harmless runtime facts for the SPARK cockpit."""
    if not isinstance(status,dict):
        status={}
    provider=status.get("ai_provider")
    transport=status.get("audio_transport")
    state=status.get("live_state")
    code=str(status.get("live_error_code") or "none")
    return {
        "service": "SPARK Core",
        "ai_provider":provider if provider in SAFE_PROVIDERS else "unknown",
        "live_state":state if isinstance(state,str) and state in SAFE_STATUSES else "unknown",
        "live_model":_plain(status.get("live_model")),
        "live_profile":_plain(status.get("live_profile")),
        "audio_transport":transport if transport in SAFE_TRANSPORTS else "unknown",
        "hands_free_ready":status.get("hands_free_ready") is True,
        "gemini_configured":status.get("gemini_configured") is True,
        "groq_configured":status.get("groq_configured") is True,
        "live_error_code":code if code in SAFE_CODES else "unknown",
        "uptime_seconds":min(8640000,max(0,int(uptime_seconds))) if isinstance(uptime_seconds,(int,float)) and not isinstance(uptime_seconds,bool) else 0,
        "host":normalize_host_vitals(status.get("host")),
    }
