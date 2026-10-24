"""Autonomous evolution: persistent authorization, controlled cycles and rollback."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_auto_evolution import AutoEvolution, AutoEvolutionError, GitSafetyGate


CLEAN_TREE = {"dirty": False, "paths": []}


class GateStub:
    """Offline replacement for GitSafetyGate returning canned inspection states.

    States may be a dict/exception reused forever, or several states consumed
    in order for one call each (the last one repeats).
    """
    def __init__(self, *states):
        self.queue = list(states)
        self.calls = 0
    def inspect(self):
        self.calls += 1
        state = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        if isinstance(state, Exception):
            raise state
        return state



class FakeSkills:
    def _file(self, project):
        if project != "general":
            raise ValueError("Unknown project")


class FakeMaintenance:
    def __init__(self, root):
        self.root = root
        self.healthy = True
    def detect(self):
        return {"healthy": self.healthy, "findings": [] if self.healthy else [{"error": "smoke test"}]}


class FakeRea:
    def __init__(self):
        self.calls = 0
    async def request(self, action, payload):
        self.calls += 1
        return [{"name": "inspect", "description": "read-only"}]


class FakeSaee:
    def __init__(self):
        self.events = []
    def record_attempt(self, project, request_id, stage, outcome, evidence=None):
        self.events.append((stage, outcome))


class FakeEvolution:
    def __init__(self, root):
        self.maintenance = FakeMaintenance(root)
        self.workspace = type("Workspace", (), {"skills": FakeSkills()})()
        self.rea = FakeRea()
        self.saee = FakeSaee()
        self.actions = []
    async def execute(self, action, project, payload):
        self.actions.append((action, payload))
        if action == "analyze_repository":
            return {"id": "b" * 24, "opportunities": [
                {"spark_paths": ["backend/calculator.py"], "verification": "calculator behavior"}]}
        if action == "stage_repository_upgrade":
            return {"id": "f" * 24, "status": "staged",
                    "changes": [{"path": "backend/calculator.py"}]}
        if action == "heal_sources":
            return {"id": "f" * 24, "status": "staged"}
        if action == "test_repair_candidate":
            return {"id": payload["id"], "status": "tested"}
        if action == "activate_repair_candidate":
            return {"id": "a" * 24, "status": "applied"}
        if action == "rollback_repair":
            return {"status": "rolled_back"}
        raise AssertionError(action)


class AutoEvolutionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        (self.root / "backend").mkdir(parents=True)
        self.source = self.root / "backend" / "calculator.py"
        self.source.write_text("value=3\n", encoding="utf-8")
        self.engine = FakeEvolution(self.root)
        self.time = [100000]
        self.git = GateStub(CLEAN_TREE)
        self.control = AutoEvolution(self.engine, Path(self.tmp.name)/"data",
                                     clock=lambda: self.time[0], git_gate=self.git)
    async def asyncTearDown(self):
        await self.control.stop_scheduler()
        self.tmp.cleanup()

    async def test_disabled_by_default_and_persistent_authorization(self):
        self.assertFalse(self.control.status()["enabled"])
        self.assertEqual((await self.control.run_once("general"))["status"], "disabled")
        self.control.configure(enabled=True, allow_model_source=False)
        self.assertTrue(AutoEvolution(self.engine, Path(self.tmp.name)/"data",
                                      git_gate=self.git).status()["enabled"])
        self.assertFalse(AutoEvolution(self.engine, Path(self.tmp.name)/"data",
                                       git_gate=self.git).status()["allow_model_source"])

    async def test_read_only_inspection_does_not_run_model_or_modify_files(self):
        self.control.configure(enabled=True, allow_model_source=False)
        result = await self.control.run_once("general")
        self.assertEqual(result["status"], "healthy")
        self.assertTrue(result["rea"]["available"])
        self.assertEqual(self.engine.actions, [])
        self.assertEqual(self.source.read_text(), "value=3\n")

    async def test_defect_without_model_consent_stages_nothing(self):
        self.source.write_text("value = (\n", encoding="utf-8")
        self.control.configure(enabled=True, allow_model_source=False)
        result = await self.control.run_once("general")
        self.assertEqual(result["status"], "awaiting_model_permission")
        self.assertEqual(self.engine.actions, [])

    async def test_authorized_repair_tests_activates_and_rate_limits(self):
        self.source.write_text("value = (\n", encoding="utf-8")
        self.control.configure(enabled=True, allow_model_source=True)
        result = await self.control.run_once("general")
        self.assertEqual(result["status"], "applied")
        self.assertEqual([a for a, _ in self.engine.actions],
                         ["heal_sources", "test_repair_candidate", "activate_repair_candidate"])
        self.assertEqual((await self.control.run_once("general"))["status"], "cooldown")
        self.time[0] += 3601
        self.assertEqual((await self.control.run_once("general"))["status"], "daily_limit")

    async def test_post_activation_failure_rolls_back_and_disables_autonomy(self):
        self.source.write_text("value = (\n", encoding="utf-8")
        self.engine.maintenance.healthy = False
        self.control.configure(enabled=True, allow_model_source=True)
        result = await self.control.run_once("general")
        self.assertEqual(result["status"], "rolled_back")
        self.assertFalse(self.control.status()["enabled"])
        self.assertEqual(self.engine.actions[-1][0], "rollback_repair")

    async def test_queued_self_upgrade_uses_existing_repository_and_release_gates(self):
        self.control.configure(enabled=True, allow_model_source=True)
        self.control.queue_goal("Improve calculator source reliability")
        outcome = await self.control.run_once("general")
        self.assertEqual(outcome["status"], "applied")
        self.assertEqual([action for action, _ in self.engine.actions],
                         ["analyze_repository", "stage_repository_upgrade",
                          "test_repair_candidate", "activate_repair_candidate"])
        self.assertEqual(self.control.status()["queued_goal"], "")

    async def test_queued_goal_never_shares_source_without_model_permission(self):
        self.control.configure(enabled=True, allow_model_source=False)
        self.control.queue_goal("Improve calculator source reliability")
        outcome = await self.control.run_once("general")
        self.assertEqual(outcome["status"], "awaiting_model_permission")
        self.assertEqual(self.engine.actions, [])
        self.assertTrue(self.control.status()["queued_goal"])

    async def test_invalid_or_overlapping_upgrade_requests_are_rejected(self):
        for bad in ("", "short", "a"*601, None):
            with self.assertRaises(AutoEvolutionError):
                self.control.queue_goal(bad)
        self.control.queue_goal("Improve calculator source reliability")
        with self.assertRaises(AutoEvolutionError):
            self.control.queue_goal("Improve another module")

    async def test_emergency_stop_while_testing_prevents_activation(self):
        self.source.write_text("value = (\n", encoding="utf-8")
        self.control.configure(enabled=True, allow_model_source=True)
        entered, release = asyncio.Event(), asyncio.Event()
        original_execute = self.engine.execute
        async def blocked_execute(action, project, payload):
            if action == "test_repair_candidate":
                entered.set()
                await release.wait()
            return await original_execute(action, project, payload)
        self.engine.execute = blocked_execute
        running = asyncio.create_task(self.control.run_once("general"))
        await asyncio.wait_for(entered.wait(), timeout=4)
        self.control.emergency_stop()
        release.set()
        result = await running
        self.assertNotEqual(result["status"], "applied")
        self.assertFalse(self.control.status()["enabled"])
        self.assertNotIn("activate_repair_candidate", [a for a, _ in self.engine.actions])

    async def test_emergency_stop_and_validation(self):
        self.control.configure(enabled=True, allow_model_source=True)
        self.control.emergency_stop()
        self.assertFalse(self.control.status()["enabled"])
        self.assertFalse(self.control.status()["allow_model_source"])
        with self.assertRaises(AutoEvolutionError):
            self.control.configure(enabled="yes", allow_model_source=True)
        with self.assertRaises(ValueError):
            await self.control.run_once("bad-project")


class BackgroundLimitsTests(unittest.TestCase):
    def test_opted_in_background_can_remove_daily_cap_and_persist_interval(self):
        with tempfile.TemporaryDirectory() as folder:
            engine=FakeEvolution(Path(folder))
            clean=GateStub(CLEAN_TREE)
            controller=AutoEvolution(engine,Path(folder)/'data',git_gate=clean)
            controller.set_background_limits(interval_seconds=300,max_upgrades_per_day=0)
            controller.configure(enabled=True,allow_model_source=True)
            controller.state['last_upgrade_day']='2026-10-21'
            self.assertFalse(controller._daily_limit('2026-10-21'))
            restored=AutoEvolution(engine,Path(folder)/'data',git_gate=GateStub(CLEAN_TREE))
            self.assertEqual(restored.status()['interval_minutes'],5)
            self.assertTrue(restored.status()['enabled'])
            self.assertEqual(restored.status()['max_upgrades_per_day'],0)
            # An older backend may rewrite the shared state without new fields.
            legacy=json.loads(controller.file.read_text());legacy.pop('interval_seconds',None);legacy.pop('max_upgrades_per_day',None)
            controller.file.write_text(json.dumps(legacy))
            after_legacy_write=AutoEvolution(engine,Path(folder)/'data').status()
            self.assertEqual(after_legacy_write['interval_minutes'],5)
            self.assertEqual(after_legacy_write['max_upgrades_per_day'],0)


class CountingGate:
    """Wraps a gate and records how many times activation checks ran."""
    def __init__(self, inner):
        self.inner = inner
        self.calls = 0
    def inspect(self):
        self.calls += 1
        return self.inner.inspect()


def hash_tree(root):
    """SHA-256 snapshot of every working file outside .git."""
    digests = {}
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        digests[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def run_git(repo, *args):
    """Fixture helper: creates throwaway repositories only (never reset/clean/checkout/stash)."""
    git = shutil.which("git")
    result = subprocess.run(
        [git, "-c", "user.name=SPARK Offline Test",
         "-c", "user.email=spark-offline-test@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60, env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"})
    if result.returncode != 0:
        raise AssertionError("git fixture failed: " + (result.stderr or "").strip())


@unittest.skipUnless(shutil.which("git"), "git binary required for offline gate tests")
class GitSafetyGateOfflineTests(unittest.IsolatedAsyncioTestCase):
    """Real-git offline coverage for the activation safety gate.

    Every repository here is a throwaway fixture; the live SPARK checkout is
    never touched by these tests.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "spark-repo"
        self.data = Path(self.tmp.name) / "data"
        (self.repo / "backend").mkdir(parents=True)
        self.source = self.repo / "backend" / "calculator.py"
        self.commit_fixture()

    def commit_fixture(self):
        run_git(self.repo, "init")
        self.source.write_text("value=1\n", encoding="utf-8")
        run_git(self.repo, "add", "backend/calculator.py")
        run_git(self.repo, "commit", "-m", "offline fixture")

    def build(self, *, gate=None, allow=True):
        engine = FakeEvolution(self.repo)
        control = AutoEvolution(engine, self.data,
                                git_gate=gate or CountingGate(GitSafetyGate(self.repo)))
        control.configure(enabled=True, allow_model_source=allow)
        return control, engine

    async def test_inspect_state_details(self):
        gate = GitSafetyGate(self.repo)
        self.assertEqual(gate.inspect(), {"dirty": False, "paths": []})
        (self.repo / "notes.txt").write_text("owner note\n", encoding="utf-8")
        state = gate.inspect()
        self.assertTrue(state["dirty"])
        self.assertIn("notes.txt", state["paths"])

    async def test_clean_repository_allows_cycle_and_rechecks_before_activation(self):
        control, engine = self.build()
        control.queue_goal("Improve calculator source reliability")
        snapshot = hash_tree(self.repo)
        outcome = await control.run_once("general")
        self.assertEqual(outcome["status"], "applied")
        # once before staging, once immediately before activation
        self.assertEqual(control.git_gate.calls, 2)
        self.assertEqual(hash_tree(self.repo), snapshot)

    async def test_unstaged_owner_edit_blocks_upgrade_and_preserves_every_file(self):
        self.source.write_text("value=2\n", encoding="utf-8")
        control, engine = self.build()
        control.set_background_limits(interval_seconds=300, max_upgrades_per_day=0)
        control.queue_goal("Improve calculator source reliability")
        snapshot = hash_tree(self.repo)
        outcome = await control.run_once("general")
        self.assertEqual(outcome["status"], "git_dirty")
        self.assertEqual(outcome["phase"], "queued_goal")
        self.assertIn("backend/calculator.py", outcome["paths"])
        self.assertEqual(engine.actions, [])
        self.assertEqual(control.state["last_status"], "git_dirty")
        status = control.status()
        # blocked, not stopped: the grant, queued goal and chosen limits survive
        self.assertTrue(status["enabled"])
        self.assertTrue(status["queued_goal"])
        self.assertEqual(status["interval_minutes"], 5)
        self.assertEqual(status["max_upgrades_per_day"], 0)
        self.assertEqual(hash_tree(self.repo), snapshot)

    async def test_staged_index_change_blocks_upgrade(self):
        self.source.write_text("value=2\n", encoding="utf-8")
        run_git(self.repo, "add", "backend/calculator.py")
        control, engine = self.build()
        control.queue_goal("Improve calculator source reliability")
        outcome = await control.run_once("general")
        self.assertEqual(outcome["status"], "git_dirty")
        self.assertEqual(engine.actions, [])

    async def test_untracked_file_blocks_upgrade_while_inspection_stays_read_only(self):
        (self.repo / "notes.txt").write_text("owner scratch\n", encoding="utf-8")
        control, engine = self.build()
        outcome = await control.run_once("general")
        # read-only inspection still reports health; only live upgrades are gated
        self.assertEqual(outcome["status"], "healthy")
        last_cycle = control.state["last_cycle"]
        control.clock = lambda: last_cycle + 4001
        control.queue_goal("Improve calculator source reliability")
        outcome = await control.run_once("general")
        self.assertEqual(outcome["status"], "git_dirty")
        self.assertIn("notes.txt", outcome["paths"])
        self.assertEqual(engine.actions, [])

    async def test_concurrent_mid_cycle_owner_edit_blocks_activation_fail_closed(self):
        control, engine = self.build()
        original_execute = engine.execute
        async def concurrent_execute(action, project, payload):
            if action == "test_repair_candidate":
                # a second actor touches the tree while SPARK is mid-cycle
                (self.repo / "scratch.txt").write_text("owner edit mid-cycle\n",
                                                       encoding="utf-8")
            return await original_execute(action, project, payload)
        engine.execute = concurrent_execute
        control.queue_goal("Improve calculator source reliability")
        outcome = await control.run_once("general")
        self.assertEqual(outcome["status"], "failed")
        actions = [action for action, _ in engine.actions]
        self.assertIn("test_repair_candidate", actions)
        # the recheck ran after staging and refused activation
        self.assertNotIn("activate_repair_candidate", actions)
        self.assertNotIn("rollback_repair", actions)
        self.assertFalse(control.status()["enabled"])
        self.assertTrue(control.status()["queued_goal"])

    async def test_git_inspection_failure_fails_closed(self):
        control, engine = self.build(
            gate=GateStub(AutoEvolutionError("git produced unreadable output")))
        control.queue_goal("Improve calculator source reliability")
        outcome = await control.run_once("general")
        self.assertEqual(outcome["status"], "git_unavailable")
        self.assertEqual(engine.actions, [])
        self.assertEqual(control.state["last_status"], "git_unavailable")
        self.assertTrue(control.status()["enabled"])

    async def test_default_gate_fails_closed_outside_a_git_repository(self):
        # An initialized repository with no commits and no verified history:
        # the gate must refuse to trust uncommitted state for activation.
        bare = Path(self.tmp.name) / "init-only"
        (bare / "backend").mkdir(parents=True)
        (bare / "backend" / "calculator.py").write_text("value=1\n", encoding="utf-8")
        run_git(bare, "init")
        gate = GitSafetyGate(bare)
        state = gate.inspect()
        self.assertTrue(state["dirty"])
        self.assertIn("backend/calculator.py", state["paths"])
        engine = FakeEvolution(bare)
        control = AutoEvolution(engine, Path(self.tmp.name) / "data", git_gate=GitSafetyGate(bare))
        control.configure(enabled=True, allow_model_source=True)
        control.queue_goal("Improve calculator source reliability")
        outcome = await control.run_once("general")
        self.assertEqual(outcome["status"], "git_dirty")
        self.assertEqual(engine.actions, [])


