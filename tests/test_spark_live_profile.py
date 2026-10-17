"""Regression: the validated minimal Live handshake must be usable by actual SPARK voice."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_live_profile import live_profile, select_live_config


class VoiceProfileTests(unittest.TestCase):
    def test_cinematic_default_voice(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(live_profile(), "cinematic")

    def test_voice_only_uses_exact_minimal_handshake_config(self):
        with patch.dict("os.environ", {"SPARK_LIVE_PROFILE": "voice"}, clear=True):
            self.assertEqual(live_profile(), "voice")
            self.assertEqual(select_live_config("voice", {"tools": ["unsafe"]}),
                             {"response_modalities": ["AUDIO"]})

    def test_full_retains_tool_configuration(self):
        full = {"response_modalities": ["AUDIO"], "tools": ["expected"]}
        self.assertIs(select_live_config("full", full), full)


    def test_cinematic_has_filmic_british_delivery_without_tools(self):
        profile = select_live_config("cinematic", {"tools": ["unapproved"], "output_audio_transcription": {}})
        self.assertEqual(profile["response_modalities"], ["AUDIO"])
        self.assertEqual(
            profile["speech_config"]["voice_config"]["prebuilt_voice_config"]["voice_name"],
            "Charon"
        )
        self.assertIn("British", profile["system_instruction"])
        self.assertIn("SPARK", profile["system_instruction"])
        self.assertNotIn("tools", profile)
        self.assertNotIn("output_audio_transcription", profile)
        self.assertNotIn("input_audio_transcription", profile)

    def test_unknown_profile_cannot_enable_sensitive_tools(self):
        with patch.dict("os.environ", {"SPARK_LIVE_PROFILE": "untrusted"}, clear=True):
            self.assertEqual(live_profile(), "voice")
        with self.assertRaises(ValueError):
            select_live_config("untrusted", {"tools": ["unapproved"]})


if __name__ == "__main__":
    unittest.main()
