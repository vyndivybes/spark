"""Prevent SPARK Live from feeding its own loudspeaker output to the mic.

Half-duplex is a deliberate safe default until a tested acoustic echo
canceller is available. Gate starts on the *first received model PCM packet*,
not only when playback begins. It releases after the final queued speaker
chunk is played and a short acoustic tail has elapsed.
"""
import time


class EchoGate:
    def __init__(self, tail_seconds=0.75):
        if tail_seconds < 0:
            raise ValueError("tail_seconds must be nonnegative")
        self.tail_seconds = tail_seconds
        self.reset()

    def reset(self):
        self._output_active = False
        self._writing = False
        self._turn_finished = False
        self._release_at = 0.0

    def on_output_received(self):
        self._output_active = True
        self._turn_finished = False

    def on_playback_started(self):
        self._writing = True
        self._output_active = True

    def _release(self, now):
        self._output_active = False
        self._release_at = now + self.tail_seconds

    def on_turn_finished(self, queue_empty, now=None):
        self._turn_finished = True
        if self._output_active and queue_empty and not self._writing:
            self._release(time.monotonic() if now is None else now)

    def on_playback_finished(self, queue_empty, now=None):
        self._writing = False
        if self._output_active and self._turn_finished and queue_empty:
            self._release(time.monotonic() if now is None else now)

    def mic_blocked(self, now=None):
        current = time.monotonic() if now is None else now
        return self._output_active or current < self._release_at
