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


class AutoEvolution:
    def __init__(self, evolution, data_dir, *, clock=time.time):
        self.evolution = evolution
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
            "interval_minutes": self._interval() // 60,
            "max_upgrades_per_day": self.state.get("max_upgrades_per_day", MAX_UPGRADES_PER_UTC_DAY),
            "scope": "existing non-protected backend Python files only",
            "rea_mode": "discovery only (no autonomous REA tool calls)",
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
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        if self._daily_limit(day):
            self.state["last_status"] = "daily_limit"
            self._persist()
            return {"status": "daily_limit", "queued_goal": goal, "rea": rea}
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
        words = set(re.findall(r"[a-z0-9]+", goal.lower()))
        def score(name):
            tokens = set(re.findall(r"[a-z0-9]+", Path(name).stem.lower())) - {"spark"}
            return len(tokens & words)
        ranked = sorted(targets, key=lambda name: (-score(name), name))
        if not ranked or score(ranked[0]) == 0:
            self.state["last_status"] = "needs_target"
            self._persist()
            return {"status": "needs_target", "queued_goal": goal,
                    "reason": "Name the SPARK module to improve for bounded autonomous changes.", "rea": rea}
        target = ranked[0]
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
            if repair_id:
                try:
                    await self.evolution.execute("rollback_repair", project, {"id": repair_id})
                finally:
                    self.emergency_stop()
            self.state["last_status"] = "failed"
            self._persist()
            self._record(project, "test", "queued upgrade failed", {
                "target": target, "exception_type": type(error).__name__})
            return {"status": "failed", "reason": type(error).__name__,
                    "queued_goal": goal, "rea": rea}

    async def run_once(self, project="general"):
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
                if repair_id:
                    try:
                        await self.evolution.execute("rollback_repair", project, {"id": repair_id})
                    finally:
                        self.emergency_stop()
                self.state["last_status"] = "failed"
                self._persist()
                self._record(project, "test", "repair failed",
                             {"exception_type": type(error).__name__})
                return {"status": "failed", "reason": type(error).__name__, "rea": rea}

    async def start_scheduler(self):
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
