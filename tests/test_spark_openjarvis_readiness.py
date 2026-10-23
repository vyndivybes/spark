"""Source-only capability inventory regression tests; no external systems."""
from pathlib import Path
import tempfile
import unittest
from backend.spark_openjarvis_readiness import FEATURES, inventory


class ReadinessTests(unittest.TestCase):
    def test_exactly_sixteen_unique_capabilities(self):
        self.assertEqual(len(FEATURES), 16)
        self.assertEqual([f.number for f in FEATURES], list(range(1, 17)))
        self.assertEqual(len({f.slug for f in FEATURES}), 16)

    def test_empty_repo_never_claims_connected_or_verified(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "backend").mkdir()
            result = inventory(root)
            self.assertEqual(result["count"], 16)
            self.assertEqual(result["verified_live_count"], 0)
            self.assertTrue(all(f["live_status"] == "UNVERIFIED" for f in result["features"]))
            self.assertTrue(all(f["source_status"] == "NO_FOUNDATION_FOUND" for f in result["features"]))

    def test_source_presence_is_not_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "backend").mkdir()
            (root / "backend/spark_google_mcp.py").write_text("pass", encoding="utf-8")
            result = inventory(root)
            first = result["features"][0]
            self.assertEqual(first["source_status"], "FOUNDATION_PRESENT")
            self.assertEqual(first["live_status"], "UNVERIFIED")
            self.assertEqual(result["verified_live_count"], 0)

    def test_missing_backend_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                inventory(d)

    def test_provenance_fields_are_populated(self):
        for feature in FEATURES:
            self.assertIn(feature.priority, ("P1", "P2", "P3"))
            self.assertTrue(feature.live_acceptance)
            self.assertTrue(feature.foundation_paths)
            self.assertTrue(all(p.startswith(("backend/", "tests/")) for p in feature.foundation_paths))


if __name__ == "__main__":
    unittest.main()
