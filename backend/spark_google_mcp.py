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
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
from urllib.parse import urlencode
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
    def __init__(self, state, message, *, quota_project=False):
        self.state = state
        self.quota_project = quota_project
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
        if self.config_dir is not None and body is None and upload is None and command in (
                ['drive', 'about', 'get'], ['drive', 'files', 'list']):
            return self._official_drive_read(command, params)
        invocation = [str(self.cli), *command]
        if params is not None:
            invocation += ['--params', json.dumps(params)]
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
        empty_triage = command[:2] == ['gmail', '+triage'] and not result.stdout.strip() and result.returncode == 0
        value = {'messages': []} if empty_triage else json.loads(result.stdout)
        if isinstance(value, dict) and isinstance(value.get('error'), dict):
            code = value['error'].get('code')
            if code == 403:
                quota_project = 'serviceusage.services.use' in str(value['error'].get('message', ''))
                raise GoogleAccessError('permission_denied', 'Google denied API access for this signed-in account (403). Check Google Workspace, app and API permissions. Repeated sign-in alone may not resolve this.', quota_project=quota_project)
            if code == 401:
                raise GoogleAccessError('authorization_required', 'Google login expired or was not accepted (401). Reconnect this account.')
        if result.returncode:
            raise ValueError('Google access unavailable. Check the account authorization and API permissions.')
        if not isinstance(value, dict) or 'error' in value:
            raise ValueError('Google returned an unsupported response.')
        return value

    def _official_drive_read(self, command, params):
        """Use OAuth directly for Drive reads; gws adds an unnecessary quota header.

        The CLI decrypts its own store into this process's memory only. Never
        persist, log or return its credentials. Fixed Google endpoints and live
        identity verification keep refresh tokens and results account-bound.
        """
        credentials = self._run(['auth', 'export', '--unmasked'], None)
        if not all(isinstance(credentials.get(key), str) and credentials[key]
                   for key in ('client_id', 'client_secret', 'refresh_token')):
            raise GoogleAccessError('authorization_required', 'Official Drive credentials are unavailable.')
        opener = build_opener(ProxyHandler({}))
        def request(url, *, data=None, token=None):
            headers = {'Authorization': 'Bearer ' + token} if token else {'Content-Type': 'application/x-www-form-urlencoded'}
            try:
                with opener.open(Request(url, data=data, headers=headers), timeout=20) as response:
                    raw = response.read(500_001)
                if len(raw) > 500_000:
                    raise ValueError('Google response exceeded the read limit.')
                value = json.loads(raw)
                if not isinstance(value, dict) or 'error' in value:
                    raise ValueError('Google returned an unsupported response.')
                return value
            except HTTPError as error:
                if error.code == 403:
                    raise GoogleAccessError('permission_denied', 'Google denied official Drive access (403). Grant read-only Drive consent and check Workspace policy.') from None
                raise GoogleAccessError('authorization_required', 'Google could not authorize the official Drive read.') from None
        grant = {key: credentials[key] for key in ('client_id', 'client_secret', 'refresh_token')}
        grant['grant_type'] = 'refresh_token'
        token = request('https://oauth2.googleapis.com/token', data=urlencode(grant).encode())
        access = token.get('access_token')
        if not isinstance(access, str) or not access:
            raise GoogleAccessError('authorization_required', 'Google could not refresh the official account.')
        identity = request('https://www.googleapis.com/oauth2/v2/userinfo', token=access)
        if str(identity.get('email', '')).lower() != self.account:
            raise GoogleAccessError('account_mismatch', 'Signed-in Google account differs from the host-selected account.')
        resource = 'about' if command == ['drive', 'about', 'get'] else 'files'
        return request('https://www.googleapis.com/drive/v3/' + resource + '?' + urlencode(params, doseq=True), token=access)

    def _read_gmail_helper(self, operation, *, search_query=None, search_limit=20):
        """Use gws's read-only helper for its known quota-header defect.

        gws auth status refreshes the isolated credentials and obtains the email
        from Google's live userinfo endpoint; it does not trust a saved label.
        No tokens are exported and no IAM/billing permissions are changed.
        """
        try:
            status = self._run(['auth', 'status'], None)
            if status.get('token_valid') is not True:
                raise GoogleAccessError('authorization_required', 'Google could not verify this account login.')
            if str(status.get('user', '')).lower() != self.account:
                raise GoogleAccessError('account_mismatch', 'Signed-in Google account differs from the host-selected account.')
            limit = search_limit if operation == 'search' else {'profile': 1, 'pending': 5, 'list': 10, 'briefing': MAIL_LIMIT}[operation]
            query = 'in:inbox is:unread' if operation == 'pending' else '-in:spam -in:trash'
            if operation == 'search':
                query = 'in:anywhere ' + search_query
            day, tomorrow, _ = local_window()
            if operation == 'briefing':
                query += f' after:{int(day.timestamp()) - 1} before:{int(tomorrow.timestamp())} -in:sent'
            result = self._run(['gmail', '+triage', '--max', str(limit), '--query=' + query,
                                '--labels', '--format', 'json'], None)
            rows = result.get('messages')
            if not isinstance(rows, list):
                raise ValueError('Google returned an invalid message list.')
            messages = []
            for row in rows[:limit]:
                if not isinstance(row, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{5,100}', str(row.get('id', ''))):
                    raise ValueError('Google returned an invalid message identifier.')
                message = {key: str(row.get(key, ''))[:bound] for key, bound in
                           (('id', 100), ('from', 500), ('subject', 1000), ('date', 150))}
                message['snippet'] = ''  # The helper supplies metadata only.
                if operation == 'briefing':
                    unread = 'UNREAD' in (row.get('labels') or [])
                    level, reason = mail_importance(message['subject'], '', unread)
                    message.update(unread=unread, priority=level, reason=reason,
                                   reply_status='not_verified', url=None)
                messages.append(message)
            # A successful helper read also proves Gmail access, even when empty.
            data = {'messages': messages, 'shown': len(messages),
                    'more_available': len(rows) >= limit,
                    'interpretation': 'Message metadata only; whether a reply is required has not been verified.'}
            if operation == 'profile':
                data = {'emailAddress': self.account, 'verification': 'live_google_userinfo_and_gmail_read'}
            elif operation == 'search':
                data.update(query=search_query, scope='Server-side Gmail search across mailbox history, including archived, sent, spam and trash; the query may narrow this scope.',
                            possibly_truncated=len(rows) >= limit,
                            note='Bounded metadata results. No matches means this query returned no matches, not proof that a sender never emailed you. Refine the query when possibly_truncated is true.')
            elif operation == 'briefing':
                data.update(source='gmail', date=day.date().isoformat(), timezone=TIMEZONE,
                            account=self.account, returned=len(messages),
                            possibly_truncated=len(rows) >= limit, note=data['interpretation'])
            return {'ok': True, 'account': self.account, 'service': 'gmail',
                    'read_only': True, 'transport': 'gws_readonly_helper', 'data': data}
        except GoogleAccessError as exc:
            return {'ok': False, 'state': exc.state, 'message': str(exc)}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {'ok': False, 'state': 'authorization_required',
                    'message': 'Google read unavailable; no results were invented.'}

    def search(self, query, limit=20):
        if (not isinstance(query, str) or not query.strip() or len(query) > 500
                or any(ord(char) < 32 for char in query)
                or type(limit) is not int or not 1 <= limit <= 20):
            return {'ok': False, 'state': 'invalid_arguments',
                    'message': 'Use a Gmail query of 1–500 characters and a limit of 1–20.'}
        # A personal-store token override must also pass the normal identity gate.
        if self.config_dir is None:
            verified = self.read('gmail', 'profile')
            if not verified.get('ok'):
                return verified
        return self._read_gmail_helper('search', search_query=query.strip(), search_limit=limit)

    def search_drive(self, query, limit=25, page_token=''):
        if (not isinstance(query, str) or not query.strip() or len(query) > 500
                or any(ord(char) < 32 for char in query)
                or type(limit) is not int or not 1 <= limit <= 25
                or not isinstance(page_token, str) or len(page_token) > 2048
                or any(ord(char) < 32 for char in page_token)):
            return {'ok': False, 'state': 'invalid_arguments', 'message': 'Use search text of 1–500 characters, limit 1–25 and an optional returned page token.'}
        verified = self.read('google-drive', 'profile')
        if not verified.get('ok'):
            return verified
        literal = query.strip().replace('\\', '\\\\').replace("'", "\\'")
        params = {'q': "trashed = false and fullText contains '" + literal + "'", 'pageSize': limit,
                  'corpora': 'allDrives', 'includeItemsFromAllDrives': True, 'supportsAllDrives': True,
                  'fields': 'nextPageToken,incompleteSearch,files(id,name,mimeType,modifiedTime,webViewLink,driveId)'}
        if page_token:
            params['pageToken'] = page_token
        try:
            result = self._run(['drive', 'files', 'list'], params)
            files = result.get('files', [])
            if not isinstance(files, list):
                raise ValueError('Invalid Drive results.')
            clean = [{key: str(row.get(key, ''))[:1000] for key in ('id', 'name', 'mimeType', 'modifiedTime', 'webViewLink', 'driveId')}
                     for row in files[:limit] if isinstance(row, dict)]
            return {'ok': True, 'account': self.account, 'read_only': True,
                    'data': {'query': query.strip(), 'files': clean, 'shown': len(clean),
                             'next_page_token': result.get('nextPageToken'),
                             'possibly_truncated': bool(result.get('nextPageToken')) or result.get('incompleteSearch') is True,
                             'scope': 'Google full-text index across accessible My Drive and shared drives; no recent-file or date restriction. Follow next_page_token for more results.'}}
        except GoogleAccessError as exc:
            return {'ok': False, 'state': exc.state, 'message': str(exc)}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {'ok': False, 'state': 'unavailable', 'message': 'Drive search could not be verified; no results were invented.'}

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

    def _tasks(self):
        """Bounded pending Google Tasks read; no task is changed or completed."""
        lists = self._run(['tasks', 'tasklists', 'list'], {'maxResults': 10})
        tasks = []
        truncated = bool(lists.get('nextPageToken'))
        for tasklist in (lists.get('items') or [])[:10]:
            list_id = tasklist.get('id') if isinstance(tasklist, dict) else None
            if not isinstance(list_id, str) or not list_id:
                raise ValueError('Google Tasks returned an invalid list.')
            remaining = 100 - len(tasks)
            if remaining <= 0:
                truncated = True
                break
            page = self._run(['tasks', 'tasks', 'list'], {
                'tasklist': list_id, 'maxResults': remaining,
                'showCompleted': False, 'showDeleted': False, 'showHidden': False})
            truncated = truncated or bool(page.get('nextPageToken'))
            for task in (page.get('items') or [])[:remaining]:
                if not isinstance(task, dict) or task.get('status') == 'completed' or task.get('deleted') or task.get('hidden'):
                    continue
                tasks.append({'id': str(task.get('id', ''))[:200],
                              'list_id': list_id[:200],
                              'title': str(task.get('title') or '(untitled task)')[:240],
                              'due': task.get('due'), 'status': 'needsAction',
                              'url': 'https://tasks.google.com/'})
        tasks.sort(key=lambda task: task.get('due') or '9999')
        return {'source': 'google-tasks', 'tasks': tasks,
                'possibly_truncated': truncated,
                'note': 'Up to 10 lists and 100 pending tasks; completed, hidden and deleted tasks excluded. Due values represent dates.'}

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
                "gmail", "google-drive", "google-calendar", "google-tasks"):
            raise ValueError("Unsupported Google read operation.")
        if service == 'google-tasks' and operation != 'briefing':
            raise ValueError('Google Tasks supports only its bounded read-only briefing.')
        try:
            if service == 'google-drive' and self.config_dir is not None:
                identity = self._run(['drive', 'about', 'get'], {'fields': 'user(emailAddress)'})
                profile = identity.get('user', {})
            else:
                profile = self._run(*commands[("gmail", "profile")])
            if str(profile.get("emailAddress", "")).lower() != self.account:
                return {"ok": False, "state": "account_mismatch",
                        "message": "Signed-in Google account differs from the host-selected account."}
            if operation == "briefing":
                actions = {"gmail": self._mail, "google-drive": self._drive,
                           "google-calendar": self._calendar, "google-tasks": self._tasks}
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
            if exc.quota_project and self.config_dir is not None and service == 'gmail':
                return self._read_gmail_helper(operation)
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

    if options.service == 'google-calendar':
        @server.tool()
        async def google_tasks_briefing() -> dict:
            """Read up to 100 pending Google Tasks on the host-selected personal account. Never changes tasks."""
            return await asyncio.to_thread(reader.read, 'google-tasks', 'briefing')

    if options.service == 'gmail':
        @server.tool()
        async def google_search_email(query: str, account: str = 'personal', limit: int = 20) -> dict:
            """Search the selected Gmail account's full history, not just unread inbox mail. Returns up to 20 metadata matches; never sends or marks mail read."""
            return await asyncio.to_thread(selected(account).search, query, limit)

        @server.tool()
        async def google_pending_email(account: str = 'personal') -> dict:
            """Read up to five unread inbox emails: sender, subject, date and snippet. Verifies the account automatically. Does not mark mail read or send anything."""
            return await asyncio.to_thread(selected(account).read, 'gmail', 'pending')

    if options.service == 'google-drive':
        @server.tool()
        async def google_search_drive(query: str, account: str = 'personal', limit: int = 25, page_token: str = '') -> dict:
            """Search accessible Drive file names and indexed text across all dates. Follow returned page tokens; never changes files."""
            return await asyncio.to_thread(selected(account).search_drive, query, limit, page_token)

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
