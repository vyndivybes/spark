"""Spoken-answer formatting for SPARK's MCP-backed voice tools.

These are pure functions: they take an MCP result or a parsed tool payload and
return the sentence a voice loop will speak. Authorization, transport and
service registration all stay in server.py, so nothing here can widen what a
session is allowed to ask.

Every formatter states where an answer came from and how stale or partial it is.
A voice answer is the one place a user cannot re-read a caveat, so "Graphiti
recorded" and "those are its own notes" are load-bearing, not decoration.
"""
import json
import re

# Voice-visible alias for each Hermes view. The tool names themselves never
# leave the backend.
HERMES_KIND_TOOLS = {"skills": "hermes_learned_skills",
                     "memories": "hermes_memory_cards",
                     "status": "hermes_learning_status"}

MAX_SPOKEN = 1100
_NODE = re.compile(r"^NODE (.+?) \[src=(.*?) loc=")


def mcp_text(response):
    """Flatten an MCP result to its text blocks."""
    return "\n".join(
        item.get("text", "")
        for item in (response.get("content") or [])
        if isinstance(item, dict) and item.get("type") == "text"
    ).strip()


def mcp_json(response):
    """Parse the JSON body an MCP tool returned, or None when it is not JSON."""
    text = mcp_text(response)
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def payload_or_message(response, failure):
    """A tool payload, or the sentence to speak when there is not one.

    The sidecars report their own faults inside a normal result, so an
    'unavailable' answer arrives as {'error': ...} rather than as isError.
    """
    payload = mcp_json(response)
    if not isinstance(payload, dict):
        return failure
    if payload.get("error"):
        return str(payload["error"])[:200]
    return payload


def spoken_graphify(response, empty="Graphify found no matching source nodes."):
    """Name the related nodes and their files, and say what that does not prove."""
    nodes = []
    for line in mcp_text(response).splitlines():
        match = _NODE.match(line)
        if match and match.group(2):
            entry = match.group(1)[:80] + " (" + match.group(2)[:120] + ")"
            if entry not in nodes:
                nodes.append(entry)
    if not nodes:
        return empty
    return (
        "Graphify verified these related nodes and source files: "
        + "; ".join(nodes[:9])
        + ". These are graph associations, not independently "
          "verified dependency directions or change impacts."
    )[:MAX_SPOKEN]


def spoken_facts(payload, empty):
    """Turn temporal facts into at most three spoken sentences.

    A fact carrying invalid_at is announced as superseded rather than dropped:
    omitting it would make the newer record look like the only one that ever
    existed, which is exactly the distinction a bi-temporal graph preserves.
    """
    parts = []
    for fact in [f for f in (payload.get("facts") or []) if isinstance(f, dict)][:3]:
        text = str(fact.get("fact") or "").strip()
        if not text:
            continue
        when = fact.get("valid_at")
        if isinstance(when, str) and len(when) >= 10:
            text += " (from " + when[:10] + ")"
        if fact.get("invalid_at"):
            text += ", since superseded"
        parts.append(text)
    if not parts:
        return empty
    total = payload.get("fact_count")
    suffix = ""
    if isinstance(total, int) and not isinstance(total, bool) and total > len(parts):
        suffix = " " + str(total - len(parts)) + " more are recorded."
    return ("Graphiti recorded: " + "; ".join(parts) + "." + suffix)[:MAX_SPOKEN - 200]


def spoken_timeline(payload, entity):
    """An entity's recorded history, naming what matched and what was superseded."""
    answer = spoken_facts(payload, "Graphiti has no recorded history for " + str(entity)[:60] + ".")
    names = [str(item.get("name")) for item in (payload.get("entities") or [])
             if isinstance(item, dict) and item.get("name")]
    if names:
        answer = "Matched " + ", ".join(names[:3]) + ". " + answer
    superseded = payload.get("invalidated_count")
    if isinstance(superseded, int) and not isinstance(superseded, bool) and superseded:
        answer += " " + str(superseded) + " of those were superseded by a later record."
    return answer[:MAX_SPOKEN]


def spoken_hermes(payload, kind):
    """Report another agent's notes as notes.

    Hermes writes its own skills and memory files, so its output is untrusted
    upstream content. Naming it as Hermes's claim keeps a spoken summary from
    becoming SPARK asserting something it never verified.
    """
    if kind == "status":
        if payload.get("available") is not True:
            return "Hermes Agent is registered but not installed here."
        return ("Hermes Agent has learned " + str(payload.get("learned_skill_count", 0))
                + " skills and holds " + str(payload.get("memory_count", 0))
                + " memory cards.")[:300]
    if kind == "skills":
        skills = [str(item.get("name")) for item in (payload.get("skills") or [])
                  if isinstance(item, dict) and item.get("name")]
        if not skills:
            return "Hermes Agent has not learned any skills yet."
        return ("Hermes Agent learned these skills: " + ", ".join(skills[:6])
                + ". Those are its own notes, not SPARK capabilities.")[:600]
    cards = [str(item.get("title")) for item in (payload.get("cards") or [])
             if isinstance(item, dict) and item.get("title")]
    if not cards:
        return "Hermes Agent has no memory cards yet."
    return ("Hermes Agent remembers: " + ", ".join(cards[:6])
            + ". Those are its own notes, not verified facts.")[:600]