class GateInspectionUnitTests(unittest.TestCase):
    REAL_DIR = Path(tempfile.gettempdir())

    @staticmethod
    def _ok(stdout):
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    @staticmethod
    def _responses(*entries):
        calls = iter(entries)
        def runner(argv, **kwargs):
            return next(calls)
        return runner

    def test_clean_tree_returns_no_paths(self):
        gate = GitSafetyGate(GateInspectionUnitTests.REAL_DIR, runner=self._responses(self._ok("true\n"), self._ok("")))
        self.assertEqual(gate.inspect(), {"dirty": False, "paths": []})

    def test_detects_unstaged_untracked_and_unmerged_states(self):
        gate = GitSafetyGate(GateInspectionUnitTests.REAL_DIR, runner=self._responses(
            self._ok("true\n"),
            self._ok(" M backend/spark.py\n?? notes.txt\nUU merge.txt\n")))
        state = gate.inspect()
        self.assertTrue(state["dirty"])
        self.assertEqual(state["paths"], ["backend/spark.py", "notes.txt", "merge.txt"])

    def test_unexpected_status_output_fails_closed(self):
        gate = GitSafetyGate(GateInspectionUnitTests.REAL_DIR, runner=self._responses(
            self._ok("true\n"), self._ok("garbage line")))
        with self.assertRaises(AutoEvolutionError):
            gate.inspect()

    def test_not_a_worktree_fails_closed(self):
        gate = GitSafetyGate(GateInspectionUnitTests.REAL_DIR, runner=self._responses(
            self._ok("false\n"), self._ok("")))
        with self.assertRaises(AutoEvolutionError):
            gate.inspect()

    def test_nonzero_exit_fails_closed(self):
        def runner(argv, **kwargs):
            return types.SimpleNamespace(returncode=128, stdout="", stderr="fatal: bad repository")
        with self.assertRaises(AutoEvolutionError):
            GitSafetyGate(GateInspectionUnitTests.REAL_DIR, runner=runner).inspect()

    def test_inspection_timeout_fails_closed(self):
        def runner(argv, **kwargs):
            raise subprocess.TimeoutExpired("git", timeout=30)
        with self.assertRaises(AutoEvolutionError):
            GitSafetyGate(GateInspectionUnitTests.REAL_DIR, runner=runner).inspect()

    def test_missing_git_executable_fails_closed(self):
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(AutoEvolutionError):
                GitSafetyGate(GateInspectionUnitTests.REAL_DIR).inspect()

    def test_missing_repository_root_fails_closed(self):
        missing = Path(tempfile.gettempdir()) / "spark-missing-no-such-dir-zz"
        with self.assertRaises(AutoEvolutionError):
            GitSafetyGate(missing).inspect()


