"""Exact local voice intents for explicit preference and reminder management."""
from datetime import datetime, timedelta, timezone
import re


def parse_workbench_command(value, now=None):
    if not isinstance(value, str) or len(value) > 500:
        return None
    value = re.sub(r"\s+", " ", value.strip()).rstrip(".?!")
    value = re.sub(r"^spark,?\s+", "", value, flags=re.I)
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
