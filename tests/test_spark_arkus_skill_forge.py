# Ported actual ARKUS behavior contract (user-owned source), imports point to SPARK backend.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
"""Skill Forge contract tests: AI-authored declarative skills, no arbitrary code execution."""
import tempfile
import unittest
from pathlib import Path
from arkus_skill_forge import SkillForge, SkillError


class SkillForgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.store=SkillForge(self.root)
    def tearDown(self):
        self.tmp.cleanup()
    def test_generate_test_activate_execute_survives_restart(self):
        spec={"name":"area", "description":"Calculate rectangle area", "operation":"multiply",
              "inputs":["length","width"],"output":"Area in square units"}
        draft=self.store.propose(spec,"general")
        self.assertEqual(draft["status"],"draft")
        result=self.store.test("general",draft["id"])
        self.assertEqual(result["status"],"tested")
        self.store.activate("general",draft["id"])
        new=SkillForge(self.root)
        self.assertEqual(new.run("general","area",{"length":5,"width":4})["result"],20)
        self.assertEqual(new.available("engineering"),[])
    def test_invalid_dangerous_skills_and_bad_params_denied(self):
        for spec in [
            {"name":"shell","description":"x","operation":"exec","inputs":["cmd"]},
            {"name":"../../bad","description":"x","operation":"multiply","inputs":["a","b"]},
            {"name":"safe","description":"x","operation":"multiply","inputs":["a","a"]},
        ]:
            with self.assertRaises(SkillError):
                self.store.propose(spec,"general")
        with self.assertRaises(SkillError):
            self.store.run("general","none",{"a":3})
    def test_fail_closed_on_path_link_and_oversized_input(self):
        with self.assertRaises(SkillError):
            self.store.propose({"name":"x","description":"x","operation":"add",
                                "inputs":["a","b"]},"../escape")
        draft=self.store.propose({"name":"sum","description":"x","operation":"add",
                                  "inputs":["a","b"]},"general")
        self.store.test("general",draft["id"])
        self.store.activate("general",draft["id"])
        with self.assertRaises(SkillError):
            self.store.run("general","sum",{"a":float("nan"),"b":2})
    def test_no_execution_of_unapproved_draft(self):
        spec={"name":"calc","description":"x","operation":"add","inputs":["a","b"]}
        draft=self.store.propose(spec,"general")
        with self.assertRaises(SkillError):
            self.store.run("general","calc",{"a":1,"b":2})
        with self.assertRaises(SkillError):
            self.store.activate("general",draft["id"])