class DetachedConstructorTests(unittest.IsolatedAsyncioTestCase):
    """AutoEvolution(None, data_dir) supports owner-side operations only.

    Configuration, status and emergency stop must work without a live
    engine. Upgrade execution stays blocked: no engine action and no gate
    inspection may run from a detached controller.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"

    def test_status_and_persistent_configuration_without_engine(self):
        control = AutoEvolution(None, self.data)
        status = control.status()
        self.assertFalse(status["enabled"])
        self.assertFalse(status["engine_attached"])
        control.configure(enabled=True, allow_model_source=False)
        restored = AutoEvolution(None, self.data).status()
        self.assertTrue(restored["enabled"])
        self.assertFalse(restored["allow_model_source"])
        self.assertFalse(restored["engine_attached"])

    def test_detached_emergency_stop_persists(self):
        control = AutoEvolution(None, self.data)
        control.configure(enabled=True, allow_model_source=True)
        status = control.emergency_stop()
        self.assertFalse(status["enabled"])
        self.assertFalse(status["allow_model_source"])
        restored = AutoEvolution(None, self.data)
        self.assertFalse(restored.status()["enabled"])
        self.assertFalse(restored.status()["allow_model_source"])

    async def test_upgrade_execution_refused_without_engine_or_gate(self):
        control = AutoEvolution(None, self.data)
        control.configure(enabled=True, allow_model_source=True)
        control.queue_goal("Improve calculator source reliability")
        with self.assertRaises(AutoEvolutionError):
            await control.run_once("general")
        with self.assertRaises(AutoEvolutionError):
            await control.start_scheduler()

    async def test_detached_execution_never_inspects_git_or_persists_side_effects(self):
        counting = CountingGate(GateStub(CLEAN_TREE))
        control = AutoEvolution(None, self.data, git_gate=counting)
        control.configure(enabled=True, allow_model_source=True)
        with self.assertRaises(AutoEvolutionError):
            await control.run_once("general")
        self.assertEqual(counting.calls, 0)

    async def test_detached_authorization_is_inherited_by_later_engine(self):
        control = AutoEvolution(None, self.data)
        control.configure(enabled=True, allow_model_source=True)
        attached = AutoEvolution(FakeEvolution(Path(self.tmp.name) / "repo"), self.data)
        status = attached.status()
        self.assertTrue(status["enabled"])
        self.assertTrue(status["allow_model_source"])
        self.assertTrue(status["engine_attached"])

    async def test_engine_without_functioning_gate_cannot_execute(self):
        # An engine attached over an unverifiable directory fails closed at
        # gate inspection: no upgrade is executed.
        engine = FakeEvolution(Path(self.tmp.name) / "not-a-repo")
        control = AutoEvolution(engine, self.data)
        control.configure(enabled=True, allow_model_source=True)
        control.queue_goal("Improve calculator source reliability")
        outcome = await control.run_once("general")
        self.assertEqual(outcome["status"], "git_unavailable")
        self.assertEqual(engine.actions, [])
        self.assertTrue(control.status()["enabled"])
