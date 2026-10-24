"""Bounded, owner-authorized automatic evolution.

The scheduler cannot grant its own permissions. It only processes local,
allowlisted Python repairs through SPARK's existing staged validation and
rollback engine. REA discovery is evidence only; REA tools are never executed
autonomously because the catalog can expose mutating operations.
"""
import ast
import asyncio
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from spark_maintenance import atomic_write
from spark_security_scan import scan_secrets


class AutoEvolutionError(ValueError):
    pass


PROTECTED = frozenset({
    "spark_trace_learning.py",
    "spark_python_tools.py", "spark_code_skills.py",
    "server.py", "spark_evolution.py", "spark_maintenance.py",
    "spark_rea.py", "spark_repo_upgrade.py", "spark_saee.py",
    "spark_auto_evolution.py", "spark_workspace_auth.py",
    "spark_security_scan.py", "spark_integrations.py",
    "spark_integrations_mcp.py", "spark_pc_tasks.py",
})
INTERVAL_SECONDS = 3600
MAX_UPGRADES_PER_UTC_DAY = 1
GIT_INSPECTION_TIMEOUT = 30


def rank_targets(targets, goal):
    """Rank maintenance-eligible relative paths by goal keyword overlap.

    Returns the best matching relative path, or None when no eligible
    target shares a keyword with the goal.
    """
    words = set(re.findall(r"[a-z0-9]+", goal.lower()))
    def score(name):
        tokens = set(re.findall(r"[a-z0-9]+", Path(name).stem.lower())) - {"spark"}
        return len(tokens & words)
    ranked = sorted(targets, key=lambda name: (-score(name), name))
    return ranked[0] if ranked and score(ranked[0]) else None


