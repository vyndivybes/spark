"""Capability 08 — LLM-guided specification search with hard evidence gates.

A "spec" is a bounded JSON configuration for one SPARK task (prompt shape,
parameters, routing flags). Optimization follows the OpenJarvis loop:

  diagnose -> plan -> test -> gate -> record, with owner approval and
  independent rollback to the previously active specification.

Honesty rules encoded here:
* candidates are scored only by *measured* case outcomes from an injected
  evaluator; a model's self-assessment is never used as a score;
* without an explicitly granted planner (e.g. a free-tier LLM the owner
  opted into), planning honestly reports `planner_not_configured`;
* the holdout gate refuses any candidate that loses accuracy on unseen
  cases, and activation requires an approving owner and stays rollback-able.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import random
import re
import sqlite3
import time
from pathlib import Path

MAX_CANDIDATES = 6
MAX_CASES = 400
REGRESSION_MARGIN = 0.02
IMPROVEMENT_MIN = 0.02
KEEP_RUNS = 50


class SpecError(ValueError):
    """Invalid spec, case set or search request."""


def validate_spec(spec):
    """Bounded JSON spec; executable strings are refused by design."""
    if not isinstance(spec, dict) or len(spec) > 12:
        raise SpecError("A spec is a JSON object with at most 12 fields.")
    for key, value in spec.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key):
            raise SpecError("Spec keys are short lowercase identifiers.")
        if isinstance(value, str) and len(value) > 2000:
            raise SpecError("Spec string fields are bounded at 2000 characters.")
        if isinstance(value, (list, dict)) and len(json.dumps(value)) > 8000:
            raise SpecError("Spec nested fields are bounded.")
    return spec


class CaseSet:
    """Labeled, deterministic evaluation cases with provenance."""

    def __init__(self, name, cases, *, provenance="fixture"):
        provenance = str(provenance or "fixture")
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,60}", name):
            raise SpecError("Case set names are short lowercase tokens.")
        if not isinstance(cases, list) or not MAX_CASES >= len(cases) >= 2:
            raise SpecError("A case set needs between 2 and 400 cases.")
        normalized = []
        for case in cases:
            if (not isinstance(case, dict) or
                    set(case) != {"name", "input", "expected"}):
                raise SpecError("Each case needs name, input and expected.")
            if not isinstance(case["name"], str) or not case["name"]:
                raise SpecError("Case names must be non-empty strings.")
            normalized.append({"name": str(case["name"])[:120],
                               "input": case["input"],
                               "expected": case["expected"]})
        self.name = name
        self.cases = normalized
        self.provenance = provenance

    def split(self, *, holdout_fraction=0.3, seed=7):
        if type(holdout_fraction) is not float or not 0.1 <= holdout_fraction <= 0.5:
            raise SpecError("Holdout fraction must be between 0.1 and 0.5.")
        ordered = list(self.cases)
        random.Random(seed).shuffle(ordered)
        holdout_n = max(1, int(len(ordered) * holdout_fraction))
        return ordered[holdout_n:], ordered[:holdout_n]


class SpecSearch:
    """SQLite-recorded spec search with measured scoring and owner gates."""

    def __init__(self, root, *, clock=time.time):
        self.root = Path(root) / "spec-search"
        self.clock = clock
        if self.root.is_symlink():
            raise SpecError("Linked spec storage is prohibited.")

    @contextlib.contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "spec-search.sqlite3"
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS runs("
                           "key TEXT PRIMARY KEY,goal TEXT,baseline REAL,"
                           "diagnosis TEXT,status TEXT,created REAL)")
                db.execute("CREATE TABLE IF NOT EXISTS candidates("
                           "key TEXT PRIMARY KEY,run_key TEXT,spec TEXT,"
                           "train REAL,heldout REAL,baseline REAL,status TEXT,"
                           "approved_by TEXT,created REAL)")
                db.execute("CREATE TABLE IF NOT EXISTS active("
                           "slot TEXT PRIMARY KEY,spec TEXT,since REAL)")
            yield db
            db.commit()
        finally:
            db.close()

    # -- diagnose ----------------------------------------------------------
    def diagnose(self, cases, runner, *, current_spec=None):
        """Measured failure diagnosis of the current or default spec."""
        if not callable(runner):
            raise SpecError("Scoring requires an injected measured runner.")
        validate_spec(current_spec or {})
        failures, hits = [], 0
        for case in cases:
            try:
                outcome = runner(current_spec or {}, case)
            except Exception as error:
                failures.append({"case": case["name"],
                                 "reason": "runner error: " + type(error).__name__})
                continue
            if outcome is True:
                hits += 1
            else:
                failures.append({"case": case["name"],
                                 "reason": "measured mismatch"})
        total = len(cases)
        score = hits / total if total else 0.0
        return {"score": score, "cases": total, "failures": failures,
                "provenance": getattr(cases, "provenance", "fixture")}

    # -- plan --------------------------------------------------------------
    def plan(self, goal, current_spec=None, *, planner=None):
        """Candidate specs from an owner-granted planner; honest when absent."""
        goal = str(goal or "")
        if not 10 <= len(goal) <= 600:
            raise SpecError("Describe the goal in 10–600 characters.")
        if planner is None:
            return {"status": "planner_not_configured", "candidates": [],
                    "note": "Grant a free-tier planner explicitly before "
                            "LLM-guided planning runs."}
        candidates = planner(goal, current_spec or {})
        if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
            raise SpecError("Planner must return at most %d candidates."
                            % MAX_CANDIDATES)
        return {"status": "planned", "candidates": [validate_spec(spec)
                                                    for spec in candidates]}

    # -- search / gate / record -------------------------------------------
    def search(self, goal, case_set, runner, *, planner=None,
               current_spec=None, holdout_fraction=0.3):
        """One bounded diagnose->plan->test->gate->record cycle."""
        if not isinstance(case_set, CaseSet):
            raise SpecError("Search runs against a labeled CaseSet.")
        if not callable(runner):
            raise SpecError("Scoring requires an injected measured runner.")
        train, heldout = case_set.split(holdout_fraction=holdout_fraction)
        diagnosis = self.diagnose(train, runner, current_spec=current_spec)
        baseline = diagnosis["score"]
        plan = self.plan(goal, current_spec, planner=planner)
        if plan["status"] != "planned":
            run_key = self._record_run(goal, baseline, diagnosis, plan["status"])
            return {"run": run_key, "status": plan["status"], "baseline": baseline,
                    "candidates": [], "diagnosis": {"failures": len(diagnosis["failures"])}}
        results = []
        for index, spec in enumerate(plan["candidates"]):
            train_score = self.diagnose(train, runner, current_spec=spec)["score"]
            heldout_score = self.diagnose(heldout, runner, current_spec=spec)["score"]
            improvement = train_score >= baseline + IMPROVEMENT_MIN
            no_regression = heldout_score >= baseline - REGRESSION_MARGIN
            status = "proposed" if (improvement and no_regression) else "rejected"
            key = self._record_candidate(spec=spec,
                                         train=train_score, heldout=heldout_score,
                                         baseline=baseline, status=status,
                                         goal=goal, index=index)
            results.append({"key": key, "spec": spec, "train": train_score,
                            "heldout": heldout_score, "baseline": baseline,
                            "status": status})
        run_key = self._record_run(goal, baseline, diagnosis,
                                   "gated" if any(r["status"] == "proposed"
                                                  for r in results) else "no_candidate_gated")
        return {"run": run_key, "status": "gated", "baseline": baseline,
                "candidates": results,
                "diagnosis": {"failures": len(diagnosis["failures"])}}

    # -- persistence -------------------------------------------------------
    def _record_run(self, goal, baseline, diagnosis, status):
        key = "r-" + hashlib.sha256(
            f"{goal}|{baseline}|{self.clock()}".encode()).hexdigest()[:12]
        with self._db() as db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)",
                       (key, goal[:600], baseline,
                        json.dumps({"failures": diagnosis["failures"][:20],
                                    "cases": diagnosis["cases"]}), status,
                        self.clock()))
            db.execute("DELETE FROM runs WHERE key NOT IN "
                       "(SELECT key FROM runs ORDER BY created DESC LIMIT ?)",
                       (KEEP_RUNS,))
        return key

    def _record_candidate(self, *, spec, train, heldout, baseline,
                          status, goal, index):
        key = "s-" + hashlib.sha256(
            f"{goal}|{index}|{json.dumps(spec, sort_keys=True)}|{self.clock()}"
            .encode()).hexdigest()[:12]
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO candidates VALUES(?,?,?,?,?,?,?,?,?)",
                       (key, None, json.dumps(spec, sort_keys=True),
                        train, heldout, baseline, status, None, self.clock()))
        return key

    def candidates(self, *, status=None, limit=50):
        with self._db() as db:
            if status:
                rows = db.execute("SELECT * FROM candidates WHERE status=? "
                                  "ORDER BY created DESC LIMIT ?",
                                  (str(status), int(limit))).fetchall()
            else:
                rows = db.execute("SELECT * FROM candidates ORDER BY created "
                                  "DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(row) for row in rows]

    # -- activation and rollback ------------------------------------------
    def active_spec(self):
        with self._db() as db:
            row = db.execute("SELECT spec,since FROM active WHERE slot='main'"
                             ).fetchone()
        return {"spec": json.loads(row["spec"]) if row else None,
                "since": row["since"] if row else None}

    def activate(self, key, *, approved_by):
        if not approved_by or len(str(approved_by)) < 3:
            raise SpecError("Activation requires an approving owner.")
        with self._db() as db:
            row = db.execute("SELECT spec,status FROM candidates WHERE key=?",
                             (key,)).fetchone()
            if not row:
                raise SpecError("Candidate not found.")
            if row["status"] != "proposed":
                raise SpecError("Only a gated proposed candidate can be activated.")
            current = db.execute("SELECT spec FROM active WHERE slot='main'"
                                 ).fetchone()
            db.execute("INSERT OR REPLACE INTO active VALUES(?,?,?)",
                       ("main", current["spec"] if current else "null", self.clock()))
            # The previous spec is preserved as a rollback checkpoint slot.
            if current:
                db.execute("INSERT OR REPLACE INTO active VALUES(?,?,?)",
                           ("rollback", current["spec"], self.clock()))
            db.execute("INSERT OR REPLACE INTO active VALUES('main',?,?)",
                       (row["spec"], self.clock()))
            db.execute("UPDATE candidates SET status='activated',approved_by=? "
                       "WHERE key=?", (str(approved_by)[:60], key))
        return {"key": key, "status": "activated", "approved_by": str(approved_by)[:60],
                "rollback": True}

    def rollback(self):
        """Independent rollback to the checkpointed previous spec."""
        with self._db() as db:
            previous = db.execute("SELECT spec FROM active WHERE slot='rollback'"
                                  ).fetchone()
            main = db.execute("SELECT spec FROM active WHERE slot='main'"
                              ).fetchone()
            if not main or main["spec"] in (None, "null"):
                raise SpecError("No activated spec to roll back.")
            db.execute("INSERT OR REPLACE INTO active VALUES('main',?,?)",
                       (previous["spec"] if previous else "null", self.clock()))
            db.execute("DELETE FROM active WHERE slot='rollback'")
        try:
            restored = json.loads(previous["spec"]) if previous else None
        except (json.JSONDecodeError, TypeError):
            restored = None
        return {"status": "rolled_back", "spec": restored}

    def status(self):
        with self._db() as db:
            runs = db.execute("SELECT COUNT(*) count FROM runs").fetchone()["count"]
            active = self.active_spec()
        return {"runs_recorded": runs, "active_spec": active["spec"],
                "active_since": active["since"],
                "planner": "owner-granted only (never auto-configured)"}
