"""Read-only File Intelligence: duplicates, large/old/temp inventory. No mutation."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_file_intelligence import (
    FileIntelligence, FileIntelligenceError, INTELLIGENCE_ACTIONS, _is_temp,
)


class TempClassificationTests(unittest.TestCase):
    def test_temp_names_and_extensions(self):
        self.assertTrue(_is_temp(Path("stuff.tmp")))
        self.assertTrue(_is_temp(Path("file.bak")))
        self.assertTrue(_is_temp(Path("Thumbs.db")))
        self.assertTrue(_is_temp(Path("~$report.docx")))
        self.assertFalse(_is_temp(Path("report.pdf")))


class FileIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        (self.docs / "sub").mkdir(parents=True)
        self.files = {
            "a.txt": b"hello world",
            "b.txt": b"hello world",       # exact duplicate of a.txt
            "c.txt": b"different content",
            "big.bin": b"x" * (2 * 1024 * 1024),
            "junk.tmp": b"temp payload",
        }
        for name, data in self.files.items():
            (self.docs / name).write_bytes(data)
        (self.docs / "sub" / "nested.txt").write_bytes(b"hello world")  # duplicate
        self.intel = FileIntelligence(root=self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_scan_finds_exact_duplicates_across_subdirs(self):
        report = self.intel.scan(str(self.docs), large_mb=1, old_days=1)
        self.assertEqual(len(report["duplicates"]), 1)
        dup = report["duplicates"][0]
        self.assertEqual(dup["count"], 3)
        self.assertEqual(dup["size"], len(b"hello world"))
        names = sorted(Path(p).name for p in dup["paths"])
        self.assertEqual(names, ["a.txt", "b.txt", "nested.txt"])

    def test_only_same_size_files_are_hashed(self):
        report = self.intel.scan(str(self.docs), large_mb=1, old_days=1)
        # a/b/nested share a size, so 3 hashed; everyone else is unique in size.
        self.assertEqual(report["hashed_count"], 3)
        self.assertLess(report["hashed_count"], report["file_count"])

    def test_large_and_temp_reports(self):
        report = self.intel.scan(str(self.docs), large_mb=1, old_days=1)
        large = {Path(item["path"]).name for item in report["large_files"]}
        self.assertEqual(large, {"big.bin"})
        temp = {Path(item["path"]).name for item in report["temp_files"]}
        self.assertEqual(temp, {"junk.tmp"})

    def test_reclaimable_bytes_counts_extra_copies_and_temp(self):
        report = self.intel.scan(str(self.docs), large_mb=1, old_days=1)
        expected = len(b"hello world") * 2 + len(b"temp payload")
        self.assertEqual(report["reclaimable_bytes"], expected)

    def test_scan_moves_nothing(self):
        before = {p.name for p in self.docs.iterdir()}
        self.intel.scan(str(self.docs))
        after = {p.name for p in self.docs.iterdir()}
        self.assertEqual(before, after)
        self.assertIn("Read-only", self.intel.scan(str(self.docs))["note"])

    def test_old_files_detected(self):
        old = self.docs / "ancient.txt"
        old.write_text("old")
        past = time.time() - 900 * 86400
        os.utime(old, (past, past))
        report = self.intel.scan(str(self.docs), large_mb=1, old_days=365)
        self.assertIn("ancient.txt", {Path(item["path"]).name for item in report["old_files"]})

    def test_bad_directory_and_dangerous_paths_rejected(self):
        for bad in ("relative\\path", str(Path.home()), self.root.anchor, None, 5):
            with self.assertRaises(FileIntelligenceError):
                self.intel.scan(bad)

    def test_allowed_root_confines_scans(self):
        outside = self.root.parent
        guarded = FileIntelligence(root=self.docs)
        with self.assertRaises(FileIntelligenceError):
            guarded.scan(str(outside))

    def test_bad_thresholds_rejected(self):
        for kwargs in ({"large_mb": 0}, {"large_mb": 10**9}, {"old_days": 0}, {"old_days": 10**6}):
            with self.assertRaises(FileIntelligenceError):
                self.intel.scan(str(self.docs), **kwargs)

    def test_execute_validates_shape(self):
        with self.assertRaises(FileIntelligenceError):
            self.intel.execute("nope", {"directory": str(self.docs)})
        with self.assertRaises(FileIntelligenceError):
            self.intel.execute("files_intelligence_scan", {"bogus": 1})
        report = self.intel.execute("files_intelligence_scan", {"directory": str(self.docs)})
        self.assertIn("duplicates", report)
        tuned = self.intel.execute("files_intelligence_scan",
                                   {"directory": str(self.docs), "large_mb": 5})
        self.assertIn("duplicates", tuned)
        self.assertIn("files_intelligence_scan", INTELLIGENCE_ACTIONS)


if __name__ == "__main__":
    unittest.main()
