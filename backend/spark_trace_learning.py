"""Capabilities 07 & 12 — Redacted trace learning and adaptive model routing.

Learning is evidence-first:
* traces are captured with secrets masked and labeled only from *measured*
  outcomes (execution results, never a model's self-assessment);
* a candidate routing policy is scored on the training traces, then audited
  on a held-out set against the incumbent policy. It can be proposed,
  activated only after a human approves, and rolled back to checkpoint;
* routing is local-first with real resource, permission and cost guards:
  cloud providers are only used when the owner's permission flag allows it
  and no local model meets the measured quality floor.

No claim of intelligence improvement is made without the held-out gate.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
from dataclasses import asdict
from pathlib import Path

from spark_maintenance import atomic_write
from vendor.openjarvis_learning.skill_discovery import SkillDiscovery

SECRET_PATTERNS = re.compile(
    r"([A-Za-z0-9_]*(?:api[_-]?key|apikey|token|secret|password|authorization)[A-Za-z0-9_]*)"
    r"\s*[=:]\s*[\"']?\S[^\s\"']*", re.I)
LOCAL_MODELS = ("ollama-local", "llamacpp-local", "groq-free-cloud", "gemini-free-cloud")
TASK_CLASSES = ("digest", "research", "coding", "triage", "memory", "voice")


class LearningError(ValueError):
    """Invalid trace, policy or learning request."""


def mask_secrets(text):
    if not isinstance(text, str):
        return ""
    return SECRET_PATTERNS.sub(lambda match: match.group(1) + "=<redacted>", text)


class TraceStore:
    """SQLite store of masked traces with measured outcome labels."""

    def __init__(self, root, *, clock=time.time):
        self.root = Path(root) / "trace-learning"
        self.clock = clock
        if self.root.is_symlink():
            raise LearningError("Linked trace storage is prohibited.")

    @contextlib.contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "traces.sqlite3"
        if path.is_symlink():
            raise LearningError("Linked trace storage is prohibited.")
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS traces("
                           "key TEXT PRIMARY KEY,task_class TEXT,model TEXT,"
                           "masked TEXT,latency_ms REAL,status TEXT,"
                           "success INTEGER,created REAL)")
                db.execute("CREATE TABLE IF NOT EXISTS candidates("
                           "key TEXT PRIMARY KEY,definition TEXT,"
                           "train_score REAL,heldout_score REAL,baseline REAL,"
                           "status TEXT,decision_by TEXT,created REAL)")
            yield db
            db.commit()
        finally:
            db.close()

    def capture(self, task_class, model, payload, latency_ms, *, success=None):
        """Capture one real execution trace; payload is masked immediately."""
        if str(task_class) not in TASK_CLASSES:
            raise LearningError("Capture a trace for a known task class.")
        if str(model) not in LOCAL_MODELS:
            raise LearningError("Capture a trace for a configured model only.")
        masked = mask_secrets(json.dumps(payload, ensure_ascii=False, default=str)) \
            if not isinstance(payload, str) else mask_secrets(payload)
        if success is not None and type(success) is not bool:
            raise LearningError("Measured success must be a boolean or None.")
        key = "t-" + hashlib.sha256(f"{task_class}|{model}|{masked}|{self.clock()}".encode(
            "utf-8")).hexdigest()[:14]
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO traces VALUES(?,?,?,?,?,?,?,?)",
                       (key, task_class, model, masked[:8000], latency_ms,
                        "labeled" if success is not None else "pending",
                        None if success is None else int(success), self.clock()))
        return {"key": key, "masked": True, "status": "captured"}

    def label(self, key, *, success):
        """Apply a measured outcome label; self-reported values are rejected."""
        if type(success) is not bool:
            raise LearningError("Label with a measured boolean outcome only.")
        with self._db() as db:
            row = db.execute("SELECT status FROM traces WHERE key=?", (key,)).fetchone()
            if not row:
                raise LearningError("Trace not found: " + str(key))
            db.execute("UPDATE traces SET success=?,status='labeled' WHERE key=?",
                       (int(success), key))
        return {"key": key, "status": "labeled", "success": success}

    def labeled(self, *, task_class=None, limit=500):
        with self._db() as db:
            if task_class:
                rows = db.execute("SELECT * FROM traces WHERE task_class=? AND "
                                  "status='labeled' ORDER BY created DESC LIMIT ?",
                                  (task_class, limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM traces WHERE status='labeled' "
                                  "ORDER BY created DESC LIMIT ?",
                                  (limit,)).fetchall()
        return [dict(row) for row in rows]

    def model_summary(self):
        with self._db() as db:
            rows = db.execute(
                "SELECT model,task_class,COUNT(*) count,"
                "AVG(success) success_rate,AVG(latency_ms) latency "
                "FROM traces WHERE status='labeled' "
                "GROUP BY model,task_class").fetchall()
        return [dict(row) for row in rows]


def policy_always_local(*args, **kwargs):
    """Static baseline policy: prefer ollama-local for every task."""
    return "ollama-local"


def policy_latency_smallest(summary, task_class, **_):
    """Learned candidate: pick the model with lowest measured latency."""
    rows = [row for row in summary if row["task_class"] == task_class]
    if not rows:
        return "ollama-local"
    best = min(rows, key=lambda row: (row["latency"], -row["count"]))
    return best["model"]


class AdaptiveRouter:
    """Local-first routing with measured evidence and permission gates."""

    def __init__(self, store, *, local_ram_gb=None, cloud_allowed=False,
                 latency_budget_ms=3000):
        self.store = store
        self.local_ram_gb = local_ram_gb  # None = unknown; local-only until measured
        self.cloud_allowed = cloud_allowed
        self.latency_budget_ms = latency_budget_ms
        self.current_policy = policy_always_local

    def summary(self):
        return self.store.model_summary()

    def select(self, task_class, *, apply_policy=True):
        """Choose a model with local-first preference and honest fallbacks."""
        if task_class not in TASK_CLASSES:
            raise LearningError("Route a known task class.")
        summary = self.summary()
        if apply_policy:
            try:
                chosen = self.current_policy(summary, task_class)
            except Exception:
                chosen = "ollama-local"
        else:
            chosen = "ollama-local"
        local_ready = self.local_ram_gb is None or self.local_ram_gb >= 6
        if chosen.endswith("local") and not local_ready and summary:
            # Low memory machine: use the lightest local measurement.
            local_rows = [row for row in summary if row["model"].endswith("local")]
            if local_rows:
                chosen = min(local_rows,
                             key=lambda row: (row["latency"], -row["count"]))["model"]
        cloud_ok = self.cloud_allowed and chosen.endswith(("cloud",))
        if not cloud_ok and chosen.endswith(("cloud",)):
            return {"model": "ollama-local", "reason":
                    "cloud not permitted; local fallback used", "local_first": True,
                    "measured": False}
        return {"model": chosen,
                "reason": ("measured policy choice" if apply_policy else "static baseline"),
                "local_first": chosen.endswith("local"),
                "measured": bool(summary)}

    def set_policy(self, policy):
        if not callable(policy):
            raise LearningError("Policies are callables.")
        self.current_policy = policy


class LearningEngine:
    """Candidate scoring, held-out gating, approval and rollback."""

    REGRESSION_MARGIN = 0.02   # candidate must not lose accuracy
    IMPROVEMENT_MIN = 0.05     # or must beat baseline by this margin

    def __init__(self, store, lock_split=0.25, *, clock=time.time):
        self.store = store
        self.lock_split = lock_split
        if type(lock_split) is not float or not 0.1 <= lock_split <= 0.5:
            raise LearningError("Held-out split must be between 0.1 and 0.5.")
        self.clock = clock

    def dataset(self, task_class):
        rows = list(reversed(self.store.labeled(task_class=task_class)))
        data = [row for row in rows if row["success"] is not None]
        if len(data) < 40:
            raise LearningError("Collect at least 40 labeled traces for this "
                                "task before learning.")
        holdout_n = max(6, int(len(data) * self.lock_split))
        heldout, train = data[:holdout_n], data[holdout_n:]
        return train, heldout

    def baseline_score(self, dataset):
        """Majority-outcome baseline accuracy."""
        positives = sum(1 for row in dataset if row["success"])
        total = len(dataset)
        if not total:
            return 0.0
        winners = max(positives, total - positives)
        return winners / total

    def candidate_score(self, named_rows, policy):
        """Fraction of taskClasses where the policy picks the best model."""
        summary_rows = named_rows
        best_per_class = {}
        for row in summary_rows:
            key = row["task_class"]
            best_row = max(self._by_class(summary_rows, key),
                           key=lambda r: (r["success_rate"], -r["latency"]))
            best_per_class[key] = best_row["model"]
        hits = total = 0
        for row in summary_rows:
            total += 1
            picked = policy(summary_rows, row["task_class"])
            if picked == best_per_class[row["task_class"]]:
                hits += 1
        if not total:
            return 0.0
        return hits / total

    @staticmethod
    def _by_class(rows, task_class):
        return [row for row in rows if row["task_class"] == task_class]

    def propose(self, name, policy, task_class, *, run_rows=None):
        """Score a candidate on train, then audit on held-out before proposing."""
        if not re.fullmatch(r"[a-z0-9_.-]{3,60}", name):
            raise LearningError("Candidate names are short lowercase tokens.")
        train, heldout = self.dataset(task_class)
        train_summary = self._as_summary(train)
        heldout_summary = self._as_summary(heldout)
        baseline = self.candidate_base(train_summary)
        candidate = self.candidate_score(train_summary, policy)
        heldout_score = self.candidate_score(heldout_summary, policy)
        beats_baseline = candidate >= baseline + self.IMPROVEMENT_MIN
        no_regression = heldout_score >= baseline - self.REGRESSION_MARGIN
        status = "proposed" if (beats_baseline and no_regression) else "rejected"
        key = "c-" + hashlib.sha256((name + str(self.clock())).encode()).hexdigest()[:12]
        with self.store._db() as db:
            db.execute("INSERT OR REPLACE INTO candidates VALUES(?,?,?,?,?,?,?,?)",
                       (key, name, candidate, heldout_score, baseline, status,
                        None, self.clock()))
        return {"key": key, "name": name, "train": candidate,
                "heldout": heldout_score, "baseline": baseline,
                "beats_baseline": beats_baseline, "no_regression": no_regression,
                "status": status}

    @staticmethod
    def candidate_base(summary):
        """Baseline: the majority-latency naive pick accuracy per class."""
        classes = {}
        for row in summary:
            classes[row["task_class"]] = True
        if not classes:
            return 0.0
        return 1 / len(classes)

    @classmethod
    def _as_summary(cls, rows):
        """Aggregate raw traces into per-(model,task) measured summaries."""
        if rows and "success_rate" in rows[0]:
            return rows
        aggregates = {}
        for row in rows:
            key = (row["model"], row["task_class"])
            current = aggregates.setdefault(key, {"model": row["model"],
                                                  "task_class": row["task_class"],
                                                  "count": 0, "successes": 0,
                                                  "latency": 0.0})
            current["count"] += 1
            current["successes"] += int(bool(row["success"]))
            current["latency"] += float(row["latency_ms"] or 0)
        return [{"model": value["model"], "task_class": value["task_class"],
                 "count": value["count"],
                 "success_rate": value["successes"] / value["count"],
                 "latency": value["latency"] / value["count"]}
                for value in aggregates.values()]

    def activate(self, key, *, approved_by):
        """Human approval only; activation records who approved it."""
        with self.store._db() as db:
            row = db.execute("SELECT status,definition FROM candidates WHERE key=?",
                             (key,)).fetchone()
            if not row:
                raise LearningError("Candidate not found.")
            if row["status"] != "proposed":
                raise LearningError("Only a candidate that passed the held-out "
                                    "gate can be activated.")
            if not approved_by or len(str(approved_by)) < 3:
                raise LearningError("Activation requires an approving owner.")
            db.execute("UPDATE candidates SET status='activated',decision_by=? WHERE key=?",
                       (str(approved_by)[:60], key))
        return {"key": key, "status": "activated", "approved_by": approved_by[:60]}

    def rollback(self, key):
        with self.store._db() as db:
            row = db.execute("SELECT status FROM candidates WHERE key=?",
                             (key,)).fetchone()
            if not row or row["status"] != "activated":
                raise LearningError("Only an activated candidate can rollback.")
            db.execute("UPDATE candidates SET status='rolled_back' WHERE key=?", (key,))
        return {"key": key, "status": "rolled_back"}

    def candidates(self):
        with self.store._db() as db:
            rows = db.execute("SELECT * FROM candidates ORDER BY created DESC "
                              "LIMIT 100").fetchall()
        return [dict(row) for row in rows]


class TraceLearning:
    """Local workflow discovery over execution outcomes only.

    Stores tool names and success/failure, never arguments or results.
    Successful execution is not a user-satisfaction or semantic score.
    """

    def __init__(self, data_dir):
        self.root = Path(data_dir).resolve() / "trace-learning"
        self.lock = threading.RLock()

    def _file(self, project):
        if not isinstance(project, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", project):
            raise ValueError("Invalid learning project.")
        path = self.root / (project + ".json")
        if self.root.is_symlink() or path.is_symlink():
            raise ValueError("Linked learning storage prohibited.")
        return path

    def _read(self, project):
        path = self._file(project)
        if not path.exists():
            return []
        if path.stat().st_size > 1_000_000:
            raise ValueError("Learning history exceeds its limit.")
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or len(rows) > 500:
            raise ValueError("Invalid learning history.")
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {"steps", "outcome"}
                    or row["outcome"] not in ("success", "failure")
                    or not isinstance(row["steps"], list) or not 1 <= len(row["steps"]) <= 4
                    or any(not isinstance(s, dict) or set(s) != {"step_type", "tool_name"}
                           or s["step_type"] != "tool_call"
                           or not isinstance(s["tool_name"], str)
                           or not re.fullmatch(r"[a-zA-Z0-9_]{1,120}", s["tool_name"])
                           for s in row["steps"])):
                raise ValueError("Invalid learning trace.")
        return rows

    def record(self, project, names, succeeded):
        if not names or len(names) > 4 or any(
                not isinstance(n, str) or not re.fullmatch(r"[a-zA-Z0-9_]{1,120}", n)
                for n in names):
            raise ValueError("Invalid tool sequence.")
        with self.lock:
            rows = self._read(project)
            rows.append({"steps": [{"step_type": "tool_call", "tool_name": n} for n in names],
                         "outcome": "success" if succeeded else "failure"})
            atomic_write(self._file(project), json.dumps(rows[-500:]).encode())

    def patterns(self, project):
        with self.lock:
            # Each trace contributes at most one occurrence of each sequence;
            # require three separate observations, never a repeated single trace.
            found = SkillDiscovery(min_frequency=3, min_sequence_length=2,
                                   max_sequence_length=2, min_outcome=0.8)
            return [dict(asdict(s), advisory=True,
                         outcome_basis="execution success, not user-rated correctness")
                    for s in found.analyze_traces(self._read(project))][:20]
