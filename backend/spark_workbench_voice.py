"""Exact local voice intents for explicit preference and reminder management."""
from datetime import datetime, timedelta, timezone
import re


def parse_workbench_command(value, now=None):
    if not isinstance(value, str) or len(value) > 500:
        return None
    value = re.sub(r"\s+", " ", value.strip()).rstrip(".?!")
    value = re.sub(r"^spark,?\s+", "", value, flags=re.I)

    utterance = re.sub(r"^(?:jarvis|spark),?\s+", "", value, flags=re.I)
    # Explicit natural-language read-only executive briefing intents.
    # No model may invent an email or calendar item without this source read.
    if re.fullmatch(
        r"(?:what (?:important (?:emails?|mails?) (?:did i receive|came in) today|"
        r"(?:emails?|mails?) (?:need|require) my attention|"
        r"(?:is )?my schedule tomorrow|needs my attention)|"
        r"(?:show|give|read) (?:me )?(?:my |the )?(?:daily |today'?s? )?"
        r"(?:executive |google )?briefing|"
        r"(?:brief me|daily executive briefing|"
        r"summarize (?:my )?(?:gmail|calendar|google drive|gmail calendar and drive)))",
        utterance, re.I):
        return {"action": "executive_briefing", "payload": {}}

    # Governed capability voices (OpenJarvis 01-16): read-only status,
    # history and bounded local research only. Mutating capability actions
    # (approve/send/execute/activate/revoke/configure/opt-in) are never
    # mapped here, so the owner must perform them from the Capabilities
    # Center where a checked payload and an ostensible owner gate apply.
    capability = CAPABILITY_VOICE_INTENTS(utterance)
    if capability:
        return capability

    # A named SPARK source artifact is always an architecture question, even
    # inside temporal phrasing: "what did we decide about spark.py" belongs to
    # Graphify, which can read the file, not to a memory graph that cannot.
    graph_target = re.search(
        r"\b(?:graphify|groqvoiceloop|groq voice loop|grokwise|jarvisclient|jarvis client|jarvis bridge|"
        r"spark_groq|spark_jarvis|spark_workbench|spark_rea|spark\.py|server\.py|main\.js)\b",
        utterance, re.I
    )

    # Hermes Agent's learned experience. Three exact phrasings rather than one
    # loose pattern: this reads another agent's notes aloud, so an ambiguous
    # utterance should not reach it.
    if re.fullmatch(r"(?:show|list|read|check) (?:me )?(?:the )?hermes(?: agent)? skills", value, re.I):
        return {"action": "hermes_experience", "payload": {"kind": "skills"}}
    if re.fullmatch(r"(?:show|list|read|check) (?:me )?(?:the )?hermes(?: agent)? memor(?:y|ies)", value, re.I):
        return {"action": "hermes_experience", "payload": {"kind": "memories"}}
    if re.fullmatch(r"(?:is|check|show) (?:the )?hermes(?: agent)? (?:available|installed|ready|status)", value, re.I):
        return {"action": "hermes_experience", "payload": {"kind": "status"}}

    # Obsidian: explicit note lookups against the user's local vault.
    obsidian_search = re.fullmatch(
        r"(?:search|find|look up) (?:my )?obsidian (?:notes?|vault) for (.{2,120})", value, re.I)
    if obsidian_search:
        return {"action": "obsidian_search", "payload": {"query": obsidian_search[1].strip()}}
    obsidian_open = re.fullmatch(
        r"(?:open|read) (?:my )?obsidian note (?:called |named |titled )?(.{2,200})", value, re.I)
    if obsidian_open:
        return {"action": "obsidian_read", "payload": {"path": obsidian_open[1].strip()}}

    # Graphiti answers questions about the user's own recorded history, so it is
    # matched before the Graphify context heuristic: "what changed in the
    # printer project" would otherwise be swept up by the word "project".
    graph_question = utterance
    graph_context = (
        re.search(
            r"\b(?:architecture|architectural|dependencies?|depends|dependency|impact|affected|"
            r"modules?|components?|codebase|connect|connects|connected|wired|wiring|"
            r"interact|interacts|relationship|flow|calls?)\b",
            graph_question, re.I
        )
        and re.search(
            r"\b(?:spark|jarvis|voice|groq|grokwise|camera|desktop|bridge|backend|frontend|"
            r"electron|loop|client|workbench|api|rest)\b",
            graph_question, re.I
        )
    )
    if not graph_target:
        entity = re.fullmatch(
            r"(?:show|list|read|give) (?:me )?(?:the )?(?:history|timeline) (?:of|for) "
            r"(?:the |my |our |an |a )?(.{3,120})",
            utterance, re.I
        )
        if entity:
            return {"action": "graphiti_entity_history", "payload": {"entity": entity[1].strip()}}
        # The whole utterance is passed on, not just the tail: Graphiti retrieves
        # by embedding, and a fragment like "to PETG" loses the words that place
        # it in time.
        if (3 <= len(utterance) <= 220 and re.match(
            r"(?:what do (?:we|i|you) (?:know|remember) about|what (?:has|have) changed (?:with|in|about)|"
            r"what changed (?:with|in|about)|what did (?:we|i) decide (?:about|on|for)|"
            r"when did (?:we|i) (?:change|decide|switch)|what is the (?:history|timeline) of)\b",
            utterance, re.I
        )):
            return {"action": "graphiti_voice_query", "payload": {"question": utterance}}

    # Graphiti: temporal knowledge graph about the user's recorded history.
    graphiti_entity = re.search(
        r"(?:what(?:'s| is) the history (?:of|for)|history of|timeline for|everything about)\s+(.{1,80})",
        utterance, re.I
    )
    graphiti_q = re.search(
        r"\b(?:when did|what did we|when was|what changed|timeline|history|"
        r"decision|decided|superseded|last time|previously)\b",
        utterance, re.I
    ) and not re.search(
        r"\b(?:function|class|module|file|code|implement|import|dependency|dependencies|"
        r"architecture|connect|calls|source|src=|backend|frontend|electron|jarvis bridge|groq voice loop)\b",
        utterance, re.I
    )
    if not graph_target and len(utterance) <= 220 and graphiti_entity:
        return {"action": "graphiti_entity_history", "payload": {"entity": graphiti_entity.group(1).strip()}}
    if not graph_target and len(utterance) <= 220 and graphiti_q and not graph_context:
        return {"action": "graphiti_voice_query", "payload": {"question": utterance}}

    # Local architecture questions are answered from Graphify.
    if len(graph_question) <= 220 and (graph_target or graph_context):
        return {
            "action": "graphify_voice_query",
            "payload": {"question": graph_question}
        }
    if re.fullmatch(r'(?:show|check|list) (?:my )?agent(?:s| status)?',value,re.I):
        return {'action':'agent_snapshot','payload':{}}
    if re.fullmatch(r'(?:show|check) (?:my )?(?:system health|system status)',value,re.I):
        return {'action':'intelligence_health','payload':{}}
    if re.fullmatch(r"(?:what are|show|list) my (?:saved )?preferences", value, re.I):
        return {"action": "workbench_snapshot", "payload": {}}
    saved = re.fullmatch(r"remember my (.{1,80}?) as (.{1,250})", value, re.I)
    if saved:
        return {"action": "save_preference", "payload": {"key": saved[1], "value": saved[2]}}
    reminder = re.fullmatch(r"remind me in ([0-9]{1,5}) (minutes?|hours?) to (.{1,200})", value, re.I)
    if reminder:
        minutes = int(reminder[1])*(60 if reminder[2].lower().startswith("hour") else 1)
        if not 1 <= minutes <= 10080:
            return None
        instant = now or datetime.now(timezone.utc)
        return {"action": "add_agenda", "payload": {"title": reminder[3], "kind": "reminder",
                "due": (instant+timedelta(minutes=minutes)).isoformat()}}
    return None


