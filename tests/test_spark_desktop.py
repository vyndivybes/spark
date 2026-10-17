import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "backend" / "spark_desktop.py"
spec = importlib.util.spec_from_file_location("spark_desktop", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class LaunchPolicyTest(unittest.TestCase):
    def test_only_allowlisted_windows_application(self):
        calls = []
        def stub(*args, **kwargs):
            calls.append((args, kwargs))
        result = mod.launch_allowed_app("notepad", platform="win32", starter=stub)
        self.assertTrue(result["ok"])
        self.assertEqual(calls[0][0][0], ["notepad.exe"])
        self.assertFalse(calls[0][1]["shell"])

    def test_reject_untrusted_commands(self):
        for s in ["cmd.exe", "powershell", "../calc.exe", "notepad.exe", "", None]:
            with self.subTest(s=s):
                self.assertFalse(mod.launch_allowed_app(s, platform="win32")["ok"])

    def test_reject_non_windows(self):
        self.assertFalse(mod.launch_allowed_app("notepad", platform="linux")["ok"])

if __name__ == "__main__":
    unittest.main()
