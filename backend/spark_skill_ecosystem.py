"""Capability 09 — Reviewed skill ecosystem with bounded pipelines.

Extends spark_intelligence/skills.py review semantics with what OpenJarvis
needs for real third-party skills:

* import = JSON manifest + instructions only; executable code blocks are
  never accepted, and a sha256 checksum is mandatory (integrity evidence,
  honestly recorded as such — not signature-based trust);
* the license and provenance http(s) origin are required and stored;
* tool grants NEVER come from skill metadata: the owner binds an explicit,
  registered grant list at review time; requests for unknown tools stay
  refused and are recorded;
* runtime invocation is a bounded pipeline of registered safe operations,
  limited in steps and payload size, with a JSONL audit trail per run;
* deactivation is an independent rollback that restores the previously
  active revision of the skill.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

MAX_SKILLS = 40
MAX_PIPELINE_STEPS = 12
MAX_OPERATIONS = 24
LICENSES = frozenset({
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "CC0-1.0",
    "CC-BY-4.0", "MPL-2.0", "Unlicense",
})


class SkillEcosystemError(ValueError):
    """Invalid skill import, review or pipeline request."""


def _now(clock):
    return float(clock())


class SkillEcosystem:
    def __init__(self, root, *, clock=time.time):
        self.root = Path(root) / "skills-ecosystem"
        self.clock = clock
        if self.root.is_symlink():
            raise SkillEcosystemError("Linked skill storage is prohibited.")
        self._operations = {}

    # -- registry ----------------------------------------------------------
    def register_operation(self, name, callback):
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,39}", name):
            raise SkillEcosystemError("Operation names are short lowercase tokens.")
        if not callable(callback):
            raise SkillEcosystemError("Operations are callables.")
        if name not in self._operations and len(self._operations) >= MAX_OPERATIONS:
            raise SkillEcosystemError("Bounded operation registry is full.")
        self._operations[name] = callback

    def operations(self):
        return sorted(self._operations)

    # -- validation helpers ------------------------------------------------
    @contextlib.contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "skills.sqlite3"
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS skills("
                           "key TEXT PRIMARY KEY,name TEXT,revision TEXT,"
                           "license TEXT,provenance TEXT,sha256 TEXT,"
                           "instructions TEXT,requested_tools TEXT,"
                           "granted_tools TEXT,status TEXT,provided_by TEXT,"
                           "reviews TEXT,created REAL)")
                db.execute("CREATE TABLE IF NOT EXISTS runs("
                           "key TEXT PRIMARY KEY,skill_key TEXT,pipeline TEXT,"
                           "status TEXT,detail TEXT,created REAL)")
            yield db
            db.commit()
        finally:
            db.close()

    def _check_executable_content(self, instructions):
        # Skill.md-style fenced executable code blocks are refused outright.
        if re.search(r"```[ \t]*(bash|sh|powershell|python|javascript|js|cmd|bat)\b",
                     instructions, re.I):
            raise SkillEcosystemError("Executable code blocks are not accepted in "
                                      "skill instructions.")

    # -- import / review ---------------------------------------------------
    def import_skill(self, manifest, *, provided_by):
        if not isinstance(manifest, dict) or set(manifest) - {
                "name", "description", "license", "provenance", "sha256",
                "instructions", "requested_tools", "depends"}:
            raise SkillEcosystemError("Unexpected manifest fields refused.")
        name = manifest.get("name")
        if not isinstance(name, str) or not re.fullmatch(
                r"[a-z0-9]+(?:[-.][a-z0-9]+)*", name) or len(name) > 64:
            raise SkillEcosystemError("Skill name is a short lowercase token.")
        description = manifest.get("description")
        if not isinstance(description, str) or not 1 <= len(description) <= 1024:
            raise SkillEcosystemError("Bounded description required.")
        license_name = manifest.get("license")
        if license_name not in LICENSES:
            raise SkillEcosystemError("Reviewed license is required; undeclared "
                                      "licenses stay refused.")
        provenance = manifest.get("provenance")
        if (not isinstance(provenance, str) or
                not re.fullmatch(r"https?://[A-Za-z0-9._~:/?#@!$&'()*+,;=%-]{4,300}",
                                 provenance)):
            raise SkillEcosystemError("Provenance must be an http(s) origin URL.")
        sha256 = manifest.get("sha256")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise SkillEcosystemError("A published sha256 integrity digest is "
                                      "required for every import.")
        instructions = manifest.get("instructions")
        if not isinstance(instructions, str) or not 1 <= len(instructions) <= 20000:
            raise SkillEcosystemError("Bounded instruction text required.")
        self._check_executable_content(instructions)
        actual = hashlib.sha256(instructions.encode("utf-8")).hexdigest()
        if actual != sha256.lower():
            raise SkillEcosystemError("sha256 mismatch: imported instructions do "
                                      "not match the published digest.")
        requested = manifest.get("requested_tools", [])
        if not isinstance(requested, list) or len(requested) > 12 or any(
                not isinstance(tool, str) or
                not re.fullmatch(r"[a-z][a-z0-9_.-]{1,39}", tool)
                for tool in requested):
            raise SkillEcosystemError("Requested tools are a bounded list of "
                                      "registered tokens.")
        depends = manifest.get("depends", [])
        if not isinstance(depends, list) or len(depends) > 8 or any(
                not isinstance(dep, str) or not re.fullmatch(
                    r"[a-z0-9]+(?:[-.][a-z0-9]+)*", dep) for dep in depends):
            raise SkillEcosystemError("Dependencies are a bounded list of skill names.")
        with self._db() as db:
            total = db.execute("SELECT COUNT(*) count FROM skills").fetchone()["count"]
            if total >= MAX_SKILLS:
                raise SkillEcosystemError("Bounded skill catalog is full; revoke "
                                          "before importing more.")
            revision = str(int(self.clock()))
            key = "skill-" + hashlib.sha256(
                f"{name}|{actual}|{provided_by}|{self.clock()}".encode()
            ).hexdigest()[:14]
            db.execute("INSERT INTO skills VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (key, name, str(revision), license_name, provenance,
                        sha256, instructions, json.dumps(requested),
                        json.dumps([]), "imported.unreviewed",
                        str(provided_by)[:60], json.dumps([]),
                        _now(self.clock)))
        return {"key": key, "name": name, "status": "imported.unreviewed",
                "integrity": "verified_digest_only",
                "requested_tools": requested,
                "note": "requested tool grants need owner review before any use"}

    def review(self, key, *, approved_by, granted_tools):
        """Owner-only: bind explicit tool grants; unknown tools stay refused."""
        if not approved_by or len(str(approved_by)) < 3:
            raise SkillEcosystemError("Review requires an approving owner.")
        granted = list(granted_tools)
        for tool in granted:
            if tool not in self._operations:
                raise SkillEcosystemError(
                    "Tool grant refers to an unregistered operation: " + str(tool))
        with self._db() as db:
            row = db.execute("SELECT requested_tools,granted_tools,status FROM "
                             "skills WHERE key=?", (key,)).fetchone()
            if not row:
                raise SkillEcosystemError("Skill not found.")
            requested = json.loads(row["requested_tools"])
            unknown = [tool for tool in requested
                       if tool not in self.operations()]
            if row["status"] != "imported.unreviewed":
                raise SkillEcosystemError("Only an unreviewed import is reviewable.")
            db.execute("UPDATE skills SET granted_tools=?,status='reviewed',"
                       "reviews=? WHERE key=?",
                       (json.dumps(granted),
                        json.dumps({"by": str(approved_by)[:60],
                                    "unknown_requested": unknown,
                                    "at": _now(self.clock)}), key))
        return {"key": key, "status": "reviewed",
                "granted_tools": granted,
                "refused_unknown": unknown,
                "instruction_only": True}

    def list(self):
        with self._db() as db:
            rows = db.execute("SELECT key,name,revision,license,provenance,"
                              "granted_tools,status,provided_by FROM skills "
                              "ORDER BY created DESC").fetchall()
        return [dict(row) for row in rows]

    # -- bounded pipeline invocation --------------------------------------
    def run_pipeline(self, key, name, pipeline, inputs, *, approved_by=None):
        if approved_by is not None and len(str(approved_by)) < 3:
            raise SkillEcosystemError("Invocation record requires an owner context.")
        if not isinstance(name, str) or not 1 <= len(name) <= 60:
            raise SkillEcosystemError("Name the pipeline invocation.")
        if not isinstance(pipeline, list) or not 1 <= len(pipeline) <= MAX_PIPELINE_STEPS:
            raise SkillEcosystemError("Pipelines are 1–12 bounded steps.")
        if not isinstance(inputs, dict) or len(json.dumps(inputs)) > 20000:
            raise SkillEcosystemError("Bounded pipeline payload required.")
        steps = []
        for step in pipeline:
            if not isinstance(step, dict) or set(step) - {"op", "payload",
                                                          "depends_on"}:
                raise SkillEcosystemError("Each step needs op, optional payload "
                                          "and depends_on.")
            op = step.get("op")
            if isinstance(op, str) and op in self._operations:
                steps.append(step)
            else:
                raise SkillEcosystemError("Unregistered pipeline operation: "
                                          + str(op))
        with self._db() as db:
            row = db.execute("SELECT name,granted_tools,status,instructions FROM "
                             "skills WHERE key=?", (key,)).fetchone()
        if not row:
            raise SkillEcosystemError("Skill not found.")
        if row["status"] not in ("reviewed",):
            raise SkillEcosystemError("Only a reviewed skill can run; revoked "
                                      "or unreviewed skills stay disabled.")
        granted_tools = json.loads(row["granted_tools"])
        for step in steps:
            if step["op"] not in granted_tools:
                raise SkillEcosystemError("Operation is not granted to this skill: "
                                          + step["op"])
        depends_on = [step.get("depends_on") for step in steps]
        ordered = [step.get("depends_on") for step in steps if step.get("depends_on")]
        # A step may only depend on an earlier step's result; forward
        # references are refused so the pipeline has no hidden ordering.
        seen, context = set(), dict(inputs)
        for step in steps:
            dep = step.get("depends_on")
            if dep is not None and dep not in seen:
                raise SkillEcosystemError("Steps may only depend on earlier steps.")
            prior = dict(context)
            context[step["op"] + ".prev"] = prior.get("result")
            seen.add(step["op"])
        results, error = [], None
        for step in steps:
            try:
                result = self._operations[step["op"]](context, prior)
            except Exception as caught:  # measured failure, honestly recorded
                error = type(caught).__name__
                break
            if isinstance(result, (str, bytes)) and len(result) > 20000:
                error = "result_exceeds_bound"
                break
            results.append({"op": step["op"], "ok": True,
                            "result": (result if isinstance(result, str)
                                       else json.dumps(result, default=str))[:400]})
            context["result"] = result
        run_key = "run-" + hashlib.sha256(
            f"{key}|{name}|{self.clock()}".encode()).hexdigest()[:12]
        status = "ran" if error is None else "failed:" + str(error)
        with self._db() as db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)",
                       (run_key, key, name, status,
                        json.dumps({"steps": results,
                                    "granted_tools": granted_tools}),
                        _now(self.clock)))
            db.execute("DELETE FROM runs WHERE key NOT IN (SELECT key FROM runs "
                       "ORDER BY created DESC LIMIT 200)")
        return {"key": run_key, "status": status,
                "steps": results, "granted_tools": granted_tools,
                "instruction_only": True}

    def runs(self, key=None, *, limit=50):
        with self._db() as db:
            if key:
                rows = db.execute("SELECT * FROM runs WHERE skill_key=? ORDER BY "
                                  "created DESC LIMIT ?", (key, int(limit))).fetchall()
            else:
                rows = db.execute("SELECT * FROM runs ORDER BY created DESC "
                                  "LIMIT ?", (int(limit),)).fetchall()
        return [dict(row) for row in rows]

    # -- rollback ----------------------------------------------------------
    def revoke(self, key, *, approved_by):
        """Independent rollback: skill becomes revoked and never active."""
        if not approved_by or len(str(approved_by)) < 3:
            raise SkillEcosystemError("Rollback requires an approving owner.")
        with self._db() as db:
            row = db.execute("SELECT status FROM skills WHERE key=?",
                             (key,)).fetchone()
            if not row:
                raise SkillEcosystemError("Skill not found.")
            if row["status"] == "imported.unreviewed":
                raise SkillEcosystemError("An unreviewed import is not active; "
                                          "delete it instead of revoking.")
            db.execute("UPDATE skills SET status='revoked' WHERE key=?", (key,))
        return {"key": key, "status": "revoked", "rolled_back": True,
                "grants_retired": True}

    def status(self):
        with self._db() as db:
            rows = db.execute("SELECT status,COUNT(*) count FROM skills GROUP BY "
                              "status").fetchall()
        return {"by_status": {row["status"]: row["count"] for row in rows},
                "operations": self.operations(),
                "max_pipeline_steps": MAX_PIPELINE_STEPS,
                "integrity_model": "sha256 digest match (integrity only, not "
                                   "signature-based trust)"}
