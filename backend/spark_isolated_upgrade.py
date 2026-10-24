"""Minimal isolated candidate workspaces for continuous self-upgrades.

Every upgrade cycle is generated, inspected and focused-tested inside a
small throw-away workspace on secondary storage (D: by default) instead of
the live repository. Only the selected target source, its backend import
closure and the matching focused test files are copied - never the whole
repository - so the owner's live work tree, uncommitted changes and
unrelated files are preserved and verified byte for byte.

Promotion into the live tree is a separate, explicitly gated step owned by
AutoEvolution: a dirty work tree, an exhausted daily quota or a failed
health check keeps the candidate staged in isolation. Nothing is ever
committed into the live repository and no unrelated owner file is staged
by this module. Emergency stop, rollback and audit history are retained.
"""
import ast
import asyncio
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

from spark_maintenance import atomic_write, digest
from spark_security_scan import scan_secrets
from spark_auto_evolution import rank_targets


DEFAULT_BASE_DIRECTORY = r"D:\SPARK-Evolution-Temp\isolated-upgrades"
MAX_CLOSURE_FILES = 40
MAX_CANDIDATE_WORKSPACES = 24
MAX_COPIED_FILE_BYTES = 262144
ISOLATED_TEST_TIMEOUT = 240
CANDIDATE_STATUS = frozenset({"testing", "tested", "rejected", "promoted",
                              "rolled_back", "stale", "failed", "discarded"})


class IsolatedUpgradeError(ValueError):
    pass


