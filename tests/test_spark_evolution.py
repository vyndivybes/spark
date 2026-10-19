import asyncio
import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_evolution import Evolution
from spark_maintenance import Maintenance, MaintenanceError, digest
from spark_workspace import SparkWorkspace
from arkus_skill_forge import SkillError
from spark_workspace import WorkspaceError
from spark_rea import ReaError
from spark_evolution import ACTION_KEYS
from spark_workbench import ACTION_KEYS as WORKBENCH_ACTIONS
from spark_productivity import WorkbenchError
from spark_workspace_auth import workspace_client_allowed
import os


class RepairTests(unittest.TestCase):
    def test_candidate_requires_separate_test_and_activation_approval(self):
        engine = Maintenance(self.root,self.data,validator=lambda root:None)
        candidate=engine.stage(self.patch())
        self.assertEqual(self.source.read_text(),'value = 1\n')
        with self.assertRaises(MaintenanceError):engine.activate_candidate(candidate['id'],approved=True)
        with self.assertRaises(MaintenanceError):engine.test_candidate(candidate['id'],approved=False)
        tested=engine.test_candidate(candidate['id'],approved=True)
        self.assertEqual(tested['status'],'tested')
        self.assertEqual(self.source.read_text(),'value = 1\n')
        with self.assertRaises(MaintenanceError):engine.activate_candidate(candidate['id'],approved=False)
        result=engine.activate_candidate(candidate['id'],approved=True)
        self.assertEqual(result['status'],'applied')
        self.assertEqual(self.source.read_text(),'value = 2\n')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        (self.root / "backend").mkdir(parents=True)
        (self.root / "tests").mkdir()
        self.source = self.root / "backend" / "calculator.py"
        self.source.write_text("value = 1\n")
        self.data = Path(self.temp.name) / "data"

    def tearDown(self):
        self.temp.cleanup()

    def patch(self, text="value = 2\n"):
        return [{"path": "backend/calculator.py", "content": text, "sha256": digest(self.source.read_bytes())}]

    def test_real_staged_suite_rejects_wrong_patch_and_accepts_correct_fix(self):
        (self.root / "tests" / "test_spark_sample.py").write_text(
            "import unittest,sys\nfrom pathlib import Path\n"
            "sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))\n"
            "from calculator import value\n"
            "class TestValue(unittest.TestCase):\n def test_value(self):self.assertEqual(value,2)\n")
        engine = Maintenance(self.root, self.data)
        with self.assertRaises(MaintenanceError):
            engine.apply(self.patch("value = 3\n"))
        self.assertEqual(self.source.read_text(), "value = 1\n")
        result = engine.apply(self.patch())
        self.assertEqual(result["status"], "applied")
        self.assertEqual(self.source.read_text(), "value = 2\n")
        engine.rollback(result["id"])
        self.assertEqual(self.source.read_text(), "value = 1\n")

    def test_post_application_failure_restores_backup(self):
        scopes=[]
        def validate(root):
            # Windows runners can expose TEMP through a short-name alias.
            live=root.samefile(self.root)
            scopes.append(live)
            if live:
                raise RuntimeError("live smoke failed")
        engine = Maintenance(self.root, self.data, validate)
        with self.assertRaises(RuntimeError):
            engine.apply(self.patch())
        self.assertEqual(self.source.read_text(), "value = 1\n")
        self.assertEqual(scopes,[False,True])
        self.assertEqual(engine.history()[0]["status"], "rolled_back")

    def test_interrupted_application_recovers_after_new_engine_starts(self):
        engine = Maintenance(self.root, self.data, lambda root: None)
        result = engine.apply(self.patch())
        journal = engine.backups / result["id"] / "journal.json"
        record = json.loads(journal.read_text())
        record["status"] = "applying"
        journal.write_text(json.dumps(record))
        restored = Maintenance(self.root, self.data, lambda root: None)
        self.assertEqual(restored.recover(), [result["id"]])
        self.assertEqual(self.source.read_text(), "value = 1\n")
        self.assertEqual(restored.recover(), [])

    def test_rollback_preserves_subsequent_human_changes(self):
        engine = Maintenance(self.root, self.data, lambda root: None)
        result = engine.apply(self.patch())
        self.source.write_text("value = 99\n")
        with self.assertRaisesRegex(MaintenanceError, "newer edits"):
            engine.rollback(result["id"])
        self.assertEqual(self.source.read_text(), "value = 99\n")

    def test_scope_stale_source_and_recovery_code_are_rejected(self):
        engine = Maintenance(self.root, self.data, lambda root: None)
        change = self.patch()
        self.source.write_text("value = 44\n")
        with self.assertRaisesRegex(MaintenanceError, "Source changed"):
            engine.apply(change)
        for path in ("../outside.py", "backend/../secret.py", "backend\\calculator.py", "tests/test_spark_sample.py"):
            with self.assertRaises(MaintenanceError):
                engine.apply([{**self.patch()[0], "path": path}])
        (self.root / "backend" / "server.py").write_text("x=1")
        with self.assertRaisesRegex(MaintenanceError, "manual upgrade"):
            engine.apply([{**self.patch()[0], "path": "backend/server.py"}])

    def test_detection_identifies_syntax_errors(self):
        self.source.write_text("def broken(:\n")
        result = Maintenance(self.root, self.data).detect()
        self.assertFalse(result["healthy"])
        self.assertEqual(result["findings"][0]["line"], 1)


class EvolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_generated_skill_needs_separate_inspection_and_activation(self):
        candidate=await self.engine.execute('generate_skill','general',{'description':'Area','base_id':None})
        self.assertEqual(candidate['status'],'tested')
        with self.assertRaises(SkillError):self.workspace.skills.run('general','area',{'a':3,'b':4})
        self.workspace.execute('activate_skill','general',{'id':candidate['id']})
        self.assertEqual(self.workspace.skills.run('general','area',{'a':3,'b':4})['result'],12)

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.temp.name)
        self.spec = {"name": "area", "description": "Area", "operation": "multiply", "inputs": ["a", "b"],
                     "tests": [{"parameters": {"a": 3, "b": 4}, "expected": 12}]}
        async def generate(instruction, context):
            return self.spec
        self.engine = Evolution(self.workspace, generator=generate)

    async def asyncTearDown(self):
        await self.engine.rea.close()
        self.temp.cleanup()

    async def test_generated_skill_passes_and_persists_then_failed_upgrade_keeps_it(self):
        first = await self.engine.execute("generate_skill", "general", {"description": "Area", "base_id": None})
        self.assertEqual(first["status"], "tested")
        self.workspace.execute('activate_skill','general',{'id':first['id']})
        bad = {**self.spec, "operation": "add"}
        result = await self.engine.execute("upgrade_skill", "general", {"spec": bad, "base_id": first["id"]})
        self.assertEqual(result["status"], "rejected")
        restored = SparkWorkspace(self.temp.name)
        self.assertEqual(restored.skills.run("general", "area", {"a": 3, "b": 4})["result"], 12)

    async def test_failed_active_upgrade_recovers_previous_revision_on_run(self):
        first = await self.engine.execute("upgrade_skill", "general", {"spec": self.spec, "base_id": None})
        self.workspace.execute('activate_skill','general',{'id':first['id']})
        upgrade = {**self.spec, "operation": "add", "tests": [{"parameters": {"a": 3, "b": 4}, "expected": 7}]}
        revised=await self.engine.execute("upgrade_skill", "general", {"spec": upgrade, "base_id": first["id"]})
        self.workspace.execute('activate_skill','general',{'id':revised['id']})
        path = self.workspace.skills._file("general")
        registry = json.loads(path.read_text())
        registry[-1]["spec"]["tests"][0]["expected"] = 999
        path.write_text(json.dumps(registry))
        result = self.workspace.skills.run("general", "area", {"a": 3, "b": 4})
        self.assertEqual(result["result"], 12)
        self.assertTrue(result["recovered_previous_revision"])

    async def test_bad_user_inputs_do_not_trigger_skill_rollback(self):
        first=await self.engine.execute("upgrade_skill", "general", {"spec": self.spec, "base_id": None})
        self.workspace.execute('activate_skill','general',{'id':first['id']})
        with self.assertRaises(SkillError):
            self.workspace.skills.run("general", "area", {"a": "wrong", "b": 4})
        self.assertEqual(self.workspace.skills.available("general")[0]["status"], "active")

    async def test_executable_skill_and_invalid_project_are_rejected(self):
        with self.assertRaises(SkillError):
            await self.engine.execute("upgrade_skill", "general", {"spec": {**self.spec, "code": "bad"}, "base_id": None})
        with self.assertRaises(SkillError):
            await self.engine.execute("diagnose_sources", "../escape", {})


class EvolutionSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_foreign_website_cannot_use_an_authenticated_owner_session(self):
        namespace=self.handler()
        namespace['sio'].get_environ=lambda sid:{'HTTP_ORIGIN':'https://example.com'}
        await namespace['workspace_action']('owner',{'request_id':'foreign','action':'rea_discover','project':'general','payload':{}})
        namespace['spark_evolution'].execute.assert_not_awaited()
        self.assertFalse(namespace['sio'].emit.await_args.args[1]['ok'])

    def handler(self, owner="owner", authenticated=True):
        source = Path(__file__).resolve().parents[1] / "backend" / "server.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        handler = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "workspace_action")
        handler.decorator_list = []
        namespace = {
            "asyncio": asyncio, "sio": SimpleNamespace(emit=AsyncMock(),get_environ=lambda sid:{"HTTP_ORIGIN":"http://localhost:5173"}),
            "workspace_client_allowed":workspace_client_allowed,"os":os,
            "audio_loop": SimpleNamespace(owner_sid=owner, session=object()),
            "SETTINGS": {"face_auth_enabled": True},
            "authenticator": SimpleNamespace(authenticated=authenticated),
            "spark_evolution": SimpleNamespace(execute=AsyncMock(return_value={"tools": []})),
            "spark_workspace": None, "workspace_project_by_sid": {},
            "EVOLUTION_ACTIONS": ACTION_KEYS, "WorkspaceError": WorkspaceError,
            "MaintenanceError": MaintenanceError, "ReaError": ReaError, "SkillError": SkillError,
            "WORKBENCH_ACTIONS": WORKBENCH_ACTIONS, "WorkbenchError": WorkbenchError,
        }
        exec(compile(ast.Module(body=[handler], type_ignores=[]), str(source), "exec"), namespace)
        return namespace

    async def test_non_owner_and_unauthenticated_windows_cannot_invoke_rea(self):
        for sid, authenticated in (("stranger", True), ("owner", False)):
            namespace = self.handler(authenticated=authenticated)
            await namespace["workspace_action"](sid, {"request_id": "one", "action": "rea_discover", "project": "general", "payload": {}})
            namespace["spark_evolution"].execute.assert_not_awaited()
            reply = namespace["sio"].emit.await_args
            self.assertFalse(reply.args[1]["ok"])
            self.assertEqual(reply.kwargs["room"], sid)

    async def test_authorized_request_routes_to_direct_bridge_and_owning_room(self):
        namespace = self.handler()
        await namespace["workspace_action"]("owner", {"request_id": "one", "action": "rea_discover", "project": "general", "payload": {}})
        namespace["spark_evolution"].execute.assert_awaited_once_with("rea_discover", "general", {})
        reply = namespace["sio"].emit.await_args
        self.assertTrue(reply.args[1]["ok"])
        self.assertEqual(reply.kwargs["room"], "owner")


if __name__ == "__main__":
    unittest.main()
