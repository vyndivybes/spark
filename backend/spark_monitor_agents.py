"""Capability 11 — Long-running monitor agents with checkpoints.

Each monitor is a small registered check function (bounded, scoped to one
source) that SPARK can revisit on a schedule. State is persisted locally so
that monitors resume after a restart, duplicate events are never re-raised,
failures back off exponentially, notifications require an owner receipt, and
cancellation is durable. Memory is compacted to a bounded number of events.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

DEFAULT_INTERVAL = 900
MAX_BACKOFF = 6 * 3600
KEEP_EVENTS = 200
MAX_EVENTS_PER_RUN = 50


class MonitorError(ValueError):
    """Invalid monitor registration, schedule or event handling."""


class MonitorAgents:
    def __init__(self, root, *, clock=time.time):
        self.root = Path(root) / "monitors"
        self.clock = clock
        self.checks = {}   # monitor name -> callable() -> list of events
        if self.root.is_symlink():
            raise MonitorError("Linked monitor storage is prohibited.")

    @contextlib.contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "monitors.sqlite3"
        if path.is_symlink():
            raise MonitorError("Linked monitor storage is prohibited.")
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS checkpoints("
                           "name TEXT PRIMARY KEY,scope TEXT,interval INTEGER,"
                           "last_run REAL,last_success REAL,next_due REAL,"
                           "failures INTEGER DEFAULT 0,cancelled INTEGER DEFAULT 0,"
                           "cursor TEXT)")
                db.execute("CREATE TABLE IF NOT EXISTS events("
                           "key TEXT PRIMARY KEY,name TEXT,kind TEXT,"
                           "payload TEXT,created REAL,state TEXT NOT NULL)")
                db.execute("CREATE TABLE IF NOT EXISTS notifications("
                           "key TEXT PRIMARY KEY,created REAL,"
                           "notified INTEGER DEFAULT 0,acknowledged REAL)")
            yield db
            db.commit()
        finally:
            db.close()

    # -- registration -----------------------------------------------------
    def register(self, name, scope, check, *, interval=DEFAULT_INTERVAL):
        if not re.fullmatch(r"[a-z0-9_-]{2,40}", str(name)):
            raise MonitorError("Monitor names must be short lowercase tokens.")
        if not str(scope):
            raise MonitorError("Every monitor declares its scoped source.")
        if not callable(check):
            raise MonitorError("A monitor needs a callable check.")
        if type(interval) is not int or not 60 <= interval <= 6 * 3600:
            raise MonitorError("Choose a monitor interval between 60s and 6h.")
        self.checks[name] = {"check": check, "scope": scope}
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO checkpoints VALUES(?,?,?,?,?,?,?,?,?)",
                       (name, scope, interval, None, None, self.clock(), 0, 0, None))
        return {"registered": True, "monitor": name, "scope": scope,
                "interval": interval}

    def cancel(self, name):
        if name not in self.checks:
            raise MonitorError("Unknown monitor: " + str(name))
        with self._db() as db:
            db.execute("UPDATE checkpoints SET cancelled=1 WHERE name=?", (name,))
        return {"monitor": name, "cancelled": True}

    def _checkpoint(self, db, name):
        row = db.execute("SELECT * FROM checkpoints WHERE name=?", (name,)).fetchone()
        if not row:
            raise MonitorError("Monitor is not registered: " + str(name))
        return row

    # -- execution ---------------------------------------------------------
    def run_once(self, name, *, force=False):
        """One bounded, idempotent monitor cycle; backoff on failures."""
        check = self.checks.get(name)
        if not check:
            raise MonitorError("Unknown monitor: " + str(name))
        now = self.clock()
        with self._db() as db:
            row = self._checkpoint(db, name)
            if row["cancelled"]:
                return {"monitor": name, "state": "cancelled", "events": 0}
            if not force and now < row["next_due"]:
                return {"monitor": name, "state": "waiting",
                        "next_due": row["next_due"], "events": 0}
            interval = row["interval"]
            failures = int(row["failures"] or 0)
            try:
                events = check["check"]()  # Never receives unapproved context.
            except Exception as error:
                failures = min(failures + 1, 30)
                backoff = min(MAX_BACKOFF, interval * (2 ** failures))
                db.execute("UPDATE checkpoints SET last_run=?,failures=?,next_due=? "
                           "WHERE name=?", (now, failures, now + backoff, name))
                return {"monitor": name, "state": "failed",
                        "error": str(error)[:200], "failures": failures,
                        "next_due": now + backoff, "events": 0}
            if not isinstance(events, (list, tuple)):
                events = []
            fresh = 0
            for event in list(events)[:MAX_EVENTS_PER_RUN]:
                if not isinstance(event, dict) or "kind" not in event:
                    continue
                key = name + "|" + hashlib.sha256(json.dumps(
                    {k: event.get(k) for k in sorted(event)},
                    ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()[:16]
                exists = db.execute("SELECT 1 FROM events WHERE key=?",
                                    (key,)).fetchone()
                if exists:
                    continue  # Duplicate events are never raised twice.
                db.execute("INSERT OR REPLACE INTO events VALUES(?,?,?,?,?,?)",
                           (key, name, str(event["kind"])[:60],
                            json.dumps(event, ensure_ascii=False, default=str), now,
                            "new"))
                db.execute("INSERT OR REPLACE INTO notifications VALUES(?,?,0,NULL)",
                           (key, now))
                fresh += 1
            cursor = json.dumps({"count": fresh}, sort_keys=True)
            db.execute("UPDATE checkpoints SET last_run=?,last_success=?,next_due=?,"
                       "failures=0,cursor=? WHERE name=?",
                       (now, now, now + interval, cursor, name))
        return {"monitor": name, "state": "completed", "events": fresh,
                "next_due": now + interval}

    # -- notifications and memory -------------------------------------------
    def pending_notifications(self, *, limit=50):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise MonitorError("Request between 1 and 200 notifications.")
        with self._db() as db:
            rows = db.execute("SELECT n.key,n.created,n.notified,n.acknowledged,"
                              "e.name,e.kind,e.payload FROM notifications n "
                              "JOIN events e ON e.key=n.key "
                              "WHERE n.notified=1 AND n.acknowledged IS NULL "
                              "ORDER BY n.created DESC LIMIT ?", (limit,)).fetchall()
        return {"notifications": [dict(row) for row in rows],
                "count": len(rows)}

    def deliver(self, name, callback):
        """Deliver new events to the owner's channel; recorded with receipts."""
        check = self.checks.get(name)
        if not check:
            raise MonitorError("Unknown monitor: " + str(name))
        delivered = 0
        with self._db() as db:
            rows = db.execute("SELECT n.key,n.created FROM notifications n "
                              "WHERE n.notified=0 AND n.acknowledged IS NULL "
                              "ORDER BY n.created LIMIT 50").fetchall()
        for row in rows:
            try:
                callback(row["key"])
            except Exception:
                continue  # Delivery failure keeps the event queued for retry.
            with self._db() as db:
                db.execute("UPDATE notifications SET notified=1 WHERE key=?",
                           (row["key"],))
            delivered += 1
        return {"monitor": name, "delivered": delivered}

    def acknowledge(self, key):
        if not isinstance(key, str) or len(key) > 120:
            raise MonitorError("Invalid notification key.")
        with self._db() as db:
            row = db.execute("SELECT notified FROM notifications WHERE key=?",
                             (key,)).fetchone()
            if not row:
                raise MonitorError("Notification not found.")
            db.execute("UPDATE notifications SET acknowledged=? WHERE key=?",
                       (self.clock(), key))
        return {"acknowledged": True, "key": key}

    def compact(self):
        """Bound monitor memory without dropping unacknowledged state."""
        with self._db() as db:
            deletable = db.execute(
                "SELECT key FROM events ORDER BY created DESC LIMIT -1 OFFSET ?",
                (KEEP_EVENTS,)).fetchall()
            removed = 0
            for row in deletable:
                waiting = db.execute(
                    "SELECT 1 FROM notifications WHERE key=? AND acknowledged IS NULL",
                    (row["key"],)).fetchone()
                if not waiting:
                    db.execute("DELETE FROM events WHERE key=?", (row["key"],))
                    removed += 1
        return {"compacted": True, "removed_events": removed,
                "policy": f"keep at most {KEEP_EVENTS} events, none unacknowledged"}

    # -- status --------------------------------------------------------------
    def status(self):
        with self._db() as db:
            rows = [dict(row) for row in
                    db.execute("SELECT name,scope,interval,last_run,last_success,"
                               "next_due,failures,cancelled FROM checkpoints")]
        out = []
        for row in rows:
            row["cancelled"] = bool(row["cancelled"])
            row["state"] = ("cancelled" if row["cancelled"] else
                            "failed" if row["failures"] else
                            "configured, untested" if row["last_success"] is None
                            else "healthy")
            out.append(row)
        return {"schema": "spark.monitor_agents.v1", "monitors": out,
                "checks": sorted(self.checks),
                "policy": ("scoped check callbacks only; deduplicated events; "
                           "exponential backoff; owner receipts; resume via "
                           "persisted checkpoints before and after restart")}
