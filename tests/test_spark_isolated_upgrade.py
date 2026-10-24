"""Isolated continuous upgrading: D: workspaces, gated promotion, rollback.

Offline acceptance: the model and every heavy dependency are replaced by
fakes; the only real subprocess work is the focused unittest run inside the
throw-away workspace. The live fixture repository is never a real Git
checkout reset/clean/checkout/stash target; the real SPARK checkout is
never touched.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_auto_evolution import AutoEvolution, AutoEvolutionError
from spark_isolated_upgrade import (
    IsolatedUpgradeManager, IsolatedUpgradeError, DEFAULT_BASE_DIRECTORY,
)


ORIGIN = "value=3\n"
OWNER_NOTE = "# owner manual note while SPARK works\n"
IMPROVE_DOUBLE = "\n\ndef double(number):\n    return number * 2\n"
BROKEN_DOUBLE = "\n\ndef double(number):\n    return number * 3\n"
EXTRA_NOTE = "\n# reliability notes\n"

TEST_SOURCE = '''import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import calculator as module


class CalculatorCandidateTests(unittest.TestCase):
    def test_value_is_preserved(self):
        self.assertEqual(module.value, 3)

    def test_double_behavior(self):
        self.assertEqual(module.double(21), 42)
'''


def digest_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hash_tree(root):
    digests = {}
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        digests[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


class FakeSkills:
    def _file(self, project):
        if project != "general":
            raise ValueError("Unknown project")


class FakeMaintenance:
    def __init__(self, root):
        self.root = root
        self.healthy = True

    def detect(self):
        return {"healthy": self.healthy, "findings": [] if self.healthy else [{"error": "smoke"}]}


class FakeRea:
    async def request(self, action, payload):
        return [{"name": "inspect", "description": "read-only"}]


class FakeSaee:
    def __init__(self):
        self.events = []

    def record_attempt(self, project, request_id, stage, outcome, evidence=None):
        self.events.append((stage, outcome))


class FakeEvolution:
    """Offline engine whose activation/rollback really touch the live fixture.

    activate_repair_candidate writes the candidate content into the fixture
    repository (like the real maintenance engine) so every test can verify
    what promotion did or did not do to the live tree.
    """

    def __init__(self, root):
        self.maintenance = FakeMaintenance(root)
        self.workspace = type("Workspace", (), {"skills": FakeSkills()})()
        self.rea = FakeRea()
        self.saee = FakeSaee()
        self.actions = []
        self.improvements = [IMPROVE_DOUBLE, EXTRA_NOTE]
        self.staged = {}
        self.backups = {}

    async def execute(self, action, project, payload):
        self.actions.append((action, payload))
        if action == "analyze_repository":
            return {"id": "b" * 24, "opportunities": [
                {"spark_paths": ["backend/calculator.py"],
                 "verification": "calculator double behavior test"}]}
        if action == "stage_repository_upgrade":
            source = self.maintenance.root / "backend" / "calculator.py"
            change = {"path": "backend/calculator.py",
                      "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                      "content": source.read_text(encoding="utf-8") + self.improvements.pop(0)}
            record = {"id": hashlib.sha256(change["content"].encode()).hexdigest()[:24],
                      "status": "staged", "changes": [change]}
            self.staged[record["id"]] = record
            return record
        if action == "test_repair_candidate":
            return {"id": payload["id"], "status": "tested"}
        if action == "activate_repair_candidate":
            record = self.staged[payload["id"]]
            for change in record["changes"]:
                target = self.maintenance.root / change["path"]
                self.backups[change["path"]] = target.read_bytes()
                target.write_text(change["content"], encoding="utf-8")
            return {"id": payload["id"], "status": "applied"}
        if action == "rollback_repair":
            for relative, data in list(self.backups.items()):
                (self.maintenance.root / relative).write_bytes(data)
            self.backups.clear()
            return {"status": "rolled_back"}
        raise AssertionError(action)


class MutableGate:
    """Inspection stub whose reported state is adjustable between cycles."""
    def __init__(self, state):
        self.state = state
        self.calls = 0

    def inspect(self):
        self.calls += 1
        return self.state


CLEAN = {"dirty": False, "paths": []}
DIRTY = {"dirty": True, "paths": ["notes.txt"]}


class IsolatedUpgradeTests(unittest.IsolatedAsyncioTestCase):
    """Full offline acceptance of the isolated upgrade lifecycle."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        (self.repo / "backend").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        (self.repo / "backend" / "calculator.py").write_text(ORIGIN, encoding="utf-8")
        (self.repo / "tests" / "test_spark_calculator.py").write_text(TEST_SOURCE, encoding="utf-8")
        self.iso = Path(self.tmp.name) / "isolated"
        self.engine = FakeEvolution(self.repo)
        self.manager = IsolatedUpgradeManager(self.engine, self.repo, base_dir=self.iso)
        self.git = MutableGate(CLEAN)
        self.data = Path(self.tmp.name) / "data"
        self.time = [1_000_000]
        self.control = AutoEvolution(self.engine, self.data,
                                     clock=lambda: self.time[0],
                                     git_gate=self.git,
                                     isolated=self.manager)
        self.control.configure(enabled=True, allow_model_source=True)
        self.control.set_background_limits(interval_seconds=60, max_upgrades_per_day=0)

    def live_text(self):
        return (self.repo / "backend" / "calculator.py").read_text(encoding="utf-8")

    def queue_and_advance(self, goal="Improve calculator double behavior"):
        self.control.queue_goal(goal)
        self.time[0] += 61

    async def test_successful_isolated_upgrade_promotes_and_preserves_unrelated_files(self):
        before = hash_tree(self.repo)
        self.queue_and_advance()
        outcome = await self.control.run_once("general")
        self.assertEqual(outcome["status"], "applied")
        self.assertEqual(self.live_text(), ORIGIN + IMPROVE_DOUBLE)
        # only the target changed; every other file stayed byte identical
        unrelated = {p: d for p, d in hash_tree(self.repo).items()
                     if p != "backend/calculator.py"}
        self.assertEqual(unrelated, {p: d for p, d in before.items() if p != "backend/calculator.py"})
        records = self.manager.list_candidates()
        self.assertEqual([r["status"] for r in records], ["promoted"])
        self.assertTrue((self.iso / "audit.jsonl").is_file())
        kinds = [entry["kind"] for entry in self.manager.history()]
        self.assertIn("cycle_tested", kinds)
        self.assertIn("candidate_promoted", kinds)

    async def test_dirty_live_tree_holds_candidate_and_touches_nothing(self):
        self.git.state = DIRTY
        before = hash_tree(self.repo)
        self.queue_and_advance()
        outcome = await self.control.run_once("general")
        self.assertEqual(outcome["status"], "isolated_staged")
        self.assertEqual(self.live_text(), ORIGIN)
        self.assertEqual(hash_tree(self.repo), before)
        self.assertEqual(self.manager.held_count(), 1)
        self.assertEqual(self.control.status()["last_status"], "isolated_staged")
        # switching to a clean work tree promotes the held candidate later
        self.git.state = CLEAN
        self.time[0] += 61
        outcome = await self.control.run_once("general")
        self.assertEqual(outcome["status"], "applied")
        self.assertEqual(self.live_text(), ORIGIN + IMPROVE_DOUBLE)

    async def test_failed_isolated_tests_reject_the_candidate_and_keep_live_intact(self):
        self.engine.improvements = [BROKEN_DOUBLE]
        before = hash_tree(self.repo)
        self.queue_and_advance()
        outcome = await self.control.run_once("general")
        self.assertEqual(outcome["status"], "isolated_rejected")
        record = self.manager.list_candidates()[0]
        self.assertEqual(record["status"], "rejected")
        self.assertFalse(record["validation"]["passed"])
        self.assertTrue(record["validation"]["tests_run"])
        self.assertEqual(self.live_text(), ORIGIN)
        self.assertEqual(hash_tree(self.repo), before)
        self.assertTrue(self.control.status()["enabled"])

    async def test_multiple_successful_sequential_isolated_upgrades_on_the_same_day(self):
        self.queue_and_advance("Improve calculator double behavior")
        first = await self.control.run_once("general")
        self.assertEqual(first["status"], "applied")
        self.queue_and_advance("Improve calculator reliability notes")
        second = await self.control.run_once("general")
        self.assertEqual(second["status"], "applied")
        self.assertEqual(self.live_text(), ORIGIN + IMPROVE_DOUBLE + EXTRA_NOTE)
        self.assertEqual([r["status"] for r in self.manager.list_candidates()],
                         ["promoted", "promoted"])

    async def test_quota_exhaustion_defers_promotion_and_keeps_candidate_isolated(self):
        self.control.set_background_limits(interval_seconds=60, max_upgrades_per_day=1)
        self.queue_and_advance()
        applied = await self.control.run_once("general")
        self.assertEqual(applied["status"], "applied")
        self.queue_and_advance()
        outcome = await self.control.run_once("general")
        self.assertEqual(outcome["status"], "isolated_ready")
        self.assertIn("quota", outcome["reason"])
        self.assertEqual(self.live_text(), ORIGIN + IMPROVE_DOUBLE)
        self.assertEqual(self.manager.held_count(), 1)
        self.assertEqual(self.control.status()["last_status"], "isolated_ready")

    async def test_restart_reconstructs_held_candidate_and_audit_history(self):
        self.git.state = DIRTY
        self.queue_and_advance()
        outcome = await self.control.run_once("general")
        self.assertEqual(outcome["status"], "isolated_staged")
        # simulate a service restart over the same storage
        fresh_manager = IsolatedUpgradeManager(self.engine, self.repo, base_dir=self.iso)
        fresh_control = AutoEvolution(self.engine, self.data,
                                      clock=lambda: self.time[0],
                                      git_gate=self.git, isolated=fresh_manager)
        self.assertTrue(fresh_control.status()["enabled"])
        record = fresh_manager.held()
        self.assertEqual(record["status"], "tested")
        self.assertTrue(fresh_manager.history())
        self.git.state = CLEAN
        self.time[0] += 61
        outcome = await fresh_control.run_once("general")
        self.assertEqual(outcome["status"], "applied")
        self.assertEqual(self.live_text(), ORIGIN + IMPROVE_DOUBLE)

    async def test_concurrent_owner_modification_is_detected_and_never_overwritten(self):
        self.git.state = DIRTY
        self.queue_and_advance()
        outcome = await self.control.run_once("general")
        self.assertEqual(outcome["status"], "isolated_staged")
        # the owner edits the live target after generation and testing
        edited = self.repo / "backend" / "calculator.py"
        edited.write_text(ORIGIN + OWNER_NOTE, encoding="utf-8")
        self.git.state = CLEAN
        self.time[0] += 61
        outcome = await self.control.run_once("general")
        self.assertEqual(outcome["status"], "stale")
        self.assertIn("backend/calculator.py", outcome["paths"])
        self.assertEqual(self.live_text(), ORIGIN + OWNER_NOTE)
        self.assertEqual(self.manager.list_candidates()[0]["status"], "stale")
        self.assertTrue(self.control.status()["enabled"])

    async def test_failed_health_check_rolls_back_and_disables_autonomy(self):
        self.engine.maintenance.healthy = False
        self.queue_and_advance()
        outcome = await self.control.run_once("general")
        self.assertEqual(outcome["status"], "rolled_back")
        self.assertEqual(self.live_text(), ORIGIN)
        self.assertEqual([a for a, _ in self.engine.actions][-1], "rollback_repair")
        self.assertEqual(self.manager.list_candidates()[0]["status"], "rolled_back")
        self.assertFalse(self.control.status()["enabled"])

    async def test_emergency_stop_during_promotion_blocks_live_activation(self):
        self.queue_and_advance()
        entered = asyncio.Event()
        original_execute = self.engine.execute

        async def hooked_execute(action, project, payload):
            result = await original_execute(action, project, payload)
            if action == "test_repair_candidate":
                entered.set()
                self.control.emergency_stop()
            return result

        self.engine.execute = hooked_execute
        outcome = await self.control.run_once("general")
        await entered.wait()
        self.assertEqual(outcome["status"], "failed")
        actions = [a for a, _ in self.engine.actions]
        self.assertIn("test_repair_candidate", actions)
        self.assertNotIn("activate_repair_candidate", actions)
        self.assertEqual(self.live_text(), ORIGIN)
        self.assertFalse(self.control.status()["enabled"])

    async def test_workspace_is_minimal_and_never_copies_the_whole_repository(self):
        for index in range(30):
            (self.repo / "backend" / ("noise_%02d.py" % index)).write_text("x=%d\n" % index, encoding="utf-8")
        (self.repo / "tests" / "test_spark_noise.py").write_text("raise SystemExit\n", encoding="utf-8")
        outcome = await self.manager.run_cycle("Improve calculator double behavior", "general")
        self.assertEqual(outcome["status"], "tested")
        workspace = self.iso / outcome["workspace"]
        copied_backend = sorted(p.name for p in (workspace / "backend").glob("*.py"))
        copied_tests = sorted(p.name for p in (workspace / "tests").glob("*.py"))
        self.assertEqual(copied_backend, ["calculator.py"])
        self.assertEqual(copied_tests, ["test_spark_calculator.py"])
        manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["target"], "backend/calculator.py")
        self.assertEqual(set(manifest["originals"]), {"backend/calculator.py", "tests/test_spark_calculator.py"})
        self.assertEqual(self.live_text(), ORIGIN)

    def test_primary_storage_default_points_at_the_d_drive(self):
        self.assertTrue(DEFAULT_BASE_DIRECTORY.lower().startswith("d:"))
        self.assertIn("SPARK", DEFAULT_BASE_DIRECTORY)

    def test_secret_findings_reject_without_crashing_or_exposing_values(self):
        workspace = self.manager._build('Improve calculator double behavior')
        finding = {'label': 'high_entropy_literal', 'line': 1, 'redacted': 'private-prefix'}
        with patch('spark_isolated_upgrade.scan_secrets', return_value=[finding]):
            result = self.manager._validate(workspace)
        self.assertFalse(result['passed'])
        self.assertIn('high_entropy_literal', result['findings'][0]['error'])
        self.assertNotIn('private-prefix', json.dumps(result))

    def test_real_scanner_keeps_isolated_secret_gate_closed(self):
        workspace = self.manager._build('Improve calculator double behavior')
        target = workspace.root / 'backend/calculator.py'
        clean = ORIGIN + IMPROVE_DOUBLE + "\nheaders = {'Content-Type': 'application/x-www-form-urlencoded'}\n"
        target.write_text(clean, encoding='utf-8')
        self.assertTrue(self.manager._validate(workspace)['passed'])
        for assignment in ('opaque = "9f4Aq7Zx2Lm8Pw3Rt6Yu1Io5Nb0Vc7Df"',
                           'password = "application/x-www-form-urlencoded"'):
            with self.subTest(assignment=assignment):
                target.write_text(clean + assignment + '\n', encoding='utf-8')
                result = self.manager._validate(workspace)
                self.assertFalse(result['passed'])
                self.assertEqual(result['returncode'], 0)
                self.assertTrue(any('Credential scan finding:' in f.get('error', '') for f in result['findings']))


if __name__ == "__main__":
    unittest.main()
