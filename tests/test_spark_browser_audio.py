"""Tests for the fail-closed 16-kHz microphone PCM socket protocol."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_browser_audio import validate_pcm, select_transport

class BrowserAudioTests(unittest.TestCase):
    def test_transport_defaults_handsfree_and_preserves_native_escape_hatch(self):
        self.assertEqual(select_transport(None), "browser_aec")
        self.assertEqual(select_transport("native"), "native")
        with self.assertRaises(ValueError):
            select_transport("unknown")

    def test_accepts_little_endian_binary_chunks(self):
        pcm = bytes(3200)
        self.assertEqual(validate_pcm(pcm), pcm)
        self.assertEqual(validate_pcm(bytearray(pcm)), pcm)
        self.assertEqual(validate_pcm(memoryview(pcm)), pcm)

    def test_refuses_text_oversized_odd_empty_pcm(self):
        for invalid in ("hello", {"data":"secret"}, bytes(13000), b"", b"\x01"):
            with self.subTest(invalid=type(invalid)):
                with self.assertRaises(ValueError):
                    validate_pcm(invalid)

if __name__ == "__main__":
    unittest.main()
