import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_live_config import live_model, live_status, live_error_message


class LiveConfigTests(unittest.TestCase):
    def test_current_free_tier_live_model_is_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(live_model(), "gemini-3.8-live")

    def test_explicit_supported_live_model_is_respected(self):
        with patch.dict(os.environ, {"SPARK_LIVE_MODEL": "gemini-3.1-flash-live-preview"}, clear=True):
            self.assertEqual(live_model(), "gemini-3.1-flash-live-preview")

    def test_old_ada_model_is_never_selected(self):
        with patch.dict(os.environ, {"SPARK_LIVE_MODEL": "models/gemini-2.5-flash-native-audio-preview-12-2025"}, clear=True):
            self.assertEqual(live_model(), "gemini-3.8-live")

    def test_credential_status_does_not_expose_key(self):
        value = live_status(True, "gemini-3.8-live")
        self.assertEqual(value["state"], "idle")
        self.assertEqual(value["model"], "gemini-3.8-live")
        missing = live_status(False, "gemini-3.8-live")
        self.assertEqual(missing["state"], "setup_required")
        self.assertNotIn("secret-example", str(missing))

    def test_live_error_categories_never_include_private_provider_body(self):
        for raw, expected in [
            ("Error HTTP 429: secret-example quota exceeded", "rate limit"),
            ("Error HTTP 403: secret-example", "permission"),
            ("Error HTTP 404: secret-example", "model"),
            ("Some deep stack internal secret-example", "connection")
        ]:
            result = live_error_message(Exception(raw))
            self.assertIn(expected, result.lower())
            self.assertNotIn("secret-example", result)


if __name__ == "__main__":
    unittest.main()
