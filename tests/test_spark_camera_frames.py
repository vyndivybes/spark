import base64
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).resolve().parents[1] / "backend" / "spark_camera_frames.py"
s = importlib.util.spec_from_file_location("spark_camera_frames", p)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)
JPEG = bytes((255,216,255,0,1,255,217))

class FrameChecks(unittest.TestCase):
    def test_valid_binary(self):
        self.assertEqual(m.validate_camera_frame(JPEG), JPEG)

    def test_valid_base64(self):
        self.assertEqual(m.validate_camera_frame(base64.b64encode(JPEG).decode()), JPEG)

    def test_reject_invalid(self):
        for value in [None, {}, b"", b"invalid", "not-base64", b"\xff\xd8\xffpartial"]:
            with self.subTest(value=type(value)):
                with self.assertRaises(ValueError):
                    m.validate_camera_frame(value)

    def test_reject_oversize(self):
        with self.assertRaises(ValueError):
            m.validate_camera_frame(bytes((255,216,255)) + b"x" * (2*1024*1024) + bytes((255,217)))

if __name__ == "__main__":
    unittest.main()