# Governed read-only voice surface for OpenJarvis capabilities 01-16. Each
# entry maps an exact utterance to one `spark_workbench.py` ACTION_KEYS
# action whose effect is a local read, a status or a bounded local research
# pass. Mutating capability actions are deliberately absent from this table
# (voice cannot configure channels, approve sends, execute proposals,
# activate policies, revoke skills or opt engines in without the owner).
_CAPABILITY_TABLE = [
    (r"(?:play|read|speak|report) (?:me )?(?:the |my )?(?:latest |today's )?morning digest(?: now)?",
     "digest_speech", {"digest": ""}),
    (r"(?:show|give) (?:me )?(?:the )?morning digest status",
     "digest_status", {}),
    (r"(?:run|prepare|compose) (?:the )?morning digest(?: now)?",
     "digest_run", {}),
    (r"(?:show|give) (?:me )?(?:the )?(?:latest |last |recent )?digest history",
     "digest_history", {"limit": 5}),
    (r"(?:show|check) (?:the )?(?:messaging|channel) hub status",
     "hub_status", {}),
    (r"(?:show|check) (?:the )?proactive (?:agent )?(?:daily )?summary",
     "proactive_summary", {}),
    (r"(?:show|check|list) (?:the )?proactive inbox",
     "proactive_inbox", {"state": "", "limit": 20}),
    (r"(?:show|check) (?:the )?opencode status",
     "opencode_status", {}),
    (r"research (.{2,200})",
     "research_run", None),
    (r"(?:run|start) deep research (?:on|about|into) (.{2,200})",
     "research_run", None),
    (r"(?:show|check) (?:the )?trace(?: learning)? status",
     "trace_status", {}),
    (r"(?:show|check) (?:the )?learning status",
     "learning_status", {}),
    (r"(?:show|check) (?:the )?spec search status",
     "spec_search_status", {}),
    (r"(?:show|check) (?:the )?skill(?: ecosystem)? status",
     "skill_status", {}),
    (r"(?:show|give) (?:me )?(?:the )?skill list",
     "skill_list", {}),
    (r"(?:show|check) (?:the )?agent runtimes? status",
     "agents_status", {}),
    (r"(?:show|check) (?:the )?monitor status",
     "monitor_status", {}),
    (r"(?:show|check) (?:the )?connector status",
     "connector_status", {}),
    (r"(?:show|check) (?:the )?evaluation status",
     "eval_status", {}),
    (r"(?:show|give) (?:me )?(?:the )?evaluation history",
     "eval_history", {"limit": 5}),
    (r"(?:show|check) (?:the )?telemetry status",
     "telemetry_status", {}),
    (r"(?:show|read) (?:the )?telemetry report (?:for )?([A-Za-z0-9_.-]{1,40})",
     "telemetry_report", None),
    (r"(?:show|check) (?:the )?(?:inference )?backend status",
     "backend_describe", {}),
]


