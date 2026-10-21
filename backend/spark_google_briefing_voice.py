"""Faithful, concise spoken summaries of the last locally verified Google reads."""
from datetime import datetime
from zoneinfo import ZoneInfo


def spoken_briefing(brief):
    if not isinstance(brief, dict):
        return "The executive briefing is unavailable. No Google results were verified."
    sources = brief.get("sources") or {}
    ready = {key for key, value in sources.items()
             if value.get("last_success") and not value.get("stale") and
             value.get("state") == "current"}
    if not ready:
        return ("I cannot verify your Gmail, Calendar or Drive information yet. "
                "Open SPARK Home, check each Google source status and select Refresh source data.")
    parts = ["Executive briefing, India time. This uses the latest verified local Google snapshots."]
    if "gmail" in ready:
        emails = brief.get("emails") or []
        urgent = [e for e in emails if e.get("priority") in ("urgent", "action")]
        if urgent:
            parts.append(f"{len(urgent)} messages may require attention.")
            for item in urgent[:4]:
                parts.append(f"{str(item.get('subject') or 'Untitled email')[:120]}. "
                             f"{str(item.get('reason') or 'Check the email')[:100]}.")
        else:
            parts.append("No action-related messages found in the retrieved email sample.")
        parts.append("Email reply status is not verified, and this is not necessarily the whole inbox.")
    else:
        parts.append("Gmail is not verified or is stale. I cannot report today's email activity.")
    if "google-calendar" in ready:
        events = brief.get("events") or []
        if events:
            parts.append(f"{len(events)} calendar events in today's and tomorrow's retrieved schedule.")
            for item in events[:3]:
                parts.append(str(item.get("title") or "Untitled meeting")[:90] +
                             (" may overlap another event." if item.get("overlap") else "."))
        else:
            parts.append("No events found in the checked Calendar window.")
    else:
        parts.append("Calendar is not verified or is stale.")
    if "google-drive" in ready:
        reviews = [item for item in brief.get("documents") or [] if item.get("review_candidate")]
        if reviews:
            parts.append(f"{len(reviews)} Drive files look like possible review documents.")
            for item in reviews[:3]:
                parts.append(str(item.get("name") or "Untitled document")[:100] + ".")
            parts.append("Review status is inferred, not confirmed.")
        else:
            parts.append("No potential Drive review files in the retrieved sample.")
    else:
        parts.append("Drive is not verified or is stale.")
    return " ".join(parts)[:2000]
