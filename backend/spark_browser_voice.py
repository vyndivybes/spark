"""Deterministic read-only browser voice controls for the active owner session.

No model-chosen URLs, clicks, form submissions, or automatic browsing plans.
Untrusted page text never becomes an instruction.
"""
import ipaddress
import re
from urllib.parse import urlsplit

def _public_destination(value):
    if not isinstance(value,str) or not 1<=len(value)<=240 or any(x.isspace() for x in value):
        return None
    if "://" not in value:
        value="https://"+value
    try:
        parsed=urlsplit(value)
        host=parsed.hostname
        if parsed.scheme!="https" or not host or parsed.username or parsed.password:
            return None
        if parsed.port not in (None,443):
            return None
        if host.lower() in {"localhost","localhost.localdomain"} or host.lower().endswith((".localhost",".local")):
            return None
        try:
            ip=ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or not re.fullmatch(r"[a-zA-Z0-9.-]+",host):
                return None
        else:
            if not ip.is_global:return None
        if any(c in value for c in ["\\","@","#"]):
            return None
        return value
    except ValueError:
        return None

def parse_browser_voice(utterance):
    if not isinstance(utterance,str) or len(utterance)>300:return None
    text=re.sub(r"^(?:hey\s+)?(?:spark|jarvis)\s*[,,:]?\s*","",utterance.strip().rstrip(".!?"),flags=re.I)
    if not text.lower().startswith("browser "):return None
    rest=text[8:].strip()
    if rest.lower() in {"inspect this page","inspect page"}:
        return {"action":"inspect"}
    if rest.lower() in {"go back","back","previous page"}:
        return {"action":"back"}
    if rest.lower() in {"go forward","forward","next page"}:
        return {"action":"forward"}
    if rest.lower() in {"reload","refresh page"}:
        return {"action":"reload"}
    match=re.fullmatch(r"(?i)(?:open|navigate to|go to)\s+(.+)",rest)
    if match:
        target=_public_destination(match[1].strip())
        return {"action":"navigate","text":target} if target else None
    return None

async def perform_browser_voice(sessions,sid,parsed):
    if not isinstance(parsed,dict) or parsed.get("action") not in ("navigate","back","forward","reload","inspect"):
        return {"ok":False,"message":"Unsupported browser voice action."}
    session=sessions.sessions.get(sid)
    if (not session or not sessions.allowed(sid)
            or not sessions._authorized(session) or session["task"].done()):
        return {"ok":False,"message":"Open and unlock WEB_AGENT_VIEW before using browser voice commands."}
    payload={**parsed,"session_id":session["id"],
             "workspace_token":session["workspace_token"]}
    await sessions.command(sid,payload)
    return {"ok":True,"message":("Page inspection requested. Read the result in WEB_AGENT_VIEW."
                                  if parsed["action"]=="inspect" else
                                  "Browser action queued. Confirm completion in WEB_AGENT_VIEW.")}
