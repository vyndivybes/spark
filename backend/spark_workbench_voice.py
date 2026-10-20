"""Exact local voice intents for explicit preference and reminder management."""
from datetime import datetime, timedelta, timezone
import re


def parse_workbench_command(value, now=None):
    if not isinstance(value, str) or len(value) > 500:
        return None
    value = re.sub(r"\s+", " ", value.strip()).rstrip(".?!")
    value = re.sub(r"^spark,?\s+", "", value, flags=re.I)

    utterance = re.sub(r"^(?:jarvis|ada),?\s+", "", value, flags=re.I)
    # A named SPARK source artifact is always an architecture question, even
    # inside temporal phrasing: "what did we decide about ada.py" belongs to
    # Graphify, which can read the file, not to a memory graph that cannot.
    graph_target = re.search(
        r"\b(?:graphify|groqvoiceloop|groq voice loop|grokwise|jarvisclient|jarvis client|jarvis bridge|"
        r"spark_groq|spark_jarvis|spark_workbench|spark_rea|ada\.py|server\.py|main\.js)\b",
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

    # Graphiti answers questions about the user's own recorded history, so it is
    # matched before the Graphify context heuristic: "what changed in the
    # printer project" would otherwise be swept up by the word "project".
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
