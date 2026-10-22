"""Capability 03 — Proactive agent with policy tiers and durable approvals.

Collects *proposals* (suggested next actions) from SPARK's own read-only
sources, deduplicates them, and executes only what the owner approved or a
permission pattern the owner explicitly remembered allows. Tiers:

* ``read_only``   — safe inspections; may run without approval but are queued and audited.
* ``suggest``     — needs an exact approval unless the owner remembered a
  prior yes for the exact permission pattern.
* ``restricted``  — device writes, business records, shell, installs; never
  self-executed, even with a remembered choice.

Actions are reversible only when an undo handler is registered; otherwise
execution is refused. Source identity travels with every action so one
source's privileges can never be reused elsewhere. State survives restarts.
"""
from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import time
from pathlib import Path

TIERS = ("read_only", "suggest", "restricted")
DEDUPE_WINDOW = 6 * 3600
MAX_TEXT = 500


class ProactiveError(ValueError):
    """Invalid proposal, approval or execution request."""


def _safe_text(value, limit=MAX_TEXT):
    if not isinstance(value, str) or not value.strip():
        raise ProactiveError("Text must be a non-empty string.")
    return value.strip()[:limit]


class Proposal:
    """One candidate action; tier and source identity are mandatory."""

    def __init__(self, source, kind, tier, detail, *, dedupe_key=None):
        if source not in ("gmail", "google-calendar", "google-drive", "obsidian-vault",
                          "slack", "github", "camera", "workbench", "system"):
            raise ProactiveError("Proposals must name a real SPARK source.")
        if str(tier) not in TIERS:
            raise ProactiveError("Tier must be one of: " + ", ".join(TIERS))
        if not isinstance(kind, str) or not 3 <= len(str(kind)) <= 60 or \
                not re.fullmatch(r"[a-z0-9_.-]+", str(kind)):
            raise ProactiveError("Action kind must be a short token.")
        self.source = source
        self.kind = kind
        self.tier = tier
        self.detail = _safe_text(detail)
        self.dedupe_key = dedupe_key or f"{source}/{kind}/{hashlib_fingerprint(self.detail)}"


def hashlib_fingerprint(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]