def CAPABILITY_VOICE_INTENTS(utterance):
    """Match governed capability phrases; returns None unless read-only."""
    for pattern, action, payload in _CAPABILITY_TABLE:
        match = re.fullmatch(pattern, utterance, re.I)
        if not match:
            continue
        if payload is None:  # parameterized, payload shape known per action
            if action == "research_run":
                return {"action": action,
                        "payload": {"question": match[1].strip(), "max_hops": ""}}
            if action == "telemetry_report":
                return {"action": action, "payload": {"model": match[1].strip()}}
            return None
        return {"action": action, "payload": dict(payload)}
    return None


def capability_voice_summary(action, result):
    """Turn honest capability results into short spoken text, or None."""
    if isinstance(result, str):
        return result[:600]
    if not isinstance(result, dict):
        if action == "eval_history" and isinstance(result, list):
            return f"{len(result)} evaluation runs on record."
        if action == "skill_list" and isinstance(result, list):
            return f"{len(result)} imported skills on record."
        return None
    if action == "digest_speech":
        return result.get('text') if isinstance(result, dict) else None
    if action == "digest_status":
        state = result.get("latest_run") or {}
        return (f"Morning digest: schedule "
                f"{state.get('schedule_ist') or result.get('schedule_ist') or 'not scheduled'}, "
                f"news {'enabled' if result.get('news_enabled') else 'off'}; "
                f"{_primitive_count(state, 'sources')} source states.")
    if action == "digest_run":
        return f"Morning digest {result.get('date')}: {result.get('status', 'unknown')}."
    if action == "digest_history":
        runs = result.get("runs") or []
        return f"{len(runs)} recent digest runs on record."
    if action == "hub_status":
        return (f"Messaging hub covers {len(result.get('providers') or [])} providers. "
                f"{result.get('policy')}")
    if action == "proactive_summary":
        return (f"Proactive today: {result.get('proposed', 0)} proposed, "
                f"{result.get('approved', 0)} approved, {result.get('executed', 0)} executed, "
                f"{result.get('denied', 0)} denied.")
    if action == "proactive_inbox":
        proposals = result.get("proposals") if isinstance(result.get("proposals"), list) else []
        extra = f" Latest: {proposals[-1].get('title')}" if proposals and isinstance(proposals[-1], dict) and proposals[-1].get("title") else ""
        return f"{len(proposals)} proactive proposals waiting in the inbox.{extra}"
    if action == "opencode_status":
        discovery = result.get("discovery") or {}
        if discovery.get("installed"):
            return "OpenCode is installed and ready for scoped sessions."
        return "OpenCode is not installed on this machine; install it manually first."
    if action == "research_run":
        answer = result.get("answer") or {}
        return (f"Research stopped after {result.get('hops', 0)} hops with "
                f"{len(result.get('citations') or [])} citations. "
                f"{answer.get('text', '')}")[:500]
    if action == "trace_status":
        return f"{len(result.get('summary') or [])} task classes summarized in the trace store."
    if action == "learning_status":
        return (f"Learning: active policy {result.get('active_policy', 'none')}; "
                f"{len(result.get('candidates') or [])} candidates on record.")
    if action == "spec_search_status":
        return (f"Spec search: {result.get('runs_recorded', 0)} runs recorded; "
                f"{result.get('planner', 'planner state unknown')}.")
    if action == "skill_status":
        return (f"Skill ecosystem ready; {len(result.get('operations') or [])} "
                f"operations registered. {result.get('integrity_model')}")
    if action == "skill_list":
        return None
    if action == "agents_status":
        return (f"Agent runtimes: {len(result.get('adapters') or [])} adapters, "
                f"step budget {result.get('max_steps', '?')}. {result.get('codeact_scope')}")
    if action == "monitor_status":
        return (f"Monitors: {len(result.get('monitors') or [])} registered. "
                f"{result.get('policy')}")
    if action == "connector_status":
        by_state = result.get("by_state") or {}
        return (f"Connectors: {'; '.join(f'{k} {v}' for k, v in by_state.items())}. "
                f"{len(result.get('adapters_attached') or [])} local adapters attached.")
    if action == "eval_status":
        return (f"{len(result.get('suites') or [])} evaluation suites uploaded. "
                f"{result.get('honesty')}")
    if action == "eval_history":
        return f"{len(result)} evaluation runs on record." if isinstance(result, list) else None
    if action == "telemetry_status":
        return (f"Telemetry: {result.get('entries', 0)} measurements. "
                f"Energy {result.get('energy', 'not measured')}.")
    if action == "telemetry_report":
        return _primitive_summary(result)
    if action == "backend_describe":
        engines = result.get("engines") or []
        states = "; ".join(f"{e.get('engine')} {e.get('state')}"
                           for e in engines if isinstance(e, dict))
        return f"Inference backends: {states}."
    return _primitive_summary(result)


