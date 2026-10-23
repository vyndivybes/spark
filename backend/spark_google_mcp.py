"""Google Workspace adapter using the host's encrypted gws login.

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
import base64
import tempfile
from email.message import EmailMessage

TIMEZONE = "Asia/Kolkata"  # Fixed-offset IST needs no tzdata installation on Windows.
IST = timezone(timedelta(hours=5, minutes=30))
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
    local = (now or datetime.now(timezone.utc)).astimezone(IST)
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


GOOGLE_WRITE_TOOLS = {
    'gmail': ['google_save_email_draft'],
    'google-drive': ['google_save_drive_text'],
    'google-calendar': ['google_save_calendar_event'],
}


class GoogleAccessError(ValueError):
    def __init__(self, state, message):
        self.state = state
        super().__init__(message)


class GoogleReader:
    def __init__(self, cli, account, config_dir=None):
        self.cli = Path(cli)
        if not self.cli.is_absolute() or not self.cli.is_file():
            raise ValueError("Configure the installed native Google Workspace CLI.")
        if not isinstance(account, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", account):
            raise ValueError("Configure the expected Google account on the host.")
        self.account = account.lower()
        self.config_dir = Path(config_dir) if config_dir is not None else None
        if self.config_dir is not None and not self.config_dir.is_absolute():
            raise ValueError('Configure an absolute account credential directory.')

    def _run(self, command, params, *, body=None, upload=None):
        invocation = [str(self.cli), *command, '--params', json.dumps(params)]
        if body is not None:
            invocation += ['--json', json.dumps(body)]
        if upload is not None:
            invocation += ['--upload', Path(upload).name, '--upload-content-type', 'text/plain']
        environment = None
        if self.config_dir is not None:
            environment = dict(os.environ)
            for key in ('GOOGLE_WORKSPACE_CLI_TOKEN', 'GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE'):
                environment.pop(key, None)
            environment['GOOGLE_WORKSPACE_CLI_CONFIG_DIR'] = str(self.config_dir)
        result = subprocess.run(invocation,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                encoding='utf-8', timeout=30, shell=False,
                                cwd=str(Path(upload).parent) if upload is not None else None,
                                env=environment)
        if len(result.stdout.encode('utf-8')) > 500_000:
            raise ValueError('Google access unavailable. Complete the local OAuth login and check API permissions.')
        value = json.loads(result.stdout)
        if isinstance(value, dict) and isinstance(value.get('error'), dict):
            code = value['error'].get('code')
            if code == 403:
                raise GoogleAccessError('permission_denied', 'Google denied API access for this signed-in account (403). Check Google Workspace, app and API permissions. Repeated sign-in alone may not resolve this.')
            if code == 401:
                raise GoogleAccessError('authorization_required', 'Google login expired or was not accepted (401). Reconnect this account.')
        if result.returncode:
            raise ValueError('Google access unavailable. Check the account authorization and API permissions.')
        if not isinstance(value, dict) or 'error' in value:
            raise ValueError('Google returned an unsupported response.')
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
            ("gmail", "pending"): (["gmail", "users", "messages", "list"],
                                   {"userId": "me", "maxResults": 5, "q": "in:inbox is:unread"}),
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
        if operation not in ("profile", "list", "briefing", "pending") or service not in (
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
            elif (service, operation) == ("gmail", "pending"):
                listed = self._run(*commands[(service, operation)])
                messages = []
                for item in listed.get("messages", [])[:5]:
                    message_id = _id(item.get("id"))
                    if not message_id:
                        raise ValueError("Gmail returned no message identifier.")
                    detail = self._run(["gmail", "users", "messages", "get"],
                        {"userId": "me", "id": message_id, "format": "metadata",
                         "metadataHeaders": ["From", "Subject", "Date"],
                         "fields": "id,threadId,snippet,internalDate,payload(headers)"})
                    header_values = {h.get("name", "").lower(): h.get("value", "")
                               for h in detail.get("payload", {}).get("headers", [])}
                    messages.append({"id": message_id, "from": header_values.get("from", "")[:500],
                                     "subject": header_values.get("subject", "")[:1000],
                                     "date": header_values.get("date", "")[:150],
                                     "snippet": detail.get("snippet", "")[:1000]})
                data = {"interpretation": "Unread messages in the inbox, not a determination of which require a reply.",
                        "messages": messages, "shown": len(messages),
                        "more_available": bool(listed.get("nextPageToken"))}
            else:
                data = self._run(*commands[(service, operation)])
            return {"ok": True, "account": self.account, "service": service,
                    "read_only": True, "data": data}
        except GoogleAccessError as exc:
            return {"ok": False, "state": exc.state, "message": str(exc)}
        except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError):
            return {"ok": False, "state": "authorization_required",
                    "message": ("Google read unavailable. Check account, local OAuth login, "
                                "service access and API scopes; no results were invented.")}

    def write(self, service, operation, arguments, *, allowed=False):
        """Fixed draft/file/event operations only. Sending mail is never implemented."""
        if not allowed:
            return {'ok': False, 'state': 'write_not_authorized', 'message': 'Host write permission is disabled.'}
        expected = {'gmail': 'draft', 'google-drive': 'text', 'google-calendar': 'event'}
        if operation != expected.get(service):
            return {'ok': False, 'state': 'operation_denied', 'message': 'Unsupported write. Email sending is disabled.'}
        try:
            if not isinstance(arguments, dict):
                raise ValueError('Supply a structured write request.')
            commands, params, body, content = build_write(service, arguments)
        except (ValueError, TypeError) as exc:
            return {'ok': False, 'state': 'invalid_arguments', 'message': str(exc)}
        verified = self.read(service, 'profile')
        if not verified.get('ok'):
            return verified
        try:
            if service == 'google-drive' and params.get('fileId'):
                metadata = self._run(['drive', 'files', 'get'],
                    {'fileId': params['fileId'], 'fields': 'id,mimeType'})
                if metadata.get('mimeType') not in ('text/plain', 'text/markdown'):
                    return {'ok': False, 'state': 'unsupported_file_type',
                            'message': 'This tool updates text files only; it will not replace Google Docs or binary files.'}
            if content is None:
                data = self._run(commands, params, body=body)
            else:
                with tempfile.TemporaryDirectory(prefix='spark-drive-') as directory:
                    source = Path(directory) / 'content.txt'
                    source.write_text(content, encoding='utf-8')
                    data = self._run(commands, params, body=body, upload=str(source))
            return {'ok': True, 'service': service, 'operation': operation,
                    'sent': False, 'data': data}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {'ok': False, 'state': 'write_unverified',
                    'message': 'Write was not verified. Check Google permissions and inspect the item before retrying; no automatic retry.'}


def _text(value, label, limit=2000, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(f'Invalid {label}.')
    return value


def _id(value):
    if value not in (None, '') and (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', value)):
        raise ValueError('Invalid item identifier.')
    return value


def build_write(service, args):
    """Build only documented, explicitly supported provider requests."""
    if service == 'gmail':
        if set(args) - {'to', 'subject', 'body', 'draft_id'}:
            raise ValueError('Only email draft fields are allowed. Sending is disabled.')
        recipient = _text(args.get('to'), 'recipient', 320)
        if not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+', recipient):
            raise ValueError('Supply one email recipient.')
        subject = _text(args.get('subject'), 'subject', 998)
        if '\r' in subject or '\n' in subject:
            raise ValueError('Subject must be a single line.')
        message = EmailMessage()
        message['To'] = recipient
        message['Subject'] = subject
        message.set_content(_text(args.get('body'), 'email body', 100000, empty=True))
        body = {'message': {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode('ascii')}}
        params = {'userId': 'me'}
        draft = _id(args.get('draft_id'))
        if draft:
            params['id'] = draft
        return ['gmail', 'users', 'drafts', 'update' if draft else 'create'], params, body, None
    if service == 'google-drive':
        if set(args) - {'name', 'text', 'file_id'}:
            raise ValueError('Only text content and a file name are supported.')
        name = _text(args.get('name'), 'file name', 200)
        content = _text(args.get('text'), 'file text', 200000, empty=True)
        file_id = _id(args.get('file_id'))
        params = {'fields': 'id,name,mimeType,webViewLink'}
        if file_id:
            params['fileId'] = file_id
        return ['drive', 'files', 'update' if file_id else 'create'], params, {'name': name, 'mimeType': 'text/plain'}, content
    if service == 'google-calendar':
        if set(args) - {'summary', 'start', 'end', 'description', 'location', 'event_id'}:
            raise ValueError('Only personal event fields are supported; invitations are disabled.')
        body = {'summary': _text(args.get('summary'), 'event summary', 500)}
        dates = []
        for key in ('start', 'end'):
            value = _text(args.get(key), key, 64)
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.utcoffset() is None:
                raise ValueError('Event times must include a timezone offset, such as +05:30.')
            dates.append(parsed)
            body[key] = {'dateTime': value}
        if dates[1] <= dates[0]:
            raise ValueError('Event end must be after its start.')
        for key in ('description', 'location'):
            if key in args:
                body[key] = _text(args[key], key, 8000, empty=True)
        params = {'calendarId': 'primary', 'sendUpdates': 'none'}
        event_id = _id(args.get('event_id'))
        if event_id:
            params['eventId'] = event_id
        return ['calendar', 'events', 'patch' if event_id else 'insert'], params, body, None
    raise ValueError('Unsupported Google service.')


def main():
    parser = argparse.ArgumentParser(description="SPARK Google Workspace MCP")
    parser.add_argument("--cli", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--service", choices=["gmail", "google-drive", "google-calendar"],
                        required=True)
    parser.add_argument("--allow-writes", action="store_true")
    parser.add_argument("--official-account")
    parser.add_argument("--official-config-dir")
    options = parser.parse_args()
    reader = GoogleReader(options.cli, options.account)
    readers = {'personal': reader}
    if bool(options.official_account) != bool(options.official_config_dir):
        parser.error('Official account and its credential directory must be configured together.')
    if options.official_account:
        readers['official'] = GoogleReader(options.cli, options.official_account, options.official_config_dir)

    def selected(account):
        if account in readers:
            return readers[account]
        for candidate in readers.values():
            if isinstance(account, str) and candidate.account == account.lower():
                return candidate
        raise ValueError('This account is not configured in Spark. Choose personal or official.')
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("spark-" + options.service)

    @server.tool()
    async def google_account_status(account: str = "personal") -> dict:
        """Verify selected Google account identity and API availability."""
        return await asyncio.to_thread(selected(account).read, options.service, "profile")

    @server.tool()
    async def google_list_items(account: str = "personal") -> dict:
        """Legacy, bounded read-only list of mail IDs, files or calendars."""
        return await asyncio.to_thread(selected(account).read, options.service, "list")

    @server.tool()
    async def google_daily_briefing() -> dict:
        """Retrieve dated source-linked mail, calendar events or Drive review candidates."""
        return await asyncio.to_thread(reader.read, options.service, "briefing")

    if options.service == 'gmail':
        @server.tool()
        async def google_pending_email(account: str = 'personal') -> dict:
            """Read up to five unread inbox emails: sender, subject, date and snippet. Verifies the account automatically. Does not mark mail read or send anything."""
            return await asyncio.to_thread(selected(account).read, 'gmail', 'pending')

    if options.allow_writes:
        if options.service == 'gmail':
            @server.tool()
            async def google_save_email_draft(to: str, subject: str, body: str, draft_id: str = '', account: str = 'personal') -> dict:
                """Create or update an email draft. Does not send email. Sending remains blocked."""
                return await asyncio.to_thread(selected(account).write, 'gmail', 'draft',
                    dict(to=to, subject=subject, body=body, draft_id=draft_id), allowed=True)
        elif options.service == 'google-drive':
            @server.tool()
            async def google_save_drive_text(name: str, text: str, file_id: str = '') -> dict:
                """Create a text file or replace a specified text file's content in Drive."""
                return await asyncio.to_thread(reader.write, 'google-drive', 'text',
                    dict(name=name, text=text, file_id=file_id), allowed=True)
        elif options.service == 'google-calendar':
            @server.tool()
            async def google_save_calendar_event(summary: str, start: str, end: str,
                                                 description: str = '', location: str = '', event_id: str = '') -> dict:
                """Create or update a primary-calendar event. Times require timezone offsets. No invitations."""
                return await asyncio.to_thread(reader.write, 'google-calendar', 'event',
                    dict(summary=summary, start=start, end=end, description=description,
                         location=location, event_id=event_id), allowed=True)

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
