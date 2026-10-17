"""Stage-6 SPARK tool use: explicit opt-in, narrow schemas, no silent desktop actions."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_live_profile import live_profile, select_live_config
from spark_cinematic_tools import (
    allowed_live_tool, tool_confirmation_required, get_system_status, CINEMATIC_FUNCTIONS
)

class Stage6ToolsTests(unittest.TestCase):
    def test_default_cinematic_handshake_is_byte_for_byte_config_unchanged(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(live_profile(), "cinematic")
        conf = select_live_config("cinematic", {"tools": ["unsafe"]})
        self.assertNotIn("tools", conf)

    def test_opt_in_retains_original_voice_and_only_two_function_declarations(self):
        c = select_live_config("cinematic_tools", {"tools": ["unsafe"]})
        base = select_live_config("cinematic", {"tools": ["unsafe"]})
        for k in ("response_modalities", "speech_config"):
            self.assertEqual(c[k], base[k])
        self.assertEqual(len(c["tools"]), 1)
        names=[x["name"] for x in c["tools"][0]["function_declarations"]]
        self.assertEqual(names, ["get_system_status", "launch_desktop_app"])
        self.assertEqual(names, [x["name"] for x in CINEMATIC_FUNCTIONS])
        self.assertNotIn("google_search", str(c))
        self.assertNotIn("NON_BLOCKING", str(c))

    def test_optin_profile_explicit_only(self):
        with patch.dict("os.environ", {"SPARK_LIVE_PROFILE":"cinematic_tools"},clear=True):
            self.assertEqual(live_profile(), "cinematic_tools")
        with patch.dict("os.environ", {"SPARK_LIVE_PROFILE":"bogus"},clear=True):
            self.assertEqual(live_profile(), "voice")

    def test_profile_level_executable_tool_enforcement(self):
        for name in ("get_system_status","launch_desktop_app"):
            self.assertTrue(allowed_live_tool("cinematic_tools", name))
        for unsafe in ("run_web_agent","write_file","generate_cad","read_directory",
                       "control_light","print_stl","read_file","__import__",""):
            self.assertFalse(allowed_live_tool("cinematic_tools", unsafe))
        self.assertFalse(allowed_live_tool("cinematic", "launch_desktop_app"))
        self.assertTrue(allowed_live_tool("full", "launch_desktop_app"))

    def test_desktop_requires_confirmation_even_when_tool_permissions_disabled(self):
        self.assertTrue(tool_confirmation_required("launch_desktop_app", {"launch_desktop_app":False}))
        self.assertFalse(tool_confirmation_required("get_system_status", {"get_system_status":False}))
        self.assertTrue(tool_confirmation_required("write_file", {"write_file":True}))

    def test_system_status_is_safe_and_read_only(self):
        result = get_system_status(platform_name="Windows", clock="12:30 IST")
        self.assertEqual(result, {"service":"SPARK Core", "operating_system":"Windows",
                                  "local_time":"12:30 IST"})
        self.assertNotIn("password", str(result).lower())
        self.assertNotIn("API_KEY", str(result))

if __name__ == "__main__":
    unittest.main()
