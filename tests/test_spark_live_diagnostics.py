"""Safe status diagnostics for Live API failure without exposing provider error text."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_live_config import live_status_report


class LiveStatusReportTests(unittest.TestCase):
    def test_quota_error_is_specific_and_safe(self):
        result = live_status_report("error", "Gemini Live rate limit or quota reached (429). Check AI Studio usage; do not retry repeatedly.")
        self.assertEqual(result["live_state"], "error")
        self.assertEqual(result["live_error_code"], 429)
        self.assertIn("quota", result["live_message"].lower())

    def test_unknown_failure_does_not_leak_provider_or_credentials(self):
        result = live_status_report("error", "connection rejected with api_key=SECRET-DO-NOT-SHARE")
        self.assertEqual(result["live_state"], "error")
        self.assertEqual(result["live_error_code"], None)
        self.assertNotIn("SECRET", str(result))
        self.assertNotIn("api_key", str(result))

    def test_permission_failure_is_distinct(self):
        result = live_status_report("error", "Gemini Live permission or API key error (401/403). Check the configured Google project.")
        self.assertEqual(result["live_error_code"], 401)

    def test_connected_status_reports_no_prior_error(self):
        result = live_status_report("connected", "SPARK Core connected to Gemini Live.")
        self.assertEqual(result["live_state"], "connected")
        self.assertIsNone(result["live_error_code"])
        self.assertEqual(result["live_message"], "SPARK Core connected to Gemini Live.")

if __name__ == "__main__":
    unittest.main()
