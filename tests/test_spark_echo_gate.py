"""Offline tests for suppressing acoustic self-feedback in SPARK Live."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_echo_gate import EchoGate


class EchoGateTests(unittest.TestCase):
    def test_input_allowed_before_first_model_response(self):
        gate = EchoGate(tail_seconds=0.75)
        self.assertFalse(gate.mic_blocked(now=10.0))

    def test_model_output_blocks_mic_until_playback_drained_and_tail_expires(self):
        gate = EchoGate(tail_seconds=0.75)
        gate.on_output_received()
        self.assertTrue(gate.mic_blocked(now=10.0))
        gate.on_turn_finished(queue_empty=False, now=10.1)
        self.assertTrue(gate.mic_blocked(now=10.2))
        gate.on_playback_started()
        gate.on_playback_finished(queue_empty=True, now=10.5)
        self.assertTrue(gate.mic_blocked(now=11.0))
        self.assertFalse(gate.mic_blocked(now=11.26))

    def test_playback_in_progress_cannot_release_gate_at_turn_end(self):
        gate = EchoGate(tail_seconds=0.75)
        gate.on_output_received()
        gate.on_playback_started()
        gate.on_turn_finished(queue_empty=True, now=3)
        self.assertTrue(gate.mic_blocked(now=15))
        gate.on_playback_finished(queue_empty=True, now=15)
        self.assertTrue(gate.mic_blocked(now=15.5))
        self.assertFalse(gate.mic_blocked(now=15.76))

    def test_new_output_reblocks_tail_and_reconnect_clears_stale_state(self):
        gate = EchoGate(tail_seconds=0.75)
        gate.on_output_received()
        gate.on_turn_finished(queue_empty=True, now=1)
        self.assertTrue(gate.mic_blocked(now=1.25))
        gate.on_output_received()
        self.assertTrue(gate.mic_blocked(now=100))
        gate.reset()
        self.assertFalse(gate.mic_blocked(now=100))

    def test_nonempty_output_queue_keeps_mic_blocked_even_after_turn_completion(self):
        gate = EchoGate()
        gate.on_output_received()
        gate.on_turn_finished(queue_empty=False, now=1)
        gate.on_playback_finished(queue_empty=False, now=1.5)
        self.assertTrue(gate.mic_blocked(now=30))
        gate.on_playback_started()
        gate.on_playback_finished(queue_empty=True, now=30)
        self.assertFalse(gate.mic_blocked(now=30.8))


if __name__ == "__main__":
    unittest.main()
