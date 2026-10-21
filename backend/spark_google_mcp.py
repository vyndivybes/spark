"""Bounded, read-only Google Workspace intelligence using the host-selected gws CLI.

No client may choose an account, CLI command or OAuth scope. The account is
verified before reading content. Results are source-linked *candidates*, not
claims that a message is definitively unanswered or a document needs approval.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote
from zoneinfo import ZoneInfo

TIMEZONE = os.environ.get("SPARK_GOOGLE_TIMEZONE", "Asia/Kolkata")
MAIL_LIMIT = 20
FILE_LIMIT = 25
EVENT_LIMIT = 30

IMPORTANT = re.compile(
    r"\b(action required|approval|approve|respond|reply requested|deadline|due date|"
    r"overdue|payment failed|payment due|invoice|nda|contract|proposal|"
    r"meeting invitation|interview|security alert|verification required|"
    r"supplier|quotation|purchase order)\b", re.I)
URGENT = re.compile(
    r"\b(urgent|immediate|today|overdue|payment failed|security alert|"
    r"final reminder|expires? today)\b", re.I)
REVIEW = re.compile(r"\b(review|approval|draft|nda|contract|proposal|sign(?:ature)?|minutes)\b", re.I)


def local_window(now=None):
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(TIMEZONE))
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return day, day + timedelta(days=1), day + timedelta(days=2)


def headers(message):
    values = message.get("payload", {}).get("headers") or []
    return {str(h.get("name", "")).lower(): str(h.get("value", "")) for h in values
            if isinstance(h, dict)}


def mail_importance(subject, snippet, unread):
    text = (subject + " " + snippet)[:2000]
    if URGENT.search(text):
        return "urgent", "Urgency phrase in subject or preview; verify the message"
    if IMPORTANT.search(text):
        return "action", "Possible request, commitment or deadline; verify the message"
    if unread:
        return "review", "Unread; may warrant review"
    return "fyi", "No specific action detected in preview"


class GoogleReader:
    def __init__(self, cli, account):
        self.cli = Path(cli)
        if not self.cli.is_absolute() or not self.cli.is_file():
            raise ValueError("Configure the installed native Google Workspace CLI.")
        if not isinstance(account, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", account):
            raise ValueError("Configure the expected Google account on the host.")
        self.account = account.lower()

    def _run(self, command, params):
        result = subprocess.run(
            [str(self.cli), *command, "--params", json.dumps(params)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", timeout=30, shell=False)
        if result.returncode or len(result.stdout.encode("utf-8")) > 500_000:
            raise ValueError("Google API read failed. Verify the local OAuth login and access scopes.")
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or "error" in value:
            raise ValueError("Google returned an error or unsupported response.")
        return value

    def _mail(self):
        day, tomorrow, _ = local_window()
        query = (f"after:{int(day.timestamp()) - 1} before:{int(tomorrow.timestamp())} "
                 "-in:sent -in:spam -in:trash")
        listed = self._run(["gmail", "users", "messages", "list"],
                           {"userId": "me", "maxResults": MAIL_LIMIT, "q": query})
        candidates = listed.get("messages") or []
        if not isinstance(candidates, list):
            raise ValueError("Gmail returned an invalid message list.")
        messages = []
        for item in candidates[:MAIL_LIMIT]:
            msgid = str(item.get("id", "")) if isinstance(item, dict) else ""
            if not re.fullmatch(r"[a-zA-Z0-9_-]{5,100}", msgid):
                continue
            msg = self._run(["gmail", "users", "messages", "get"],
                            {"userId": "me", "id": msgid, "format": "metadata",
                             "metadataHeaders": ["From", "Date", "Subject"]})
            h = headers(msg)
            subject = h.get("subject", "(No subject)")[:250]
            snippet = str(msg.get("snippet") or "")[:450]
            unread = "UNREAD" in (msg.get("labelIds") or [])
            level, reason = mail_importance(subject, snippet, unread)
            thread = str(msg.get("threadId") or item.get("threadId") or "")
            messages.append({
                "id": msgid, "from": h.get("from", "")[:220],
                "subject": subject, "snippet": snippet, "date": h.get("date", "")[:120],
                "unread": unread, "priority": level, "reason": reason,
                "reply_status": "not_verified",
                "url": ("https://mail.google.com/mail/?authuser="
                        + quote(self.account, safe="@") + "#all/" + quote(thread, safe=""))
                        if thread else None})
        order = {"urgent": 0, "action": 1, "review": 2, "fyi": 3}
        messages.sort(key=lambda item: (order[item["priority"]], not item["unread"]))
        return {
            "source": "gmail", "date": day.date().isoformat(),
            "timezone": TIMEZONE, "account": self.account,
            "messages": messages,
            "returned": len(messages),
            "estimated_total": listed.get("resultSizeEstimate"),
            "possibly_truncated": bool(listed.get("nextPageToken")) or len(candidates) >= MAIL_LIMIT,
            "note": ("Metadata and previews only. Action flags are heuristics; "
                     "reply status has not been verified.")}

    def _calendar(self):
        day, _, after_tomorrow = local_window()
        listed = self._run(["calendar", "events", "list"],
                           {"calendarId": "primary", "timeMin": day.isoformat(),
                            "timeMax": after_tomorrow.isoformat(),
                            "singleEvents": True, "orderBy": "startTime",
                            "maxResults": EVENT_LIMIT})
        events = []
        for item in listed.get("items") or []:
            if not isinstance(item, dict) or item.get("status") == "cancelled":
                continue
            start = item.get("start") or {}
            end = item.get("end") or {}
            if not isinstance(start, dict) or not isinstance(end, dict):
                continue
            events.append({
                "id": str(item.get("id", ""))[:150],
                "title": str(item.get("summary") or "Untitled event")[:200],
                "start": start.get("dateTime") or start.get("date"),
                "end": end.get("dateTime") or end.get("date"),
                "all_day": "dateTime" not in start,
                "url": item.get("htmlLink"),
                "response_status": next((a.get("responseStatus") for a in item.get("attendees") or []
                                         if a.get("self")), None),
                "overlap": False})
        for a, event in enumerate(events):
            if event["all_day"]:
                continue
            try:
                start_a = datetime.fromisoformat(event["start"].replace("Z", "+00:00"))
                end_a = datetime.fromisoformat(event["end"].replace("Z", "+00:00"))
                for b, other in enumerate(events):
                    if a == b or other["all_day"]:
                        continue
                    start_b = datetime.fromisoformat(other["start"].replace("Z", "+00:00"))
                    end_b = datetime.fromisoformat(other["end"].replace("Z", "+00:00"))
                    if start_a < end_b and start_b < end_a:
                        event["overlap"] = True
                        break
            except (AttributeError, ValueError, TypeError):
                continue
        return {"source": "google-calendar", "timezone": TIMEZONE,
                "events": events, "possibly_truncated": bool(listed.get("nextPageToken")),
                "note": "Primary calendar only, today and tomorrow; overlaps are possible conflicts."}

    def _drive(self):
        listed = self._run(
            ["drive", "files", "list"],
            {"pageSize": FILE_LIMIT, "orderBy": "modifiedTime desc",
             "q": "trashed = false",
             "fields": "nextPageToken,files(id,name,mimeType,description,modifiedTime,webViewLink)"})
        files = []
        for item in listed.get("files") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")[:240]
            description = str(item.get("description") or "")[:450]
            files.append({"id": str(item.get("id", ""))[:200], "name": name,
                          "description": description, "modified": item.get("modifiedTime"),
                          "url": item.get("webViewLink"),
                          "review_candidate": bool(REVIEW.search(name + " " + description))})
        return {"source": "google-drive", "files": files,
                "possibly_truncated": bool(listed.get("nextPageToken")),
                "note": ("Recent modified files only. Review candidates are inferred "
                         "from names/descriptions, not confirmed pending approvals.")}

    def read(self, service, operation):
        commands = {
            ("gmail", "profile"): (["gmail", "users", "getProfile"], {"userId": "me"}),
            ("gmail", "list"): (["gmail", "users", "messages", "list"],
                                {"userId": "me", "maxResults": 10}),
            ("google-drive", "profile"): (["drive", "about", "get"],
                                          {"fields": "user(emailAddress,displayName)"}),
            ("google-drive", "list"): (["drive", "files", "list"],
                                       {"pageSize": 10, "fields": "files(id,name,mimeType,webViewLink)",
                                        "q": "trashed = false"}),
            ("google-calendar", "profile"): (["calendar", "calendars", "get"],
                                             {"calendarId": "primary"}),
            ("google-calendar", "list"): (["calendar", "calendarList", "list"],
                                          {"maxResults": 10}),
        }
        if operation not in ("profile", "list", "briefing") or service not in (
                "gmail", "google-drive", "google-calendar"):
            raise ValueError("Unsupported Google read operation.")
        try:
            profile = self._run(*commands[("gmail", "profile")])
            if str(profile.get("emailAddress", "")).lower() != self.account:
                return {"ok": False, "state": "account_mismatch",
                        "message": "Signed-in Google account differs from the host-selected account."}
            if operation == "briefing":
                actions = {"gmail": self._mail, "google-drive": self._drive,
                           "google-calendar": self._calendar}
                data = actions[service]()
            elif (service, operation) == ("gmail", "profile"):
                data = profile
            else:
                data = self._run(*commands[(service, operation)])
            return {"ok": True, "account": self.account, "service": service,
                    "read_only": True, "data": data}
        except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError):
            return {"ok": False, "state": "authorization_or_api_unavailable",
                    "message": ("Google read unavailable. Check account, local OAuth login, "
                                "service access and API scopes; no results were invented.")}


def main():
    parser = argparse.ArgumentParser(description="SPARK read-only Google Workspace MCP")
    parser.add_argument("--cli", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--service", choices=["gmail", "google-drive", "google-calendar"],
                        required=True)
    options = parser.parse_args()
    reader = GoogleReader(options.cli, options.account)
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("spark-" + options.service)

    @server.tool()
    async def google_account_status() -> dict:
        """Verify selected Google account identity and API availability."""
        return await asyncio.to_thread(reader.read, options.service, "profile")

    @server.tool()
    async def google_list_items() -> dict:
        """Legacy, bounded read-only list of mail IDs, files or calendars."""
        return await asyncio.to_thread(reader.read, options.service, "list")

    @server.tool()
    async def google_daily_briefing() -> dict:
        """Retrieve dated source-linked mail, calendar events or Drive review candidates."""
        return await asyncio.to_thread(reader.read, options.service, "briefing")

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
