"""Regression: the validated minimal Live handshake must be usable by actual SPARK voice."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_live_profile import live_profile, select_live_config


class VoiceProfileTests(unittest.TestCase):
    def test_default_preserves_existing_full_capabilities(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(live_profile(), "full")

    def test_voice_only_uses_exact_minimal_handshake_config(self):
        with patch.dict("os.environ", {"SPARK_LIVE_PROFILE": "voice"}, clear=True):
            self.assertEqual(live_profile(), "voice")
            self.assertEqual(select_live_config("voice", {"tools": ["unsafe"]}),
                             {"response_modalities": ["AUDIO"]})

    def test_full_retains_tool_configuration(self):
        full = {"response_modalities": ["AUDIO"], "tools": ["expected"]}
        self.assertIs(select_live_config("full", full), full)

    def test_unknown_profile_fails_closed_to_full(self):
        with patch.dict("os.environ", {"SPARK_LIVE_PROFILE": "untrusted"}, clear=True):
            self.assertEqual(live_profile(), "full")
        with self.assertRaises(ValueError):
            select_live_config("untrusted", {"tools": []})


if __name__ == "__main__":
    unittest.main()
