"""Windows File Organization Agent: preview first, approved apply, reversible undo."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_file_organizer import (
    FileOrganizer, FileOrganizerError, FILE_ORGANIZER_ACTIONS, _category,
)


class CategoryTests(unittest.TestCase):
    def test_extensions_map_to_categories(self):
        self.assertEqual(_category("report.PDF"), "Documents")
        self.assertEqual(_category("photo.jpeg"), "Images")
        self.assertEqual(_category("clip.mp4"), "Video")
        self.assertEqual(_category("archive.tar"), "Archives")
        self.assertEqual(_category("script.py"), "Code")
        self.assertEqual(_category("mystery.xyz"), "_Others")
        self.assertEqual(_category("noextension"), "_Others")


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.messy = self.root / "messy"
        self.messy.mkdir()
        for name in ("a.pdf", "b.png", "c.unknownext", "note.txt"):
            (self.messy / name).write_text("content of " + name)
        self.organizer = FileOrganizer(self.data, root=self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_scan_proposes_without_moving_anything(self):
        plan = self.organizer.scan(str(self.messy))
        self.assertEqual(plan["state"], "proposed")
        self.assertEqual(len(plan["moves"]), 4)
        # Nothing has actually moved during a scan.
        for name in ("a.pdf", "b.png", "c.unknownext", "note.txt"):
            self.assertTrue((self.messy / name).is_file())
        self.assertFalse((self.messy / "Documents").exists())

    def test_scan_skips_folders_and_name_collisions(self):
        (self.messy / "subfolder").mkdir()
        (self.messy / "Documents").mkdir()
        (self.messy / "Documents" / "a.pdf").write_text("already here")
        plan = self.organizer.scan(str(self.messy))
        moved = {move["name"] for move in plan["moves"]}
        self.assertNotIn("a.pdf", moved)
        skipped = {item["name"]: item["reason"] for item in plan["skipped"]}
        self.assertIn("subfolder", skipped)
        self.assertIn("a.pdf", skipped)

    def test_apply_requires_exact_hash_and_approval(self):
        plan = self.organizer.scan(str(self.messy))
        with self.assertRaises(FileOrganizerError):
            self.organizer.apply(plan["id"], plan["plan_hash"], False)
        with self.assertRaises(FileOrganizerError):
            self.organizer.apply(plan["id"], "wrong-hash", True)

    def test_apply_then_undo_round_trips(self):
        plan = self.organizer.scan(str(self.messy))
        applied = self.organizer.apply(plan["id"], plan["plan_hash"], True)
        self.assertEqual(applied["state"], "applied")
        self.assertTrue((self.messy / "Documents" / "a.pdf").is_file())
        self.assertTrue((self.messy / "Images" / "b.png").is_file())
        undone = self.organizer.undo(plan["id"], True)
        self.assertEqual(undone["state"], "undone")
        for name in ("a.pdf", "b.png", "c.unknownext", "note.txt"):
            self.assertTrue((self.messy / name).is_file())
        self.assertFalse((self.messy / "Documents").exists())
        self.assertFalse((self.messy / "Images").exists())

    def test_undo_refuses_when_a_file_reappeared(self):
        plan = self.organizer.scan(str(self.messy))
        self.organizer.apply(plan["id"], plan["plan_hash"], True)
        (self.messy / "a.pdf").write_text("recreated by the user")
        with self.assertRaises(FileOrganizerError):
            self.organizer.undo(plan["id"], True)

    def test_apply_is_not_repeatable(self):
        plan = self.organizer.scan(str(self.messy))
        first = self.organizer.apply(plan["id"], plan["plan_hash"], True)
        second = self.organizer.apply(plan["id"], plan["plan_hash"], True)
        self.assertEqual(second["state"], "applied")
        self.assertEqual(first["applied"], second["applied"])

    def test_apply_rolls_back_when_a_target_appears_mid_run(self):
        plan = self.organizer.scan(str(self.messy))
        (self.messy / "Images").mkdir()
        (self.messy / "Images" / "b.png").write_text("squatter")
        with self.assertRaises(FileOrganizerError):
            self.organizer.apply(plan["id"], plan["plan_hash"], True)
        # Rollback restored the already-moved files.
        self.assertTrue((self.messy / "a.pdf").is_file())
        stored = json.loads((self.data / "file-organizer" / (plan["id"] + ".json")).read_text())
        self.assertEqual(stored["state"], "rolled_back")

    def test_relative_and_dangerous_paths_are_rejected(self):
        for bad in ("relative\\path", str(Path.home()), self.temp.name + "\\..\\outside"):
            with self.assertRaises(FileOrganizerError):
                self.organizer.scan(bad)
        outside = self.root.parent
        guarded = FileOrganizer(self.data, root=self.messy)
        with self.assertRaises(FileOrganizerError):
            guarded.scan(str(outside))

    def test_allowed_root_confines_scan(self):
        other = self.root / "elsewhere"
        other.mkdir()
        (other / "x.pdf").write_text("x")
        guarded = FileOrganizer(self.data, root=self.messy)
        with self.assertRaises(FileOrganizerError):
            guarded.scan(str(other))

    def test_history_lists_recent_plans(self):
        plan = self.organizer.scan(str(self.messy))
        self.organizer.apply(plan["id"], plan["plan_hash"], True)
        history = self.organizer.history()
        self.assertEqual(history[0]["id"], plan["id"])
        self.assertEqual(history[0]["state"], "applied")

    def test_execute_validates_action_and_payload_shape(self):
        with self.assertRaises(FileOrganizerError):
            self.organizer.execute("organize_scan", {"wrong": "field"})
        with self.assertRaises(FileOrganizerError):
            self.organizer.execute("not_an_action", {})
        self.assertIn("organize_apply", FILE_ORGANIZER_ACTIONS)
        plan = self.organizer.execute("organize_scan", {"directory": str(self.messy)})
        self.assertEqual(plan["state"], "proposed")


if __name__ == "__main__":
    unittest.main()
