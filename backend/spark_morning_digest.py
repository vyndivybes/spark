"""Capability 01 — Morning Digest.

Composes one scheduled, persisted daily digest from the read-only Google
snapshots provided by PR #48 (spark_sync.py), local agenda tasks and an
optional opt-in RSS news feed. Every job has a *final* state (completed or
failed); no endless "finalizing" phase exists. Windows-local TTS is available
only on explicit request, uses the built-in SpeechSynthesizer and performs no
network call. Digest runs, triage results, acknowledgement receipts and speech
attempts are persisted for history and acceptance evidence.
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import time
import xml.etree.ElementTree
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

IST = timezone(timedelta(hours=5, minutes=30))
MAX_NEWS_BYTES = 100_000
NEWS_TIMEOUT = 10
MAX_SPEECH = 2400
FINAL_STATES = ("completed", "failed")
UNAVAILABLE_STATES = ("not_configured", "failed", "forbidden", "invalid", "upgrade_required",
                      "waiting", "unknown")


class DigestError(ValueError):
    """Invalid digest request or configuration."""


def ist_date(timestamp=None):
    return datetime.fromtimestamp(
        timestamp if timestamp is not None else time.time(), IST).date().isoformat()


class NewsSource:
    """Optional opt-in local RSS read; disabled unless the user enables it."""

    def __init__(self, url):
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            raise DigestError("Enable news with an RSS or Atom URL. It is off by default.")
        self.url = url

    def fetch(self, *, limit=8, timeout=NEWS_TIMEOUT):
        with urlopen(Request(self.url, headers={"User-Agent": "SPARK/1.0"}), timeout=timeout) as body:
            blob = body.read(MAX_NEWS_BYTES)
        root = xml.etree.ElementTree.fromstring(blob)
        items = []
        for node in root.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag not in ("item", "entry"):
                continue
            title = link = date = None
            for child in list(node):
                name = child.tag.rsplit("}", 1)[-1]
                if name == "title" and title is None:
                    title = (child.text or "").strip()[:200]
                elif name == "link" and link is None:
                    link = (child.text or "").strip() or (child.attrib or {}).get("href")
                elif name in ("pubDate", "updated", "published") and date is None:
                    date = (child.text or "").strip()[:60]
            if title:
                items.append({"title": title, "url": link, "date": date})
            if len(items) >= limit:
                break
        return {"source": "rss-news", "url": self.url, "items": items,
                "fetched_at": time.time()}


class DigestEngine:
    """One digest per project/day; persisted history with final job states."""

    def __init__(self, root, sync, *, clock=time.time, runner=None,
                 tasks=None):
        self.root = Path(root) / "morning-digest"
        self.sync = sync
        self.clock = clock
        self.runner = runner or _speak_windows
        self.tasks = tasks  # Optional callable(project) -> list of due tasks
        if self.root.is_symlink():
            raise DigestError("Linked digest storage is prohibited.")

    # -- storage ---------------------------------------------------------
    @contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "digests.sqlite3"
        if path.is_symlink():
            raise DigestError("Linked digest storage is prohibited.")
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS runs("
                           "date TEXT PRIMARY KEY,status TEXT NOT NULL,created REAL,"
                           "last_fetched REAL,sources TEXT NOT NULL,triage TEXT NOT NULL,"
                           "text TEXT NOT NULL,speech TEXT,acknowledged INTEGER DEFAULT 0,"
                           "acknowledged_at REAL,delta TEXT)")
                db.execute("CREATE TABLE IF NOT EXISTS settings("
                           "key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            yield db
            db.commit()
        finally:
            db.close()

    def configure(self, *, schedule_ist="08:30", news_enabled=False, news_url=None):
        """Persist the IST schedule and the opt-in news switch."""
        if not re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", str(schedule_ist)):
            raise DigestError("Choose a daily schedule time as HH:MM (IST).")
        if type(news_enabled) is not bool:
            raise DigestError("News must be explicitly enabled or disabled.")
        if news_enabled:
            news_url = news_url or self._stored("news_url")
            NewsSource(news_url)  # URL validation happens in NewsSource
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES('schedule_ist',?)", (schedule_ist,))
            db.execute("INSERT OR REPLACE INTO settings VALUES('news_enabled',?)",
                       (json.dumps(news_enabled),))
            if news_url is not None:
                db.execute("INSERT OR REPLACE INTO settings VALUES('news_url',?)", (news_url,))
        return self.status()

    def _stored(self, key):
        with self._db() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def _enabled_news(self):
        if self._stored("news_enabled") != "true":
            return None
        url = self._stored("news_url")
        if not url:
            raise DigestError("News is enabled but no RSS URL is configured.")
        return NewsSource(url)

    def scheduled_time(self):
        return self._stored("schedule_ist")

    def status(self):
        with self._db() as db:
            config = {row["key"]: row["value"] for row in db.execute("SELECT key,value FROM settings")}
            row = db.execute("SELECT date,status,created,last_fetched,speech,acknowledged,"
                             "acknowledged_at FROM runs ORDER BY date DESC LIMIT 1").fetchone()
        latest = None
        if row:
            latest = {"date": row["date"], "status": row["status"],
                      "created_at": row["created"], "last_fetched": row["last_fetched"],
                      "speech": row["speech"], "acknowledged": bool(row["acknowledged"]),
                      "acknowledged_at": row["acknowledged_at"]}
        return {"schema": "spark.morning_digest.v1",
                "schedule_ist": config.get("schedule_ist"),
                "news_enabled": json.loads(config["news_enabled"]) if "news_enabled" in config else False,
                "news_url": config.get("news_url"),
                "news_policy": "opt-in only; free RSS feed; bounded size and timeout",
                "latest_run": latest,
                "final_states": FINAL_STATES,
                "tts": {"engine": "Windows System.Speech (local, built-in)",
                        "network_free": True,
                        "requires_explicit_request": True}}

    def history(self, *, limit=14):
        if type(limit) is not int or not 1 <= limit <= 60:
            raise DigestError("Request between 1 and 60 digest history entries.")
        with self._db() as db:
            rows = db.execute("SELECT date,status,created,last_fetched,triage,delta,"
                              "speech,acknowledged,acknowledged_at FROM runs "
                              "ORDER BY date DESC LIMIT ?", (limit,)).fetchall()
        return {"runs": [{"date": r["date"], "status": r["status"],
                          "created_at": r["created"], "last_fetched": r["last_fetched"],
                          "triage_count": len(json.loads(r["triage"] or "[]")),
                          "delta": json.loads(r["delta"] or "null"),
                          "speech": r["speech"],
                          "acknowledged": bool(r["acknowledged"]),
                          "acknowledged_at": r["acknowledged_at"]} for r in rows],
                "count": len(rows)}

    # -- composition -----------------------------------------------------
    def _triage(self, briefing):
        """Ordered action candidates: source-linked, never asserted as truth."""
        items = []
        for mail in briefing.get("emails") or []:
            if isinstance(mail, dict) and mail.get("priority") in ("urgent", "action", "review"):
                items.append({"kind": "email", "priority": mail["priority"],
                              "reason": mail.get("reason"), "unread": bool(mail.get("unread")),
                              "title": mail.get("subject", "")[:250],
                              "url": mail.get("url"), "source": "gmail"})
        for event in briefing.get("events") or []:
            if not isinstance(event, dict):
                continue
            overlap = bool(event.get("overlap"))
            response = event.get("response_status")
            if overlap or response in ("needsAction", "declined"):
                items.append({"kind": "calendar", "priority": "action" if overlap else "review",
                              "reason": ("Overlap detected; confirm attendance" if overlap
                                         else "Your response may be outstanding"),
                              "title": event.get("title", "")[:200],
                              "start": event.get("start"), "url": event.get("url"),
                              "source": "google-calendar"})
        for doc in briefing.get("documents") or []:
            if isinstance(doc, dict) and doc.get("review_candidate"):
                items.append({"kind": "document", "priority": "review",
                              "reason": "Named like a review candidate; verify the document",
                              "title": doc.get("name", "")[:240], "url": doc.get("url"),
                              "source": "google-drive"})
        order = {"urgent": 0, "action": 1, "review": 2}
        items.sort(key=lambda item: order.get(item["priority"], 9))
        return items

    @staticmethod
    def _source_states(briefing):
        states = {}
        for service, value in (briefing.get("sources") or {}).items():
            if not isinstance(value, dict):
                continue
            state = value.get("state") or "unknown"
            failure = value.get("error")
            if isinstance(failure, str) and re.search(r"40[13]", failure):
                state = "forbidden"
            states[service] = {"state": state, "stale": bool(value.get("stale")),
                               "last_success": value.get("last_success"),
                               "message": value.get("message"),
                               "error": value.get("error"),
                               "account": value.get("account")}
        return states

    def run(self, *, now=None):
        """Compose and persist today's digest. Always ends in a final state."""
        now = now if now is not None else self.clock()
        started = time.time()
        date = ist_date(now)
        try:
            briefing = self.sync.briefing()
            if not isinstance(briefing, dict):
                raise DigestError("Integration snapshots returned an invalid digest base.")
            sources = self._source_states(briefing)
            items = self._triage(briefing)
            emails = briefing.get("emails") or []
            events = briefing.get("events") or []
            documents = briefing.get("documents") or []
            tasks = None
            if self.tasks is not None:
                tasks = self.tasks(None)
                sources["tasks"] = {"state": "current", "stale": False}
            else:
                sources["tasks"] = {"state": "not_configured",
                                    "message": "No task source is enabled for this account."}
            news = None
            try:
                news = self._enabled_news()
                if news is not None:
                    news = news.fetch()
                    sources["rss-news"] = {"state": "current", "stale": False,
                                           "last_success": news.get("fetched_at")}
            except (OSError, TimeoutError, ValueError, xml.etree.ElementTree.ParseError) as error:
                news = None
                sources["rss-news"] = {"state": "failed", "stale": True,
                                       "message": "News feed read failed: " + str(error)[:120]}
            live = {"emails": len(emails), "events": len(events),
                    "documents": len(documents), "triage": len(items)}
            previous = self._previous_counts(date)
            delta = {"today": live, "previous": previous,
                     "email_change": (None if not isinstance(previous.get("emails"), int)
                                      else live["emails"] - previous["emails"])}
            text = self._compose_text(date, live, items, tasks, news, delta, sources)
            all_unavailable = (bool(sources) and all(
                v.get("state") in UNAVAILABLE_STATES for v in sources.values()))
            status = "failed" if all_unavailable else "completed"
            result = {"date": date, "status": status, "created_at": started,
                      "last_fetched": briefing.get("generated_at"),
                      "sources": sources, "triage": items, "delta": delta,
                      "texts": {"digest_text": text},
                      "emails": emails, "events": events,
                      "documents": documents, "tasks": tasks or [],
                      "news": (news or {}).get("items") or [],
                      "timezone": "Asia/Kolkata", "read_only": True}
            with self._db() as db:
                db.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?,?,NULL,0,NULL,?)",
                           (date, status, started, result["last_fetched"],
                            json.dumps(sources, ensure_ascii=False),
                            json.dumps(items, ensure_ascii=False), text,
                            json.dumps(delta, ensure_ascii=False)))
            result["speech_text"] = text
            return result
        except (DigestError, ValueError, TypeError, json.JSONDecodeError, OSError) as error:
            message = "Digest could not be composed: " + str(error)[:200]
            with self._db() as db:
                db.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,NULL,?,?,'',? ,0,NULL,'{}')",
                           (date, "failed", started,
                            json.dumps({"state": "failed", "message": message}),
                            "[]", message))
            return {"date": date, "status": "failed", "created_at": started,
                    "last_fetched": None, "sources": {"state": "failed",
                    "message": message}, "triage": [], "delta": {},
                    "emails": [], "events": [], "documents": [], "tasks": [],
                    "news": [], "speech_text": message, "read_only": True}

    def _previous_counts(self, date):
        with self._db() as db:
            row = db.execute("SELECT delta FROM runs WHERE date<? ORDER BY date DESC LIMIT 1",
                             (date,)).fetchone()
        if not row or not row["delta"]:
            return {}
        try:
            stored = json.loads(row["delta"])
        except ValueError:
            return {}
        return stored.get("today") or {}

    @staticmethod
    def _compose_text(date, live, items, tasks, news, delta, sources):
        lines = [f"Morning digest {date} (Asia/Kolkata). {live['triage']} attention items."]
        for item in items[:6]:
            label = item.get("title") or "(item)"
            lines.append(f"- [{item['priority'].upper()}] {label} ({item['kind']})")
        email_change = delta.get("email_change")
        if isinstance(email_change, int):
            lines.append(f"Email change since previous digest: {email_change:+d}.")
        if tasks:
            lines.append(f"Tasks pending: {len(tasks)}.")
        if news:
            lines.append(f"News headlines: {len(news['items'])} (opt-in feed).")
        unavailable = [f"{name}={value.get('state')}" for name, value in sources.items()
                       if value.get("state") in UNAVAILABLE_STATES]
        if unavailable:
            lines.append("Unavailable sources: " + ", ".join(unavailable) + ".")
        return "\n".join(lines)[:MAX_SPEECH]

    # -- acknowledgement and local speech --------------------------------
    def acknowledge(self, digest_id=None):
        """Record the explicit UI receipt of the digest notification."""
        digest_id = digest_id or ist_date(self.clock())
        with self._db() as db:
            row = db.execute("SELECT status FROM runs WHERE date=?", (digest_id,)).fetchone()
            if not row:
                raise DigestError("Digest not found for acknowledgement.")
            if row["status"] != "completed":
                raise DigestError("Only a completed digest can be acknowledged.")
            db.execute("UPDATE runs SET acknowledged=1,acknowledged_at=? WHERE date=?",
                       (self.clock(), digest_id))
        return {"acknowledged": True, "digest": digest_id, "at": self.clock()}

    def speech_payload(self, digest_id=None):
        """Return the bounded Windows-local TTS payload without speaking."""
        digest_id = digest_id or ist_date(self.clock())
        with self._db() as db:
            row = db.execute("SELECT text,status FROM runs WHERE date=?", (digest_id,)).fetchone()
        if not row:
            raise DigestError("Digest not found for speech.")
        if row["status"] != "completed":
            raise DigestError("Only a completed digest can be spoken.")
        command = ["powershell", "-NoProfile", "-Command",
                   "Add-Type -AssemblyName System.Speech; "
                   "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                   "$s.Speak('" + row["text"].replace("'", "''") + "'); $s.Dispose()"]
        return {"digest": digest_id, "command": command, "network_free": True,
                "engine": "Windows System.Speech"}

    def speak(self, digest_id=None, *, timeout=90):
        payload = self.speech_payload(digest_id)
        try:
            code = self.runner(payload["command"], timeout)
        except subprocess.TimeoutExpired:
            code = 1
        except OSError:
            code = 1
        with self._db() as db:
            db.execute("UPDATE runs SET speech=? WHERE date=?",
                       ("spoken" if code == 0 else "failed", payload["digest"]))
        return {"spoken": code == 0, "exit_code": code, "speech": "local Windows System.Speech",
                "digest": payload["digest"]}


def _speak_windows(command, timeout=90):
    return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                          timeout=timeout).returncode
