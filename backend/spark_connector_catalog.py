"""Capability 13 — Broad data connector catalog with per-source evidence.

Every connector — cloud or local — carries its own lifecycle state and its
own gates; nothing is inherited from a generic "connected" banner:

  disabled -> configured -> account_validated -> verified_read
           -> (stale | failed | revoked)

Rules encoded here:
* new connectors always import disabled;
* account validation, real reads with cursor pagination, freshness
  timestamps and revocation are individual measured adapter calls the
  owner attaches for each connector; a missing call is an honest refusal;
* reads are rate-limited per connector and never run twice concurrently;
* every result records the account identity (as a masked label), source
  timestamp and UTC read time so freshness can be judged later;
* all adapters are injected callables — tests use fixture ShapedPayload
  transports, live connectors reattach SPARK's existing consented readers.
"""
from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import time
from pathlib import Path

MAX_CONNECTORS = 16
MIN_READ_INTERVAL = 2.0
KEEP_EVENTS = 300

STATES = ("disabled", "configured", "account_validated",
          "verified_read", "stale", "failed", "revoked")


class ConnectorError(ValueError):
    """Invalid connector registration, validation or read."""


def _connector_id(name):
    if not isinstance(name, str) or not re.fullmatch(
            r"[a-z][a-z0-9_.-]{1,47}", str(name)):
        raise ConnectorError("Connector ids are short lowercase tokens.")
    return name


