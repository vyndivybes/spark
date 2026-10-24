"""Structured, redacted tool-execution trace for SPARK tool dispatch.

The live voice/typed conversation executes tools through
AudioLoop.answer_mcp_tool() and confirms delivery with
session.send_tool_response(); this module turns that chain into correlated,
redacted evidence the acceptance tests can read back.

Append-only JSONL at %LOCALAPPDATA%\\SPARK\\workspace\\tool-trace.jsonl with
one record per event:

  ts        local ISO timestamp (milliseconds)
  event     tool_call_received | dispatch_denied | tool_executed |
            responses_delivered | typed_input | typed_turn_sent ...
  route     gemini_live | groq_engine | workbench
  tool      provider function name (bounded, name only)
  call_id   provider function-call id (bounded)
  session   truncated session correlation id (never credentials)
  outcome   ok | not_allowed | error | sent | session_missing ...
  detail    short counters only (answer_len, call count, text character
            counts). NEVER API keys, raw audio, conversation text, argument
            contents or source code.

Rotation is bounded: the file is compacted to its last TRACE_KEEP lines when
it grows beyond TRACE_MAX_BYTES.
"""
import datetime
import json
import os
import threading
from pathlib import Path

TRACE_MAX_BYTES = 512_000
TRACE_KEEP = 2000
TRACE_COMPACTION_BYTES = 250_000
_lock = threading.Lock()

import re
_SECRET_PATTERN = re.compile(
    r"AIzaSy\w+|gsk_\w+|sk-[A-Za-z0-9]{8,}|Bearer\s+\S+|"
    r"api[_-]?key\s*[=:]\s*\S+|token\s*[=:]\s*\S+|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE)


def _scrub(text):
    """Detail fields must never carry key-shaped material, even by mistake."""
    return _SECRET_PATTERN.sub("[redacted]", text)


def _trace_path():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    return Path(base) / "SPARK" / "workspace" / "tool-trace.jsonl"


def _compact(path):
    """Keep only the most recent records within a byte budget, then line cap."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        lines = [line for line in raw.splitlines() if line.strip()]
        kept = []
        budget = TRACE_COMPACTION_BYTES
        for line in reversed(lines):
            budget -= len(line.encode("utf-8", "replace"))
            if budget < 0 and kept:
                break
            kept.append(line)
            if len(kept) >= TRACE_KEEP:
                break
        kept.reverse()
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _clean(value, limit):
    text = str(value or "")
    return text[:limit] if len(text) <= limit else text[:limit]


def record(event, *, route="gemini_live", tool="", call_id="", session="",
           outcome="", detail=""):
    """Append one redacted trace record; never raises, never stores content."""
    path = _trace_path()
    if path is None:
        return
    entry = {
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "event": _clean(event, 40),
        "route": _clean(route, 20),
        "tool": _clean(tool, 60),
        "call_id": _clean(call_id, 40),
        "session": _clean(session, 40),
        "outcome": _clean(outcome, 40),
        "detail": _scrub(_clean(detail, 160)),
    }
    line = json.dumps(entry, ensure_ascii=True)
    with _lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            oversized = path.exists() and path.stat().st_size > TRACE_MAX_BYTES
            with path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
            if oversized:
                _compact(path)
        except OSError:
            pass

def read_tail(limit=200):
    """Redacted tail for acceptance checks; returns parsed dicts, never raises."""
    path = _trace_path()
    if path is None or not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    records = []
    for line in raw.splitlines()[-limit:]:
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records
