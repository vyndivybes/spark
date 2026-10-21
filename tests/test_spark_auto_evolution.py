"""Autonomous evolution: persistent authorization, controlled cycles and rollback."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_auto_evolution import AutoEvolution, AutoEvolutionError


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
        self.control = AutoEvolution(self.engine, Path(self.tmp.name)/"data", clock=lambda: self.time[0])
    async def asyncTearDown(self):
        await self.control.stop_scheduler()
        self.tmp.cleanup()

    async def test_disabled_by_default_and_persistent_authorization(self):
        self.assertFalse(self.control.status()["enabled"])
        self.assertEqual((await self.control.run_once("general"))["status"], "disabled")
        self.control.configure(enabled=True, allow_model_source=False)
        self.assertTrue(AutoEvolution(self.engine, Path(self.tmp.name)/"data").status()["enabled"])
        self.assertFalse(AutoEvolution(self.engine, Path(self.tmp.name)/"data").status()["allow_model_source"])

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