class GitSafetyGate:
    """Read-only Git inspection used as an activation safety gate.

    The gate never mutates the working tree: it only runs `git rev-parse` and
    `git status --porcelain=v1`, so every existing modified and untracked file
    is preserved exactly as the owner left it. Any Git inspection failure
    blocks autonomous activation (fail closed) because an unverifiable work
    tree could hide uncommitted owner changes.
    """

    def __init__(self, root, *, runner=None, timeout=GIT_INSPECTION_TIMEOUT):
        self.root = Path(root)
        self._runner = runner
        self.timeout = timeout

    def _run(self, argv):
        if self._runner is not None:
            runner = self._runner
        else:
            git = shutil.which("git")
            if not git:
                raise AutoEvolutionError(
                    "git is unavailable; the work tree cannot be verified and "
                    "autonomous activation stays blocked.")
            runner = lambda argv, **kwargs: subprocess.run(
                [git, *argv], **kwargs)
        try:
            completed = runner(argv, cwd=self.root, timeout=self.timeout,
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise AutoEvolutionError(
                "Git inspection timed out; the work-tree state cannot be trusted.") from None
        except (OSError, ValueError) as error:
            raise AutoEvolutionError("Git inspection could not run: " + str(error)[:120]) from None
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip().splitlines()
            raise AutoEvolutionError("Git inspection failed: " +
                                     (detail[0] if detail else "unknown git error")[:150])
        return completed.stdout

    def inspect(self):
        """Return {"dirty": bool, "paths": [...]} or fail closed.

        Raises AutoEvolutionError whenever a clean work tree cannot be proven.
        Dirty means any staged, unstaged, unmerged or untracked path exists.
        """
        if not self.root.is_dir():
            raise AutoEvolutionError("Repository root is missing; the Git state cannot be verified.")
        inside = (self._run(["rev-parse", "--is-inside-work-tree"]) or "").strip()
        if inside != "true":
            raise AutoEvolutionError("The target is not a verified Git work tree.")
        output = self._run(["status", "--porcelain=v1", "-uall"]) or ""
        paths = []
        for line in output.replace("\r\n", "\n").split("\n"):
            if not line:
                continue
            # Porcelain v1 records are `XY <path>`; anything else is unparseable.
            if len(line) < 4 or line[2] != " ":
                raise AutoEvolutionError("Unexpected Git status output; refusing to proceed.")
            paths.append(line[3:].lstrip('"').rstrip('"')[:200])
        return {"dirty": bool(paths), "paths": paths}


class AutoEvolution:
    def __init__(self, evolution, data_dir, *, clock=time.time, git_gate=None,
                 isolated=None):
        # `evolution=None` builds a detached, owner-side controller for
        # configuration, status and emergency stop. Upgrades stay blocked
        # until a real engine is attached (see run_once).
        self.evolution = evolution
        self.isolated = isolated
        self.git_gate = git_gate
        if self.git_gate is None and evolution is not None:
            try:
                self.git_gate = GitSafetyGate(evolution.maintenance.root)
            except AttributeError:
                self.git_gate = None
        self.clock = clock
        self.root = Path(data_dir).resolve() / "saee"
        self.file = self.root / "autonomy-policy.json"
        self.lock = asyncio.Lock()
        self.scheduler = None
        self.notify = None
        self.state = {
            "enabled": False,
            "allow_model_source": False,
            "last_cycle": 0,
            "last_upgrade_day": "",
            "last_status": "not_run",
            "queued_goal": "",
            "interval_seconds": INTERVAL_SECONDS,
            "max_upgrades_per_day": MAX_UPGRADES_PER_UTC_DAY,
        }
        if self.file.exists():
            if self.file.is_symlink() or self.root.is_symlink():
                raise AutoEvolutionError("Linked autonomy settings are prohibited.")
            try:
                data = json.loads(self.file.read_text(encoding="utf-8"))
                if (type(data) is dict and
                        type(data.get("enabled")) is bool and
                        type(data.get("allow_model_source")) is bool and
                        type(data.get("last_cycle", 0)) in (float, int) and
                        isinstance(data.get("last_upgrade_day", ""), str)):
                    self.state.update({key: data[key] for key in self.state if key in data})
                else:
                    raise ValueError()
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                # Fail closed if authorization storage cannot be validated.
                self.state["enabled"] = False
                self.state["allow_model_source"] = False

        # Older running backends rewrite autonomy-policy.json without these fields.
        # Keep explicitly chosen limits separately so an older writer cannot erase them.
        limits_file=self.root/'background-limits.json'
        if limits_file.exists() and not limits_file.is_symlink():
            try:
                limits=json.loads(limits_file.read_text(encoding='utf-8'))
                interval=limits.get('interval_seconds');maximum=limits.get('max_upgrades_per_day')
                if type(interval)is int and 60<=interval<=86400 and type(maximum)is int and maximum in (0,1):
                    self.state.update(interval_seconds=interval,max_upgrades_per_day=maximum)
            except (OSError,ValueError,TypeError):pass

    def _persist(self):
        if self.root.is_symlink() or self.file.is_symlink():
            raise AutoEvolutionError("Autonomy settings cannot be symbolic links.")
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write(self.file, json.dumps(self.state, sort_keys=True).encode("utf-8"))

    def status(self):
        return {
            **self.state,
            "running": self.lock.locked(),
            "engine_attached": self.evolution is not None,
            "git_gate_attached": self.git_gate is not None,
            "isolated_upgrades": self.isolated is not None,
            "interval_minutes": self._interval() // 60,
            "max_upgrades_per_day": self.state.get("max_upgrades_per_day", MAX_UPGRADES_PER_UTC_DAY),
            "scope": "existing non-protected backend Python files only",
            "rea_mode": "discovery only (no autonomous REA tool calls)",
            "git_gate": "activation requires a verified clean Git work tree (read-only inspection)",
            "review_required": "new files, dependencies, security, external data or PC operations",
        }

    def _interval(self):
        value=self.state.get('interval_seconds',INTERVAL_SECONDS)
        return value if type(value)is int and 60<=value<=86400 else INTERVAL_SECONDS

    def set_background_limits(self,interval_seconds=300,max_upgrades_per_day=0):
        if type(interval_seconds)is not int or not 60<=interval_seconds<=86400 or max_upgrades_per_day not in (0,1):
            raise AutoEvolutionError('Choose a valid interval and zero (no daily cap) or one daily upgrade.')
        self.state.update(interval_seconds=interval_seconds,max_upgrades_per_day=max_upgrades_per_day)
        limits_file=self.root/'background-limits.json'
        if limits_file.is_symlink():raise AutoEvolutionError('Linked background limits prohibited.')
        atomic_write(limits_file,json.dumps({'interval_seconds':interval_seconds,'max_upgrades_per_day':max_upgrades_per_day}).encode())
        self._persist();return self.status()

    def _daily_limit(self,day):
        return self.state.get('max_upgrades_per_day',1)!=0 and self.state['last_upgrade_day']==day

    def configure(self, *, enabled, allow_model_source):
        if type(enabled) is not bool or type(allow_model_source) is not bool:
            raise AutoEvolutionError("Autonomy settings must be booleans.")
        self.state["enabled"] = enabled
        self.state["allow_model_source"] = enabled and allow_model_source
        self._persist()
        return self.status()

    def emergency_stop(self):
        return self.configure(enabled=False, allow_model_source=False)

    def queue_goal(self, goal):
        if not isinstance(goal, str) or not 10 <= len(goal.strip()) <= 600:
            raise AutoEvolutionError("Describe a single upgrade goal in 10–600 characters.")
        if self.state["queued_goal"]:
            raise AutoEvolutionError("An upgrade goal is already queued. Run or cancel it first.")
        self.state["queued_goal"] = goal.strip()
        self._persist()
        return self.status()

    def cancel_goal(self):
        self.state["queued_goal"] = ""
        self._persist()
        return self.status()

    def _ensure_active(self):
        if not self.state["enabled"] or not self.state["allow_model_source"]:
            raise AutoEvolutionError("Autonomous model-assisted changes were stopped.")

    def _git_gate_result(self, phase, project, rea):
        """Return a blocked response dict, or None when the work tree is clean.

        Dirty trees block the cycle without touching the queued goal, stored
        limits or the owner's files. When Git inspection itself cannot be
        trusted, the cycle also fails closed.
        """
        try:
            state = self.git_gate.inspect()
        except AutoEvolutionError as error:
            self.state["last_status"] = "git_unavailable"
            self._persist()
            self._record(project, "risk_check", "git inspection failed; upgrade blocked",
                         {"phase": phase, "reason": str(error)[:120]})
            return {"status": "git_unavailable", "phase": phase,
                    "reason": str(error)[:160], "rea": rea}
        if not state["dirty"]:
            return None
        self.state["last_status"] = "git_dirty"
        self._persist()
        self._record(project, "risk_check", "git work tree not clean; upgrade blocked",
                     {"phase": phase, "paths": state["paths"][:5]})
        return {"status": "git_dirty", "phase": phase,
                "reason": "Commit or review local Git changes before autonomous activation; "
                          "existing modified and untracked files are never touched.",
                "paths": state["paths"][:10], "rea": rea}

    def _require_clean_git(self, phase):
        """Recheck the work tree immediately before activation (fail closed)."""
        state = self.git_gate.inspect()
        if state["dirty"]:
            raise AutoEvolutionError(
                "Git safety gate: the work tree changed before activation (%s); "
                "nothing is activated and owner edits are preserved." % phase)

    def _diagnose_syntax(self):
        root = self.evolution.maintenance.root
        backend = root / "backend"
        findings = []
        for source in sorted(backend.glob("*.py"))[:600]:
            if source.is_symlink() or not source.is_file():
                continue
            try:
                ast.parse(source.read_text(encoding="utf-8-sig"), filename=source.name)
            except (SyntaxError, UnicodeError) as err:
                relative = "backend/" + source.name
                findings.append({
                    "path": relative,
                    "error": str(err)[:180],
                    "eligible": source.name not in PROTECTED,
                })
        return findings

    def _record(self, project, stage, outcome, evidence=None):
        if self.notify:
            try:self.notify({"phase":stage,"name":outcome[:120],"project":project})
            except Exception:pass
        if self.evolution is None:
            return
        try:
            self.evolution.saee.record_attempt(
                project, "autonomy", stage, outcome, evidence or {})
        except Exception:
            # A broken ledger cannot suppress emergency rollback.
            pass

    async def _run_goal(self, project, rea, now):
        goal = self.state["queued_goal"]
        if not self.state["allow_model_source"]:
            self.state["last_status"] = "awaiting_model_permission"
            self._persist()
            return {"status": "awaiting_model_permission", "queued_goal": goal, "rea": rea}
        if self.isolated is not None:
            return await self._run_goal_isolated(project, goal, rea, now)
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        if self._daily_limit(day):
            self.state["last_status"] = "daily_limit"
            self._persist()
            return {"status": "daily_limit", "queued_goal": goal, "rea": rea}
        gate = self._git_gate_result("queued_goal", project, rea)
        if gate:
            return {**gate, "queued_goal": goal}
        root = self.evolution.maintenance.root
        targets = []
        for path in sorted((root / "backend").glob("*.py")):
            if path.name in PROTECTED or path.is_symlink():
                continue
            name = "backend/" + path.name
            if hasattr(self.evolution.maintenance, "_target"):
                try:
                    self.evolution.maintenance._target(name)
                except Exception:
                    continue
            targets.append(name)
        target = rank_targets(targets, goal)
        if target is None:
            self.state["last_status"] = "needs_target"
            self._persist()
            return {"status": "needs_target", "queued_goal": goal,
                    "reason": "Name the SPARK module to improve for bounded autonomous changes.", "rea": rea}
        source = root / target
        if not source.is_file() or scan_secrets(source.read_text(encoding="utf-8-sig"), target):
            self.state["last_status"] = "manual_review"
            self._persist()
            return {"status": "manual_review", "reason": "Source is unavailable or sensitive.", "rea": rea}
        repair_id = None
        try:
            self._ensure_active()
            analysis = await self.evolution.execute("analyze_repository", project, {
                "repository": str(root), "goal": goal, "reference_paths": [target]})
            opportunities = analysis.get("opportunities", []) if isinstance(analysis, dict) else []
            # Never allow the model to widen the automatically selected source scope.
            indexes = [i for i, item in enumerate(opportunities)
                       if isinstance(item, dict) and item.get("spark_paths") == [target]]
            if not indexes:
                self.state["last_status"] = "manual_review"
                self._persist()
                self._record(project, "risk_check", "no safely scoped improvement", {"target": target})
                return {"status": "manual_review", "reason": "No single-file supported upgrade.",
                        "queued_goal": goal, "rea": rea}
            self._ensure_active()
            candidate = await self.evolution.execute("stage_repository_upgrade", project, {
                "analysis_id": analysis["id"], "opportunity": indexes[0]})
            if not isinstance(candidate, dict) or candidate.get("status") != "staged":
                raise AutoEvolutionError("Repository upgrade was not staged.")
            changes = candidate.get("changes")
            if changes is not None and (len(changes) != 1 or
                                        any(x.get("path") != target for x in changes)):
                raise AutoEvolutionError("Upgrade modified files outside the selected scope.")
            self._ensure_active()
            tested = await self.evolution.execute("test_repair_candidate", project, {
                "id": candidate["id"], "approved": True})
            if not isinstance(tested, dict) or tested.get("status") != "tested":
                raise AutoEvolutionError("Repository candidate did not pass staged tests.")
            self._ensure_active()
            self._require_clean_git("queued_goal")
            applied = await self.evolution.execute("activate_repair_candidate", project, {
                "id": candidate["id"], "approved": True})
            if not isinstance(applied, dict) or applied.get("status") != "applied":
                raise AutoEvolutionError("Repository candidate did not activate.")
            repair_id = applied["id"]
            self._ensure_active()
            self.state["last_upgrade_day"] = day
            self._persist()
            result = await asyncio.to_thread(self.evolution.maintenance.detect)
            if not result.get("healthy"):
                await self.evolution.execute("rollback_repair", project, {"id": repair_id})
                self.emergency_stop()
                self.state["last_status"] = "rolled_back"
                self._persist()
                self._record(project, "monitor", "automatic upgrade rolled back",
                             {"repair_id": repair_id})
                return {"status": "rolled_back", "repair_id": repair_id, "rea": rea}
            self.state["queued_goal"] = ""
            self.state["last_status"] = "applied"
            self._persist()
            self._record(project, "verify", "queued upgrade applied and verified",
                         {"target": target, "repair_id": repair_id})
            return {"status": "applied", "target": target, "repair_id": repair_id,
                    "restart_required": True, "rea": rea}
        except Exception as error:
            self.emergency_stop()
            if repair_id:
                try:
                    await self.evolution.execute("rollback_repair", project, {"id": repair_id})
                finally:
                    self.emergency_stop()
            self.state["last_status"] = "failed"
            self._persist()
            self._record(project, "test", "queued upgrade failed", {
                "target": target, "exception_type": type(error).__name__,
                "message": str(error)[:120]})
            return {"status": "failed", "reason": type(error).__name__,
                    "queued_goal": goal, "rea": rea}

    async def _run_goal_isolated(self, project, goal, rea, now):
        """Queued-goal cycle through an isolated D: workspace.

        Generation, inspection and focused testing happen in the throw-away
        workspace, never in the live tree. Promotion is attempted only when
        the Git Safety Gate proves a clean work tree and the daily quota
        allows a live activation; otherwise the candidate stays staged in
        isolation for later promotion.
        """
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        try:
            cycle = await self.isolated.run_cycle(goal, project)
        except Exception as error:
            self.emergency_stop()
            self.state["last_status"] = "failed"
            self._persist()
            self._record(project, "test", "isolated upgrade cycle failed", {
                "exception_type": type(error).__name__, "message": str(error)[:120]})
            return {"status": "failed", "reason": type(error).__name__,
                    "queued_goal": goal, "isolated": True, "rea": rea}
        if cycle["status"] != "tested":
            status = {"rejected": "isolated_rejected",
                      "generation_failed": "isolated_generation_failed",
                      }.get(cycle["status"], cycle["status"])
            if cycle["status"] in ("needs_target", "manual_review"):
                # keep the goal queued: the owner can reword it
                self.state["last_status"] = status
                self._persist()
            else:
                self.state["queued_goal"] = ""
                self.state["last_status"] = status
                self._persist()
            return {**cycle, "status": status, "rea": rea}
        # Fair promotion order: oldest fully validated candidate first; the
        # candidate just staged in this cycle is only promoted when nothing
        # older is waiting.
        promotion_record = (self.isolated.held()
                            or self.isolated.candidate_record(cycle.get("candidate_id"))
                            or cycle)
        try:
            promotion = await self._promote_candidate(project, promotion_record, day)
        except Exception as error:
            self.emergency_stop()
            self.state["last_status"] = "failed"
            self._persist()
            self._record(project, "test", "isolated promotion failed", {
                "candidate_id": cycle.get("candidate_id"),
                "exception_type": type(error).__name__, "message": str(error)[:120]})
            promotion = {"status": "failed", "reason": type(error).__name__,
                         "candidate_id": cycle.get("candidate_id")}
        mapping = {"applied": "applied", "rolled_back": "rolled_back",
                   "stale": "stale_candidate", "isolated_staged": "isolated_staged",
                   "isolated_ready": "isolated_ready",
                   "git_unavailable": "git_unavailable"}
        self.state["queued_goal"] = ""
        self.state["last_status"] = mapping.get(promotion["status"], "failed")
        self._persist()
        return {**promotion, "isolated": True, "rea": rea}

    async def _promote_held(self, project, now):
        """Promote the oldest validated isolated candidate, when possible.

        Returns None when nothing is staged or the controller is not in the
        continuous isolated mode; otherwise returns an outcome dict.
        """
        held = self.isolated.held()
        if held is None:
            return None
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        try:
            outcome = await self._promote_candidate(project, held, day)
        except Exception as error:
            self.emergency_stop()
            self.state["last_status"] = "failed"
            self._persist()
            self._record(project, "test", "isolated promotion failed", {
                "exception_type": type(error).__name__, "message": str(error)[:120]})
            return {"status": "failed", "reason": type(error).__name__, "isolated": True}
        mapping = {"applied": "applied", "rolled_back": "rolled_back",
                   "stale": "stale_candidate", "isolated_staged": "isolated_staged",
                   "isolated_ready": "isolated_ready",
                   "git_unavailable": "git_unavailable"}
        self.state["last_status"] = mapping.get(outcome["status"], "failed")
        self._persist()
        self._record(project, "verify", "isolated promotion attempt", {
            "candidate_id": held.get("candidate_id"), "outcome": outcome["status"]})
        return {**outcome, "isolated": True}

    async def _promote_candidate(self, project, held, day):
        """Promote one fully validated isolated candidate into the live tree.

        A dirty live work tree keeps the candidate in isolation — no owner
        file is staged, committed or reverted. Quota exhaustion defers the
        promotion. Before activation the recorded source hashes are compared
        against the live files, so a concurrent owner edit is detected and
        never overwritten. Failures roll back through the existing repair
        engine.
        """
        candidate_id = held.get("candidate_id")
        try:
            gate_state = self.git_gate.inspect()
        except AutoEvolutionError as error:
            return {"status": "git_unavailable", "reason": str(error)[:160],
                    "candidate_id": candidate_id}
        if gate_state["dirty"]:
            return {"status": "isolated_staged", "candidate_id": candidate_id,
                    "target": held.get("target"),
                    "reason": "Live work tree has uncommitted owner changes; "
                              "the validated candidate stays in isolation.",
                    "paths": gate_state["paths"][:10]}
        if self._daily_limit(day):
            return {"status": "isolated_ready", "candidate_id": candidate_id,
                    "target": held.get("target"),
                    "reason": "Daily live-promotion quota exhausted; "
                              "the candidate stays staged in isolation."}
        mismatches = self.isolated.staleness(held)
        if mismatches:
            self.isolated.mark(candidate_id, "stale",
                               "live files changed since generation (%s); regenerate"
                               % ", ".join(mismatches)[:200])
            return {"status": "stale", "candidate_id": candidate_id,
                    "target": held.get("target"), "paths": mismatches,
                    "reason": "Concurrent modification detected; nothing was applied."}
        repair_id = None
        self._ensure_active()
        tested = await self.evolution.execute("test_repair_candidate", project,
                                              {"id": candidate_id, "approved": True})
        if not isinstance(tested, dict) or tested.get("status") != "tested":
            self.isolated.mark(candidate_id, "failed", "live regression gate rejected the candidate")
            raise AutoEvolutionError("Live regression gate rejected the isolated candidate.")
        self._ensure_active()
        self._require_clean_git("isolated_promotion")
        applied = await self.evolution.execute("activate_repair_candidate", project,
                                               {"id": candidate_id, "approved": True})
        if not isinstance(applied, dict) or applied.get("status") != "applied":
            self.isolated.mark(candidate_id, "failed", "live activation failed")
            raise AutoEvolutionError("Isolated candidate did not activate.")
        repair_id = applied["id"]
        self._ensure_active()
        self.state["last_upgrade_day"] = day
        self._persist()
        result = await asyncio.to_thread(self.evolution.maintenance.detect)
        if not result.get("healthy"):
            await self.evolution.execute("rollback_repair", project, {"id": repair_id})
            self.emergency_stop()
            self.isolated.mark(candidate_id, "rolled_back", "post-activation health check failed")
            self._record(project, "monitor", "isolated promotion rolled back",
                         {"repair_id": repair_id})
            return {"status": "rolled_back", "repair_id": repair_id,
                    "candidate_id": candidate_id, "target": held.get("target")}
        self.isolated.mark(candidate_id, "promoted", "")
        self._record(project, "verify", "isolated candidate promoted",
                     {"target": held.get("target"), "repair_id": repair_id})
        return {"status": "applied", "target": held.get("target"),
                "repair_id": repair_id, "candidate_id": candidate_id,
                "restart_required": True}

    async def run_once(self, project="general"):
        if self.evolution is None:
            raise AutoEvolutionError(
                "No evolution engine is attached; a detached AutoEvolution only "
                "supports configuration, status and emergency stop.")
        if self.git_gate is None:
            raise AutoEvolutionError(
                "No functioning Git Safety Gate is attached; upgrades are blocked.")
        self.evolution.workspace.skills._file(project)
        if not self.state["enabled"]:
            return {"status": "disabled"}
        if self.lock.locked():
            return {"status": "busy"}
        async with self.lock:
            now = self.clock()
            if now - self.state["last_cycle"] < self._interval():
                return {"status": "cooldown", "next_eligible_at": self.state["last_cycle"] + self._interval()}
            self.state["last_cycle"] = now
            self.state["last_status"] = "inspecting"
            self._persist()
            rea = {"available": False, "status": "not_configured"}
            try:
                # REA is only queried for its catalog. Tool descriptions and
                # untrusted repository contents cannot authorize execution.
                catalog = await asyncio.wait_for(
                    self.evolution.rea.request("rea_discover", {}), timeout=30)
                rea = {"available": isinstance(catalog, list),
                       "tools_discovered": len(catalog) if isinstance(catalog, list) else 0,
                       "status": "connected" if isinstance(catalog, list) else "unexpected_catalog"}
            except Exception:
                rea["status"] = "unavailable"
            findings = self._diagnose_syntax()
            if not findings and self.state["queued_goal"]:
                return await self._run_goal(project, rea, now)
            if not findings:
                if self.isolated is not None and self.state["allow_model_source"]:
                    outcome = await self._promote_held(project, now)
                    if outcome is not None:
                        return {**outcome, "scope": "isolated promotion", "rea": rea}
                self.state["last_status"] = "healthy"
                self._persist()
                self._record(project, "inspect", "syntax checks passed",
                             {"rea_connected": rea["available"]})
                return {"status": "healthy", "scope": "static Python syntax only", "rea": rea,
                        "source_edits": 0}
            eligible = [f for f in findings if f["eligible"]]
            if len(findings) != 1 or len(eligible) != 1:
                self.state["last_status"] = "manual_review"
                self._persist()
                self._record(project, "risk_check", "manual review required",
                             {"paths": [f["path"] for f in findings]})
                return {"status": "manual_review", "findings": findings, "rea": rea}
            if not self.state["allow_model_source"]:
                self.state["last_status"] = "awaiting_model_permission"
                self._persist()
                return {"status": "awaiting_model_permission", "findings": findings, "rea": rea}
            utc_day = time.strftime("%Y-%m-%d", time.gmtime(now))
            if self._daily_limit(utc_day):
                self.state["last_status"] = "daily_limit"
                self._persist()
                return {"status": "daily_limit", "findings": findings, "rea": rea}
            gate = self._git_gate_result("defect_repair", project, rea)
            if gate:
                return {**gate, "findings": findings}
            path = eligible[0]["path"]
            # Route through the same path-allowlist and sensitivity scan as
            # the founder-operated maintenance system.
            target = self.evolution.maintenance._target(path) if hasattr(
                self.evolution.maintenance, "_target") else self.evolution.maintenance.root / path
            if scan_secrets(target.read_text(encoding="utf-8-sig"), path):
                self.state["last_status"] = "manual_review"
                self._persist()
                return {"status": "manual_review", "reason": "potential secret in target", "rea": rea}
            issue = "Repair the Python syntax error in " + path + ": " + eligible[0]["error"]
            repair_id = None
            try:
                self._ensure_active()
                candidate = await self.evolution.execute("heal_sources", project,
                                                         {"paths": [path], "issue": issue})
                if not isinstance(candidate, dict) or candidate.get("status") != "staged":
                    raise AutoEvolutionError("Candidate was not staged.")
                self._ensure_active()
                tested = await self.evolution.execute("test_repair_candidate", project,
                                                     {"id": candidate["id"], "approved": True})
                if not isinstance(tested, dict) or tested.get("status") != "tested":
                    raise AutoEvolutionError("Candidate did not pass staged tests.")
                self._ensure_active()
                self._require_clean_git("defect_repair")
                applied = await self.evolution.execute("activate_repair_candidate", project,
                                                      {"id": candidate["id"], "approved": True})
                if not isinstance(applied, dict) or applied.get("status") != "applied":
                    raise AutoEvolutionError("Activation did not confirm success.")
                repair_id = applied["id"]
                self._ensure_active()
                self.state["last_upgrade_day"] = utc_day
                self._persist()
                # Verify the actual live tree; revert if the post-apply
                # regression gate detects an issue. This is NOT an OS sandbox.
                health = await asyncio.to_thread(self.evolution.maintenance.detect)
                if not health.get("healthy"):
                    await self.evolution.execute("rollback_repair", project, {"id": repair_id})
                    self.emergency_stop()
                    self.state["last_status"] = "rolled_back"
                    self._persist()
                    self._record(project, "monitor", "automatic rollback", {"repair_id": repair_id})
                    return {"status": "rolled_back", "repair_id": repair_id, "rea": rea}
                self.state["last_status"] = "applied"
                self._persist()
                self._record(project, "verify", "applied and verified", {"repair_id": repair_id})
                return {"status": "applied", "repair_id": repair_id,
                        "restart_required": True, "rea": rea}
            except Exception as error:
                self.emergency_stop()
                if repair_id:
                    try:
                        await self.evolution.execute("rollback_repair", project, {"id": repair_id})
                    finally:
                        self.emergency_stop()
                self.state["last_status"] = "failed"
                self._persist()
                self._record(project, "test", "repair failed",
                             {"exception_type": type(error).__name__,
                              "message": str(error)[:120]})
                return {"status": "failed", "reason": type(error).__name__, "rea": rea}

    async def start_scheduler(self):
        if self.evolution is None:
            raise AutoEvolutionError(
                "Autonomous scheduling requires an attached evolution engine; "
                "a detached AutoEvolution only supports configuration, status "
                "and emergency stop.")
        if self.scheduler and not self.scheduler.done():
            return
        self.scheduler = asyncio.create_task(self._schedule())

    async def _schedule(self):
        while True:
            await asyncio.sleep(self._interval())
            if self.state["enabled"]:
                try:
                    await self.run_once("general")
                except Exception:
                    self.state["last_status"] = "scheduler_error"
                    self._persist()

    async def stop_scheduler(self):
        if self.scheduler:
            self.scheduler.cancel()
            await asyncio.gather(self.scheduler, return_exceptions=True)
            self.scheduler = None