class ProactiveAgent:
    """Persisted proposal inbox with approvals and reversible execution."""

    def __init__(self, root, *, clock=time.time, executors=None):
        self.root = Path(root) / "proactive"
        self.clock = clock
        self.executors = executors or {}     # action kind -> callable(detail)
        self.undos = {}                      # reversible action kind -> callable
        if self.root.is_symlink():
            raise ProactiveError("Linked proactive storage is prohibited.")

    @contextlib.contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "actions.sqlite3"
        if path.is_symlink():
            raise ProactiveError("Linked proactive storage is prohibited.")
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS proposals("
                           "dedupe_key TEXT PRIMARY KEY,source TEXT,tier TEXT,"
                           "kind TEXT,detail TEXT,created REAL,"
                           "state TEXT NOT NULL,decision_by TEXT,"
                           "decided_at REAL,executed_payload TEXT,"
                           "result TEXT,error TEXT,reversible INTEGER,"
                           "undo_state TEXT)")
                db.execute("CREATE TABLE IF NOT EXISTS choices("
                           "pattern TEXT PRIMARY KEY,decision TEXT,updated REAL,"
                           "times_used INTEGER DEFAULT 0)")
                db.execute("CREATE TABLE IF NOT EXISTS summary("
                           "day TEXT PRIMARY KEY,proposed INTEGER,approved INTEGER,"
                           "executed INTEGER,denied INTEGER,failed INTEGER,"
                           "updated REAL)")
            yield db
            db.commit()
        finally:
            db.close()

    # -- inbox -------------------------------------------------------------
    def propose(self, proposal):
        """Queue a proposal; duplicates within the window are ignored."""
        if not isinstance(proposal, Proposal):
            raise ProactiveError("Queue a real Proposal object.")
        now = self.clock()
        with self._db() as db:
            row = db.execute("SELECT created,state FROM proposals WHERE dedupe_key=?",
                             (proposal.dedupe_key,)).fetchone()
            if row and now - row["created"] < DEDUPE_WINDOW:
                return {"queued": False, "reason": "already proposed recently",
                        "dedupe_key": proposal.dedupe_key, "state": row["state"]}
            if proposal.tier == "restricted":
                pass  # Restricted actions are queued for a human, never executed.
            elif proposal.tier == "suggest":
                registered = self._registration(proposal.kind)
                if not registered:
                    raise ProactiveError("No executor is registered for this action kind.")
                if registered["source"] != proposal.source:
                    raise ProactiveError("Executor and proposal sources disagree; "
                                         "privilege cannot cross sources.")
                if not registered.get("undo"):
                    raise ProactiveError("Suggested actions must be reversible; "
                                         "register an undo handler first.")
            reversible = bool(self._registration(proposal.kind)
                              and self._registration(proposal.kind).get("undo"))
            db.execute("INSERT OR REPLACE INTO proposals VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL,?,NULL)",
                       (proposal.dedupe_key, proposal.source, proposal.tier,
                        proposal.kind, proposal.detail, now, "proposed",
                        1 if reversible else 0))
            self._bump_summary(db, "proposed")
        return {"queued": True, "dedupe_key": proposal.dedupe_key,
                "tier": proposal.tier, "source": proposal.source,
                "state": "proposed"}

    def inbox(self, *, state=None, limit=50):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ProactiveError("Request between 1 and 200 inbox entries.")
        with self._db() as db:
            if state:
                rows = db.execute("SELECT * FROM proposals WHERE state=? "
                                  "ORDER BY created DESC LIMIT ?", (state, limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM proposals ORDER BY created DESC "
                                  "LIMIT ?", (limit,)).fetchall()
        return {"proposals": [dict(row) for row in rows], "count": len(rows)}

    def register_executor(self, kind, source, run, undo=None):
        """Bind an action kind to ONE source; undo makes it reversible."""
        existing = self.executors.get(kind)
        if existing and existing["source"] != source:
            raise ProactiveError("An executor for this kind already belongs to "
                                 "another source.")
        self.executors[kind] = {"kind": kind, "source": source, "run": run,
                                "undo": undo}

    def _registration(self, kind):
        return self.executors.get(kind)

    # -- decisions ---------------------------------------------------------
    def decide(self, dedupe_key, *, approved, by="owner", remember=False):
        """Record an exact approval or denial for one proposal."""
        if type(approved) is not bool:
            raise ProactiveError("Approval must be a boolean.")
        now = self.clock()
        with self._db() as db:
            row = db.execute("SELECT tier,kind,state,source FROM proposals WHERE dedupe_key=?",
                             (dedupe_key,)).fetchone()
            if not row:
                raise ProactiveError("Proposal not found.")
            if row["state"] != "proposed":
                raise ProactiveError("Proposal already has a final decision.")
            state = "approved" if approved else "denied"
            db.execute("UPDATE proposals SET state=?,decision_by=?,decided_at=? WHERE dedupe_key=?",
                       (state, by, now, dedupe_key))
            self._bump_summary(db, "approved" if approved else "denied")
            if remember and row["tier"] in ("read_only", "suggest") and approved:
                # The permission pattern includes the source, so a remembered
                # yes can never authorize the same action from another source.
                pattern = f"{row['source']}/{row['kind']}"
                db.execute("INSERT OR REPLACE INTO choices VALUES(?,?,?,0)",
                           (pattern, "remembered_yes", now))
        return {"dedupe_key": dedupe_key, "state": state, "remembered": remember
                and approved}

    def remembered(self, source, kind):
        if not isinstance(source, str) or not isinstance(kind, str):
            raise ProactiveError("Look up a remembered choice with real strings.")
        with self._db() as db:
            row = db.execute("SELECT decision FROM choices WHERE pattern=?",
                             (f"{source}/{kind}",)).fetchone()
        if row and row["decision"] == "remembered_yes":
            return True
        return False

    # -- execution ----------------------------------------------------------
    def execute(self, dedupe_key):
        """Run an approved proposal through its registered, bounded handler."""
        with self._db() as db:
            row = db.execute("SELECT * FROM proposals WHERE dedupe_key=?",
                             (dedupe_key,)).fetchone()
        if not row:
            raise ProactiveError("Proposal not found.")
        if row["tier"] == "restricted":
            raise ProactiveError("Restricted actions are never self-executed; "
                                 "a human must perform them.")
        approved = row["state"] == "approved"
        registered = self._registration(row["kind"])
        if not registered or registered["source"] != row["source"]:
            raise ProactiveError("No executor is registered for this action kind "
                                 "on its source.")
        if row["tier"] == "read_only":
            auto = True   # Visible, safe inspections may run without approval.
        else:
            auto = self.remembered(row["source"], row["kind"])
        if not approved and not auto:
            raise ProactiveError("This action needs an explicit approval first.")
        try:
            payload = registered["run"](row["detail"])
            with self._db() as db:
                db.execute("UPDATE proposals SET state='executed',executed_payload=?,result=NULL "
                           "WHERE dedupe_key=?",
                           (json.dumps(payload, ensure_ascii=False, default=str), dedupe_key))
                self._bump_summary(db, "executed")
            self._remember_use(row["source"], row["kind"])
            return {"executed": True, "dedupe_key": dedupe_key,
                    "result": payload, "reversible": bool(row["reversible"])}
        except ProactiveError:
            raise
        except Exception as error:
            with self._db() as db:
                db.execute("UPDATE proposals SET state='failed',error=?,result=? "
                           "WHERE dedupe_key=?", (str(error)[:200], None, dedupe_key))
                self._bump_summary(db, "failed")
            return {"executed": False, "dedupe_key": dedupe_key,
                    "error": str(error)[:200]}

    def _remember_use(self, source, kind):
        with self._db() as db:
            db.execute("UPDATE choices SET times_used=times_used+1 WHERE pattern=?",
                       (f"{source}/{kind}",))

    def undo(self, dedupe_key):
        """Reverse the last executed result through the registered handler."""
        with self._db() as db:
            row = db.execute("SELECT kind,reversible,executed_payload,source,state FROM "
                             "proposals WHERE dedupe_key=?", (dedupe_key,)).fetchone()
        if not row or row["state"] != "executed":
            raise ProactiveError("Only an executed action can be undone.")
        if not row["reversible"]:
            raise ProactiveError("This action has no registered undo; it is "
                                 "not reversible.")
        registered = self._registration(row["kind"])
        if not registered or not registered["undo"] \
                or registered["source"] != row["source"]:
            raise ProactiveError("No matching reversible handler is registered.")
        payload = json.loads(row["executed_payload"] or "null")
        try:
            registered["undo"](payload)
        except Exception as error:
            raise ProactiveError("Undo failed: " + str(error)[:150]) from None
        with self._db() as db:
            db.execute("UPDATE proposals SET state='undone',undo_state=? WHERE dedupe_key=?",
                       (self.clock(), dedupe_key))
        return {"undone": True, "dedupe_key": dedupe_key}

    # -- summaries ----------------------------------------------------------
    def daily_summary(self, day=None):
        day = day or time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
        with self._db() as db:
            row = db.execute("SELECT proposed,approved,executed,denied,failed "
                             "FROM summary WHERE day=?", (day,)).fetchone()
        counts = dict(row) if row else {"proposed": 0, "approved": 0, "executed": 0,
                                        "denied": 0, "failed": 0}
        counts["day"] = day
        return counts

    def _bump_summary(self, db, column):
        day = time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
        db.execute("INSERT INTO summary(day,proposed,approved,executed,denied,failed,updated) "
                   "VALUES(?,0,0,0,0,0,?) ON CONFLICT(day) DO NOTHING", (day, self.clock()))
        db.execute(f"UPDATE summary SET {column}={column}+1,updated=? WHERE day=?",
                   (self.clock(), day))
        db.execute("DELETE FROM summary WHERE updated < ?", (self.clock() - 30 * 86400,))


def locally_jsonless(payload):
    """JSON-friendly pass-through retained for external callers."""
    return payload if payload is None else str(payload)