def referenced_imports(text):
    """Top-level module import names of a Python source (absolute imports)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found - {"__future__"}


def _in_scope(relative):
    parts = PurePosixPath(relative).parts
    return len(parts) >= 2 and parts[0] in ("backend", "tests")


def _candidates_for_module(name, root_name):
    """Possible relative locations a module import could resolve to."""
    return [root_name + "/" + name + ".py"]


def _linked(path):
    """Symlink/junction check delegating to the shared repository helper."""
    from spark_repo_upgrade import linked
    return linked(path)


class CandidateWorkspace:
    """A per-cycle directory: manifest, candidate record and copied files."""

    def __init__(self, root, live_root, manifest):
        self.root = Path(root)
        self.live = Path(live_root)
        self.manifest = manifest

    @property
    def name(self):
        return self.root.name

    def candidate(self, default=None):
        try:
            return json.loads((self.root / "candidate.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return default


class IsolatedUpgradeManager:
    """Runs generation, validation and focused tests outside the live tree."""

    def __init__(self, evolution, live_root, *, base_dir=None, clock=time.time,
                 runner=None):
        self.evolution = evolution
        self.live = Path(live_root).resolve()
        if base_dir is not None:
            self.base = Path(base_dir)
        else:
            self.base = Path(os.environ.get("SPARK_ISOLATED_ROOT")
                             or DEFAULT_BASE_DIRECTORY)
        self.clock = clock
        self._runner = runner
        self._cycle_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # audit history
    # ------------------------------------------------------------------
    def _audit(self, kind, **fields):
        entry = {"ts": round(self.clock(), 3), "kind": kind, **fields}
        try:
            self.base.mkdir(parents=True, exist_ok=True)
            with (self.base / "audit.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, sort_keys=True) + "\n")
        except OSError:
            pass

    def history(self, limit=100):
        try:
            lines = (self.base / "audit.jsonl").read_text(
                encoding="utf-8").replace("\r\n", "\n").split("\n")
        except OSError:
            return []
        entries = [json.loads(line) for line in lines if line and not line.isspace()]
        return entries[-limit:][::-1]

    # ------------------------------------------------------------------
    # candidate discovery (restart-safe: everything lives on disk)
    # ------------------------------------------------------------------
    def workspaces(self):
        found = []
        try:
            entries = sorted(self.base.iterdir())
        except OSError:
            return found
        for directory in entries:
            manifest_path = directory / "manifest.json"
            if not directory.is_dir() or manifest_path.is_symlink():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            found.append(CandidateWorkspace(directory, self.live, manifest))
        return found

    def list_candidates(self):
        records = []
        for workspace in self.workspaces():
            record = workspace.candidate()
            if isinstance(record, dict) and record.get("status") in CANDIDATE_STATUS:
                record["workspace"] = workspace.name
                records.append(record)
        return records

    def held(self):
        """The oldest fully validated candidate waiting for promotion."""
        records = [record for record in self.list_candidates()
                   if record["status"] == "tested"]
        return records[0] if records else None

    def held_count(self):
        return len([record for record in self.list_candidates()
                    if record["status"] == "tested"])

    def candidate_record(self, candidate_id):
        for workspace in self.workspaces():
            record = workspace.candidate()
            if isinstance(record, dict) and record.get("candidate_id") == candidate_id:
                record["workspace"] = workspace.name
                return record
        return None

    def mark(self, candidate_id, status, note=""):
        if status not in CANDIDATE_STATUS:
            raise IsolatedUpgradeError("Unknown candidate status.")
        for workspace in self.workspaces():
            record = workspace.candidate()
            if isinstance(record, dict) and record.get("candidate_id") == candidate_id:
                record["status"] = status
                record["notes"] = note[:300]
                record["updated"] = round(self.clock(), 3)
                atomic_write(workspace.root / "candidate.json", json.dumps(record).encode())
                self._audit("candidate_" + status, candidate_id=candidate_id,
                            workspace=workspace.name, note=note[:200])
                return record
        return None

    def staleness(self, record):
        """Relative paths whose live content changed since generation."""
        mismatched = []
        for relative, original in (record.get("originals") or {}).items():
            path = self.live / relative
            try:
                if _in_scope(relative) and not _linked(path):
                    if digest(path.read_bytes()) != original:
                        mismatched.append(relative)
            except OSError:
                mismatched.append(relative)
        return mismatched

    # ------------------------------------------------------------------
    # workspace construction (minimal copy set)
    # ------------------------------------------------------------------
    def _eligible_targets(self):
        targets = []
        for path in sorted((self.live / "backend").glob("*.py")):
            relative = "backend/" + path.name
            if hasattr(self.evolution.maintenance, "_target"):
                try:
                    self.evolution.maintenance._target(relative)
                except Exception:
                    continue
            targets.append(relative)
        return targets

    def _matching_tests(self, stem):
        token = re.sub(r"[^a-z0-9_]", "", stem.lower())
        if not token:
            return []
        hits = []
        for path in sorted((self.live / "tests").glob("test_*" + token + "*.py")):
            if not path.is_file() or _linked(path):
                continue
            if path.stat().st_size > MAX_COPIED_FILE_BYTES:
                continue
            hits.append("tests/" + path.name)
            if len(hits) >= 8:
                break
        return hits

    def _closure(self, target, tests):
        wanted = {}
        queue = [target, *tests]
        while queue:
            relative = queue.pop(0)
            if relative in wanted or not _in_scope(relative):
                continue
            path = self.live / relative
            if not path.is_file():
                if relative in (target, *tests):
                    raise IsolatedUpgradeError("Required candidate file is missing: " + relative)
                continue
            if _linked(path) or _linked(path.parent):
                raise IsolatedUpgradeError("Linked candidate source is prohibited: " + relative)
            data = path.read_bytes()
            if len(data) > MAX_COPIED_FILE_BYTES:
                raise IsolatedUpgradeError(
                    "Candidate file exceeds the %d KiB isolation copy limit: %s"
                    % (MAX_COPIED_FILE_BYTES // 1024, relative))
            wanted[relative] = data
            if len(wanted) > MAX_CLOSURE_FILES:
                raise IsolatedUpgradeError(
                    "Candidate import closure exceeds %d files; too broad to isolate." % MAX_CLOSURE_FILES)
            text = data.decode("utf-8-sig", errors="replace")
            for name in referenced_imports(text):
                for guess in _candidates_for_module(name, "backend") + \
                             _candidates_for_module(name, "tests"):
                    if guess not in wanted:
                        queue.append(guess)
        return wanted

    def _new_workspace(self):
        if self.base.is_symlink():
            raise IsolatedUpgradeError("Linked isolated storage is prohibited.")
        try:
            self.base.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise IsolatedUpgradeError(
                "Isolated storage on %s is unavailable: %s" % (self.base.drive, str(error)[:120])) from None
        key = time.strftime("%Y%m%d-%H%M%S", time.gmtime(self.clock())) + "-" + secrets.token_hex(4)
        root = self.base / key
        try:
            root.mkdir()
        except OSError as error:
            raise IsolatedUpgradeError("Isolated workspace could not be created: " + str(error)[:120]) from None
        root_backend = root / "backend"
        root_tests = root / "tests"
        root_backend.mkdir()
        root_tests.mkdir()
        return root

    def _build(self, goal):
        targets = self._eligible_targets()
        target = rank_targets(targets, goal)
        if target is None:
            return None
        tests = self._matching_tests(Path(target).stem)
        closure = self._closure(target, tests)
        root = self._new_workspace()
        originals = {}
        for relative, data in closure.items():
            (root / relative).write_bytes(data)
            originals[relative] = digest(data)
        manifest = {
            "created": round(self.clock(), 3),
            "goal": goal,
            "target": target,
            "tests": tests,
            "originals": originals,
            "live_root": str(self.live),
        }
        atomic_write(root / "manifest.json", json.dumps(manifest, sort_keys=True).encode())
        self._record(project=None, stage="build", outcome="isolated workspace built",
                     evidence={"target": target, "files": sorted(closure)})
        return CandidateWorkspace(root, self.live, manifest)

    # ------------------------------------------------------------------
    # local validation inside the workspace
    # ------------------------------------------------------------------
    def _apply_candidate(self, workspace, changes):
        record = {
            "candidate_id": None,
            "status": "testing",
            "target": workspace.manifest["target"],
            "goal": workspace.manifest["goal"],
            "created": round(self.clock(), 3),
            "changes": changes,
            "originals": dict(workspace.manifest["originals"]),
        }
        atomic_write(workspace.root / "candidate.json", json.dumps(record).encode())
        for change in changes:
            (workspace.root / change["path"]).write_text(change["content"], encoding="utf-8")
        return record

    def _validate(self, workspace):
        findings = []
        backend = workspace.root / "backend"
        for source in sorted(backend.glob("*.py")):
            if source.is_symlink():
                findings.append({"path": source.name, "error": "linked source prohibited"})
                continue
            try:
                text = source.read_text(encoding="utf-8-sig")
                ast.parse(text, filename=source.name)
            except (SyntaxError, UnicodeError) as error:
                findings.append({"path": "backend/" + source.name, "error": str(error)[:180]})
                continue
            for hit in scan_secrets(text, "backend/" + source.name):
                findings.append({"path": "backend/" + source.name, "error": hit[:180]})
        tests_run, returncode, tail = False, None, ""
        if workspace.manifest["tests"]:
            try:
                timeout = int(os.environ.get("SPARK_ISOLATED_TEST_TIMEOUT",
                                             str(ISOLATED_TEST_TIMEOUT)))
            except ValueError:
                timeout = ISOLATED_TEST_TIMEOUT
            if not 60 <= timeout <= 600:
                return {"passed": False, "tests_run": False, "returncode": None,
                        "tail": "SPARK_ISOLATED_TEST_TIMEOUT must be 60-600 seconds."}
            runner = self._runner or subprocess.run
            try:
                completed = runner(
                    [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                     "-p", "test_*.py"],
                    cwd=workspace.root, capture_output=True, timeout=timeout,
                    text=True, encoding="utf-8", errors="replace",
                    env={**{key: value for key, value in os.environ.items()
                            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
                                               "COMSPEC", "PATHEXT", "LOCALAPPDATA",
                                               "APPDATA", "USERPROFILE"}},
                         "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
            except subprocess.TimeoutExpired:
                findings.append({"error": "Focused isolated tests timed out."})
            except (OSError, ValueError) as error:
                findings.append({"error": "Focused isolated tests could not run: " + str(error)[:120]})
            else:
                tests_run = True
                returncode = completed.returncode
                tail = ((completed.stdout or "") + (completed.stderr or ""))[-2000:]
                if returncode != 0:
                    findings.append({"error": "Focused isolated tests failed."})
        return {"passed": not findings, "findings": findings,
                "tests_run": tests_run, "returncode": returncode, "tail": tail}

    def _save_candidate_status(self, workspace, record, result):
        record["status"] = "tested" if result["passed"] else "rejected"
        record["validation"] = {key: result[key] for key in
                                ("passed", "tests_run", "returncode", "tail")}
        record["updated"] = round(self.clock(), 3)
        atomic_write(workspace.root / "candidate.json", json.dumps(record).encode())
        self._audit("candidate_" + record["status"], candidate_id=record.get("candidate_id"),
                    workspace=workspace.name, target=record["target"])
        return record

    # ------------------------------------------------------------------
    # one full isolated upgrade cycle
    # ------------------------------------------------------------------
    def _record(self, project, stage, outcome, evidence=None):
        if project is None:
            return
        try:
            self.evolution.saee.record_attempt(
                project, "isolated-upgrade", stage, outcome, evidence or {})
        except Exception:
            pass

    def _prune(self):
        workspaces = self.workspaces()
        for workspace in workspaces[:max(0, len(workspaces) - MAX_CANDIDATE_WORKSPACES)]:
            shutil.rmtree(workspace.root, ignore_errors=True)

    async def run_cycle(self, goal, project="general"):
        if not isinstance(goal, str) or not 10 <= len(goal.strip()) <= 600:
            raise IsolatedUpgradeError("Describe a single upgrade goal in 10-600 characters.")
        async with self._cycle_lock:
            self._prune()
            self._audit("cycle_started", goal=goal, project=project)
            workspace = self._build(goal)
            if workspace is None:
                outcome = {"status": "needs_target",
                           "reason": "Name the SPARK module to improve for bounded autonomous changes."}
                self._record(project, "inspect", outcome["reason"])
                self._audit("cycle_" + outcome["status"], goal=goal)
                return outcome
            target = workspace.manifest["target"]
            try:
                analysis = await self.evolution.execute("analyze_repository", project, {
                    "repository": str(workspace.root), "goal": goal,
                    "reference_paths": [target, *workspace.manifest["tests"]]})
            except Exception as error:
                outcome = {"status": "generation_failed", "workspace": workspace.name,
                           "target": target, "reason": type(error).__name__ + ": " + str(error)[:120]}
                self._record(project, "analyze", "isolated analysis failed", {"error": str(error)[:120]})
                self._audit("cycle_" + outcome["status"], goal=goal, workspace=workspace.name)
                return outcome
            opportunities = analysis.get("opportunities", []) if isinstance(analysis, dict) else []
            # Never let the proposal widen the automatically selected scope.
            indexes = [i for i, item in enumerate(opportunities)
                       if isinstance(item, dict) and item.get("spark_paths") == [target]]
            if not indexes:
                outcome = {"status": "manual_review", "workspace": workspace.name, "target": target,
                           "reason": "No single-file supported upgrade."}
                self._record(project, "risk_check", "no safely scoped improvement", {"target": target})
                self._audit("cycle_" + outcome["status"], goal=goal, workspace=workspace.name)
                return outcome
            try:
                candidate = await self.evolution.execute("stage_repository_upgrade", project, {
                    "analysis_id": analysis["id"], "opportunity": indexes[0]})
            except Exception as error:
                outcome = {"status": "generation_failed", "workspace": workspace.name,
                           "target": target, "reason": type(error).__name__ + ": " + str(error)[:120]}
                self._record(project, "stage", "isolated staging failed", {"error": str(error)[:120]})
                self._audit("cycle_" + outcome["status"], goal=goal, workspace=workspace.name)
                return outcome
            changes = candidate.get("changes") if isinstance(candidate, dict) else None
            if not isinstance(candidate, dict) or candidate.get("status") != "staged":
                outcome = {"status": "manual_review", "workspace": workspace.name, "target": target,
                           "reason": "Upgrade was not staged."}
                self._audit("cycle_" + outcome["status"], goal=goal, workspace=workspace.name)
                return outcome
            originals = workspace.manifest["originals"]
            if (not isinstance(changes, list) or len(changes) != 1
                    or any(not isinstance(change, dict)
                           or set(change) != {"path", "content", "sha256"}
                           or change["path"] != target
                           or originals.get(change["path"]) != change["sha256"]
                           or not isinstance(change["content"], str)
                           or len(change["content"].encode()) > 65536 for change in changes)):
                outcome = {"status": "manual_review", "workspace": workspace.name, "target": target,
                           "reason": "Generated upgrade exceeded its selected single-file scope."}
                self._record(project, "risk_check", "unsafe isolated upgrade scope", {"target": target})
                self._audit("cycle_" + outcome["status"], goal=goal, workspace=workspace.name)
                return outcome
            record = self._apply_candidate(workspace, changes)
            record["candidate_id"] = candidate["id"]
            atomic_write(workspace.root / "candidate.json", json.dumps(record).encode())
            result = self._validate(workspace)
            record = self._save_candidate_status(workspace, record, result)
            self._record(project, "test", "isolated candidate " + record["status"],
                         {"target": target, "candidate_id": record["candidate_id"]})
            outcome = {"status": record["status"], "workspace": workspace.name,
                       "target": target, "candidate_id": record["candidate_id"],
                       "tests_run": result["tests_run"],
                       "validation": result}
            self._audit("cycle_" + record["status"], goal=goal, workspace=workspace.name,
                        candidate_id=record["candidate_id"])
            return outcome
