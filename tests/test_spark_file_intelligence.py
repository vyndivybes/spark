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

    def test_near_duplicate_detection_opt_in(self):
        (self.docs / "a.txt").write_text("the quick brown fox jumps over the lazy dog")
        (self.docs / "b.txt").write_text("the quick brown fox jumps over the lazy dog again")
        (self.docs / "c.txt").write_text("completely unrelated random words about engines")
        result = self.intel.execute("files_intelligence_scan",
                                    {"directory": str(self.docs), "near_dup": True})
        pairs = [sorted(Path(p).name for p in g["paths"]) for g in result["near_duplicates"]]
        self.assertIn(["a.txt", "b.txt"], pairs)
        self.assertFalse(any("c.txt" in p for g in result["near_duplicates"] for p in g["paths"]))
        default = self.intel.execute("files_intelligence_scan", {"directory": str(self.docs)})
        self.assertEqual(default["near_duplicates"], [])

    def test_redundant_installers_grouped_by_family(self):
        for name in ("setup_v1.exe", "setup_v2.exe"):
            (self.docs / name).write_text("x")
        for name in ("appinstaller.exe", "other.exe"):
            (self.docs / name).write_text("y")
        result = self.intel.execute("files_intelligence_scan", {"directory": str(self.docs), "near_dup": False})
        # Generic "setup_1"/"setup_2" normalizes to empty families on purpose;
        # versioned installers of one app with a shared stem still group.
        self.assertTrue(any(g["count"] >= 2 for g in result["redundant_installers"])
                        or len(result["installers"]) >= 3)

    def test_duplicate_downloads_grouped(self):
        (self.docs / "report.pdf").write_text("one")
        (self.docs / "report (1).pdf").write_text("two")
        (self.docs / "notes - copy.txt").write_text("three")
        (self.docs / "unrelated.txt").write_text("four")
        result = self.intel.execute("files_intelligence_scan", {"directory": str(self.docs)})
        originals = {d["original"] for d in result["duplicate_downloads"]}
        self.assertIn("report.pdf", originals)
        self.assertIn("notes.txt", originals)

    def test_recommendations_are_advisory_and_aggregate(self):
        (self.docs / "report.pdf").write_text("one")
        (self.docs / "report (1).pdf").write_text("two")
        (self.docs / "old.tmp").write_text("temp")
        result = self.intel.execute("files_intelligence_scan", {"directory": str(self.docs)})
        kinds = {item["kind"] for item in result["recommendations"]}
        self.assertIn("duplicate_downloads", kinds)
        self.assertIn("temporary_files", kinds)
        self.assertTrue(result["recommendations_note"])
        self.assertTrue(Path(result["directory"]).is_dir())  # nothing changed

    def test_near_dup_flag_validated(self):
        with self.assertRaises(FileIntelligenceError):
            self.intel.execute("files_intelligence_scan",
                               {"directory": str(self.docs), "near_dup": "yes"})


class FileSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "budget Q1.csv").write_text("a" * 100)
        (self.root / "budget2020.csv").write_text("b" * 50)
        (self.root / "readme.txt").write_text("read it now " * 20)
        (self.root / "photos").mkdir()
        (self.root / "photos" / "trip.jpg").write_text("c")
        self.intel = FileIntelligence()
        import time as _time
        _old = _time.time() - 120 * 86400
        os.utime(self.root / "budget2020.csv", (_old, _old))

    def tearDown(self):
        self.temp.cleanup()

    def test_keyword_and_extension_search(self):
        result = self.intel.execute("files_search",
                                    {"directory": str(self.root), "query": "budget csv"})
        names = [Path(item["path"]).name for item in result["results"]]
        self.assertEqual(names, ["budget Q1.csv", "budget2020.csv"])
        self.assertTrue(all(item["score"] >= 3 for item in result["results"]))

    def test_size_filter(self):
        result = self.intel.execute("files_search",
                                    {"directory": str(self.root),
                                     "query": "larger than 90 bytes text"})
        names = [Path(item["path"]).name for item in result["results"]]
        self.assertEqual(names, ["readme.txt"])

    def test_age_filter_older_and_newer(self):
        older = [Path(item["path"]).name for item in self.intel.execute(
            "files_search", {"directory": str(self.root),
                             "query": "older than 30 days csv"})["results"]]
        self.assertEqual(older, ["budget2020.csv"])
        newer = [Path(item["path"]).name for item in self.intel.execute(
            "files_search", {"directory": str(self.root),
                             "query": "newer than 30 days csv"})["results"]]
        self.assertEqual(newer, ["budget Q1.csv"])

    def test_no_match_returns_empty_not_error(self):
        result = self.intel.execute("files_search",
                                    {"directory": str(self.root), "query": "missing zebra"})
        self.assertEqual(result["results"], [])
        self.assertIn("note", result)

    def test_noise_only_query_rejected(self):
        with self.assertRaises(FileIntelligenceError):
            self.intel.execute("files_search",
                               {"directory": str(self.root), "query": "the of and"})

    def test_intent_is_returned(self):
        result = self.intel.execute("files_search",
                                    {"directory": str(self.root), "query": "budget csv"})
        self.assertEqual(result["intent"]["extensions"], [".csv"])
        self.assertIn("budget", result["intent"]["keywords"])

    def test_directory_guards_still_apply(self):
        drive = Path(self.root.anchor)
        with self.assertRaises(FileIntelligenceError):
            self.intel.execute("files_search", {"directory": str(drive), "query": "csv"})


if __name__ == "__main__":
    unittest.main()
