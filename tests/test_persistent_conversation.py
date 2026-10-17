"""Stage 7 persistent chat regression tests (stdlib-only)."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

file_path = Path(__file__).resolve().parents[1] / "backend" / "project_manager.py"
spec = importlib.util.spec_from_file_location("spark_project_manager", file_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PersistentConversationTests(unittest.TestCase):
    def test_default_chat_survives_reinstantiation(self):
        with tempfile.TemporaryDirectory() as folder:
            first = module.ProjectManager(folder)
            first.log_chat("User", "Remember this conversation")
            second = module.ProjectManager(folder)
            self.assertEqual(second.get_recent_chat_history()[-1]["text"], "Remember this conversation")

    def test_project_history_remains_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = module.ProjectManager(folder)
            pm.log_chat("User", "default conversation")
            self.assertTrue(pm.create_project("PrivateProject")[0])
            self.assertTrue(pm.switch_project("PrivateProject")[0])
            pm.log_chat("User", "project-specific")
            self.assertEqual([e["text"] for e in pm.get_recent_chat_history()], ["project-specific"])
            pm.switch_project("temp")
            self.assertEqual([e["text"] for e in pm.get_recent_chat_history()], ["default conversation"])

    def test_corrupted_json_line_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = module.ProjectManager(folder)
            log_file = pm.get_current_project_path() / "chat_history.jsonl"
            log_file.write_text('{"sender":"User","text":"good"}\n{invalid\n', encoding="utf-8")
            self.assertEqual([e["text"] for e in pm.get_recent_chat_history(limit=1)], ["good"])

    def test_invalid_limits_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            pm = module.ProjectManager(folder)
            pm.log_chat("User", "hello")
            self.assertEqual(pm.get_recent_chat_history(limit=0), [])
            self.assertEqual(pm.get_recent_chat_history(limit=-1), [])


if __name__ == "__main__":
    unittest.main()
