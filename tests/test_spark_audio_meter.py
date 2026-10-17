"""SPARK UI audio-meter tests: compact, throttled, never PCM transport."""
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_audio_meter import AudioMeter


class AudioMeterTests(unittest.TestCase):
    def test_silence_and_loud_pcm_are_bounded_small_values(self):
        meter = AudioMeter()
        self.assertEqual(meter.sample(b"\x00\x00" * 1024, now=1.0), 0)
        self.assertEqual(meter.sample(struct.pack("<1024h", *([12000] * 1024)), now=1.2), 255)

    def test_meter_limits_ui_event_rate(self):
        meter = AudioMeter()
        pcm = b"\x00\x00" * 512
        self.assertEqual(meter.sample(pcm, now=1.0), 0)
        self.assertIsNone(meter.sample(pcm, now=1.01))
        self.assertIsNone(meter.sample(pcm, now=1.08))
        self.assertEqual(meter.sample(pcm, now=1.12), 0)

    def test_invalid_pcm_never_emits_raw_audio(self):
        meter = AudioMeter()
        self.assertEqual(meter.sample(b"", now=1.0), 0)
        self.assertIsNone(meter.sample(b"\x01", now=1.2))

if __name__ == "__main__":
    unittest.main()
