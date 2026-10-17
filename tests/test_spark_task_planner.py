import importlib.util
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_task_planner import prepare_task, task_preview


class TaskPlannerTests(unittest.TestCase):
    def test_preview_is_pending_without_side_effects(self):
        task = prepare_task("Open notes", [{"action": "launch_desktop_app", "args": {"app": "notepad"}}])
        preview = task_preview(task)
        self.assertEqual(preview["status"], "pending")
        self.assertTrue(preview["requires_explicit_approval"])
        self.assertEqual(preview["steps"][0]["status"], "pending")

    def test_reject_commands_and_file_paths(self):
        bad = [
            {"action": "run_command", "args": {"command": "dir"}},
            {"action": "launch_desktop_app", "args": {"app": "powershell"}},
            {"action": "read_file", "args": {"path": "C:\\secret"}},
            {"action": "launch_desktop_app", "args": {"app": "notepad", "shell": True}},
        ]
        for item in bad:
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    prepare_task("unsafe", [item])

    def test_bounds(self):
        with self.assertRaises(ValueError):
            prepare_task("empty", [])
        with self.assertRaises(ValueError):
            prepare_task("large", [{"action": "launch_desktop_app", "args": {"app": "paint"}}] * 13)


if __name__ == "__main__":
    unittest.main()