class ConnectorCatalog:
    def __init__(self, root, *, clock=time.time):
        self.root = Path(root) / "connector-catalog"
        self.clock = clock
        if self.root.is_symlink():
            raise ConnectorError("Linked connector storage is prohibited.")
        self.adapters = {}

    def _require(self, connector_id, required):
        adapter = self.adapters.get(connector_id)
        if adapter is None or adapter.get(required) is None:
            raise ConnectorError("Connector has no attached " + required
                                 + " adapter.")
        return adapter

    @contextlib.contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "connectors.sqlite3"
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS connectors("
                           "id TEXT PRIMARY KEY,provider TEXT,scope TEXT,"
                           "account TEXT,state TEXT,last_success REAL,"
                           "cursor_pos TEXT,last_error TEXT,created REAL)")
                db.execute("CREATE TABLE IF NOT EXISTS events("
                           "key TEXT PRIMARY KEY,connector TEXT,kind TEXT,"
                           "detail TEXT,created REAL)")
            yield db
            db.commit()
        finally:
            db.close()

    # -- registration ------------------------------------------------------
    def register(self, connector_id, provider, *, scope, validate_account=None,
                 read_page=None, revoke=None):
        """Register a connector; it starts disabled regardless of adapters."""
        _connector_id(connector_id)
        if not isinstance(provider, str) or not 1 <= len(provider) <= 60:
            raise ConnectorError("Provider name is a short string.")
        if not isinstance(scope, str) or not 1 <= len(scope) <= 200:
            raise ConnectorError("Declare the scope of this connector.")
        if not any((validate_account, read_page, revoke)):
            raise ConnectorError("Attach at least one measured adapter.")
        with self._db() as db:
            total = db.execute("SELECT COUNT(*) count FROM connectors"
                               ).fetchone()["count"]
            row = db.execute("SELECT state FROM connectors WHERE id=?",
                             (connector_id,)).fetchone()
            if row is None and total >= MAX_CONNECTORS:
                raise ConnectorError("Bounded catalog is full.")
            if row is None:
                db.execute("INSERT INTO connectors VALUES(?,?,?,?,?,?,?,?,?)",
                           (connector_id, provider, scope, "", "disabled",
                            None, None, None, self.clock()))
            else:
                db.execute("UPDATE connectors SET provider=?,scope=? "
                           "WHERE id=?", (provider, scope, connector_id))
        self.adapters[connector_id] = {
            "validate_account": validate_account, "read_page": read_page,
            "revoke": revoke}
        return {"id": connector_id, "state": self.state(connector_id)["state"],
                "note": "new connectors import disabled"}

    def list(self):
        with self._db() as db:
            rows = db.execute("SELECT * FROM connectors ORDER BY created "
                              "DESC").fetchall()
        return [self._public(row) for row in rows]

    def _public(self, row):
        public = dict(row)
        state = public["state"]
        public["note"] = {
            "disabled": "attach owner-approved account validation and a reader",
            "configured": "run account validation with the owner's consent",
            "account_validated": "perform one real bounded read to verify",
            "verified_read": "supported; freshness is the read timestamp",
            "stale": "older than the connector's freshness window",
            "failed": "connector failed; intervention recorded",
            "revoked": "revoked by the owner; reattachment needs new consent",
        }.get(state, state)
        return public

    # -- measured lifecycle ------------------------------------------------
    def _adapters(self, connector_id, required):
        adapter = self.adapters.get(connector_id)
        if adapter is None or adapter.get(required) is None:
            raise ConnectorError("Connector has no attached " + required
                                 + " adapter.")
        return adapter

    def state(self, connector_id):
        _connector_id(connector_id)
        with self._db() as db:
            row = db.execute("SELECT * FROM connectors WHERE id=?",
                             (connector_id,)).fetchone()
        if row is None:
            raise ConnectorError("Connector not found: " + connector_id)
        return self._public(row)

    def _transition(self, connector_id, state, **fields):
        with self._db() as db:
            updates = ["state=?"] + [key + "=?" for key in fields]
            values = [state, *fields.values(), connector_id]
            db.execute("UPDATE connectors SET " + ",".join(updates) +
                       " WHERE id=?", values)
            db.execute("DELETE FROM events WHERE connector=? AND kind=?",
                       (connector_id, ""))

    def _event(self, connector_id, kind, detail):
        key = "ev-" + str(int(self.clock() * 1_000_000)) + kind
        with self._db() as db:
            db.execute("INSERT INTO events VALUES(?,?,?,?,?)",
                       (key, connector_id, kind, detail[:600], self.clock()))
            db.execute("DELETE FROM events WHERE key NOT IN (SELECT key FROM "
                       "events ORDER BY created DESC LIMIT ?)", (KEEP_EVENTS,))

    def configure(self, connector_id, account, *, consented):
        """Owner consent attaches an account identity label (not a token)."""
        if consented is not True:
            raise ConnectorError("Configure requires explicit owner consent.")
        if not isinstance(account, str) or not 1 <= len(account) <= 120:
            raise ConnectorError("Account identity is a bounded label.")
        self._require(connector_id, "validate_account")  # presence check only
        row_state = self.state(connector_id)["state"]
        if row_state == "revoked":
            raise ConnectorError("A revoked connector needs a fresh owner "
                                 "consent record before reconfiguration.")
        self._transition(connector_id, "configured", account=account)
        self._event(connector_id, "configured",
                    "account " + account[:3] + "***")
        return self.state(connector_id)

    def _cursor_get(self, connector_id):
        with self._db() as db:
            row = db.execute("SELECT cursor_pos FROM connectors WHERE id=?",
                             (connector_id,)).fetchone()
        return row["cursor_pos"] if row else None

    def validate_account(self, connector_id):
        adapter = self._require(connector_id, "validate_account")
        row_state = self.state(connector_id)["state"]
        if row_state not in ("configured", "account_validated"):
            raise ConnectorError("Configure the connector with owner consent "
                                 "before validating its account.")
        try:
            identity = adapter["validate_account"]()
        except Exception as error:
            self._event(connector_id, "account_validation_failed",
                        type(error).__name__)
            self._transition(connector_id, "failed",
                             last_error=type(error).__name__)
            raise ConnectorError("Account validation failed: "
                                 + type(error).__name__) from None
        account = str(identity or "")[:120]
        if not account:
            self._transition(connector_id, "failed",
                             last_error="empty identity")
            raise ConnectorError("Account adapter returned no identity.")
        self._transition(connector_id, "account_validated", account=account)
        self._event(connector_id, "account_validated",
                    "identity length-only label stored")
        return self.state(connector_id)

    def read_page(self, connector_id, *, limit=20):
        adapter = self._require(connector_id, "read_page")
        row = self.state(connector_id)
        if row["state"] not in ("account_validated", "verified_read", "stale"):
            raise ConnectorError("Connector is not ready to read; validate the "
                                 "account first.")
        now = self.clock()
        last = row.get("last_success") or 0
        if now - last < MIN_READ_INTERVAL:
            raise ConnectorError("Rate limit: one read per %s seconds."
                                 % MIN_READ_INTERVAL)
        cursor = self._cursor_get(connector_id)
        try:
            result = adapter["read_page"](cursor, limit)
        except Exception as error:
            self._transition(connector_id, "failed",
                             last_error=type(error).__name__)
            self._event(connector_id, "read_failed", type(error).__name__)
            raise ConnectorError("Connector read failed: "
                                 + type(error).__name__) from None
        if not isinstance(result, dict) or set(result) - {"items", "cursor",
                                                          "source_time"}:
            raise ConnectorError("Reader must return items, cursor and an "
                                 "optional source timestamp.")
        items = result.get("items")
        if not isinstance(items, list) or len(items) > limit:
            raise ConnectorError("Reader returned invalid page items.")
        cursor_pos = result.get("cursor")
        if cursor_pos is not None and not isinstance(cursor_pos, str):
            raise ConnectorError("Cursor must be a bounded string or null.")
        source_time = result.get("source_time")
        if source_time is not None and not isinstance(source_time, (int, float)):
            raise ConnectorError("Source time must be numeric.")
        self._transition(connector_id, "verified_read", last_success=now,
                         cursor_pos=cursor_pos)
        self._event(connector_id, "verified_read",
                    "items=%d cursor=%s" % (len(items), cursor_pos))
        state = self.state(connector_id)
        state["items"] = items
        return state

    def freshness(self, connector_id, *, stale_after_seconds):
        """Judge freshness from the recorded read/success timestamps."""
        if type(stale_after_seconds) not in (int, float) or stale_after_seconds <= 0:
            raise ConnectorError("Provide a positive freshness window.")
        state = self.state(connector_id)
        last = state.get("last_success") or 0
        if not last:
            return {"id": connector_id, "state": state["state"],
                    "freshness": "no successful read yet"}
        age = self.clock() - last
        fresh = age <= stale_after_seconds
        if not fresh and state["state"] == "verified_read":
            self._transition(connector_id, "stale")
            state = self.state(connector_id)
        return {"id": connector_id, "state": state["state"],
                "age_seconds": round(age, 1), "freshness": "fresh" if fresh
                else "stale"}

    def revoke(self, connector_id, *, approved_by):
        """Owner-only revocation clears the stored account identity."""
        if not approved_by or len(str(approved_by)) < 3:
            raise ConnectorError("Revocation requires an approving owner.")
        adapter = self._require(connector_id, "revoke")
        revoker = adapter["revoke"]
        if revoker is not None:
            try:
                revoker()
            except Exception as error:
                self._event(connector_id, "revoke_remote_failed",
                            type(error).__name__)
        self._transition(connector_id, "revoked", account="")
        self._event(connector_id, "revoked",
                    "revoked by " + str(approved_by)[:60])
        return self.state(connector_id)

    def events(self, connector_id=None, *, limit=50):
        with self._db() as db:
            if connector_id:
                rows = db.execute("SELECT * FROM events WHERE connector=? "
                                  "ORDER BY created DESC LIMIT ?",
                                  (connector_id, int(limit))).fetchall()
            else:
                rows = db.execute("SELECT * FROM events ORDER BY created DESC "
                                  "LIMIT ?", (int(limit),)).fetchall()
        return [dict(row) for row in rows]

    def status(self):
        with self._db() as db:
            rows = db.execute("SELECT state,COUNT(*) count FROM connectors "
                              "GROUP BY state").fetchall()
        return {"by_state": {row["state"]: row["count"] for row in rows},
                "states": list(STATES),
                "rate_limit_seconds": MIN_READ_INTERVAL,
                "adapters_attached": sorted(self.adapters)}