# Actions the voice loop may execute at all: the legacy preference/reminder
# set plus the governed read-only capability table. Anything else (including
# every mutating capability action) is refused for voice and must be driven
# from the Capabilities Center through the owner-gated workspace handler.
CAPABILITY_VOICE_ACTIONS = frozenset(action for _, action, _ in _CAPABILITY_TABLE)
VOICE_WORKBENCH_ACTIONS = frozenset({
    "agent_snapshot", "intelligence_health", "workbench_snapshot",
    "save_preference", "add_agenda"}) | CAPABILITY_VOICE_ACTIONS

# Read-only capability actions that stay available to the token-authorized
# cockpit even when no paid voice provider session is running (the offline
# cockpit gate in server.py). Statuses, history/list/report reads plus the
# two deliberately voice-governable non-mutating composers (digest_run,
# research_run). Every mutating capability action is deliberately absent.
CAPABILITY_READ_ONLY_ACTIONS = frozenset({
    "digest_status", "digest_run", "digest_history",
    "hub_status", "hub_history",
    "proactive_summary", "proactive_inbox",
    "opencode_status",
    "research_run",
    "trace_status", "trace_labeled",
    "learning_status",
    "spec_search_status", "spec_candidates",
    "skill_status", "skill_list", "skill_runs",
    "agents_status", "agents_runs",
    "monitor_status",
    "connector_status", "connector_freshness", "connector_events",
    "eval_status", "eval_history",
    "telemetry_status", "telemetry_report",
    "backend_describe", "backend_events",
})


def _primitive_count(value, key):
    data = value.get(key) if isinstance(value, dict) else None
    return len(data) if isinstance(data, (dict, list)) else 0


def _primitive_summary(result, limit=400):
    if not isinstance(result, dict):
        return None
    parts = []
    for key, value in result.items():
        if isinstance(value, (int, float, bool, str)) and len(parts) < 6:
            parts.append(f"{key.replace('_', ' ')}: {value}")
    text = "; ".join(parts)
    return text[:limit] if text else None
