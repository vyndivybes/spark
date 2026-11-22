import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_brahma_composer import compose, LICENSE_STATUS

class ComposerTests(unittest.TestCase):
    def test_never_claims_execution(self):
        result = compose()
        self.assertTrue(result["analysis_only"])
        self.assertEqual(result["source_count"], 4)
        self.assertEqual(len(result["candidates"]), 8)
        self.assertTrue(all(r["baseline"] == "unverified" and not r["execution_enabled"]
                            and not r["tests_passed"] for r in result["candidates"]))

    def test_license_gates(self):
        for row in compose()["candidates"]:
            expected = ("limited_reuse_with_attribution"
                        if row["source"] == "Brahma-AI---Modular-Chrome-OS"
                        else "inspiration_only_until_review")
            self.assertEqual(row["reuse_policy"], expected)
        self.assertEqual(LICENSE_STATUS["Brahma-sol"], "conflict_review")

    def test_deduplicate_verified_capability(self):
        rows = {r["feature"]: r for r in compose(
            confirmed_existing={"browser_context": True, "android_pairing": False}
        )["candidates"]}
        self.assertEqual(rows["browser_context"]["next_step"], "do_not_duplicate")
        self.assertEqual(rows["android_pairing"]["baseline"], "verified_missing")
        self.assertFalse(rows["android_pairing"]["execution_enabled"])

    def test_rejects_untrusted_evidence(self):
        with self.assertRaises(ValueError):
            compose(license_overrides={"Brahma-Ai-Evo": "mit"})
        for evidence in ({"unknown": True}, {"android_pairing": "yes"},
                         {"android_pairing": 1}):
            with self.assertRaises(ValueError):
                compose(confirmed_existing=evidence)
        with self.assertRaises(TypeError):
            compose(confirmed_existing=["android_pairing"])

    def test_deterministic(self):
        self.assertEqual(compose(), compose())

if __name__ == "__main__":
    unittest.main()
