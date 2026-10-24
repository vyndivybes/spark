"""Half-duplex protection for SPARK's microphone-to-Gemini audio stream.

In cinematic mode, the mic stays blocked after each assistant reply until
a new explicit user gesture rearms it, preventing recurring self-conversation.
The legacy voice profile still has its previous automatic cooldown behavior.
"""
import time


class EchoGate:
    def __init__(self, tail_seconds=0.75, require_rearm=False):
        if tail_seconds < 0:
            raise ValueError("tail_seconds must be nonnegative")
        self.tail_seconds = tail_seconds
        self.require_rearm = require_rearm
        self.reset()

    def reset(self, hold_for_rearm=False, now=None):
        self._output_active = False
        self._writing = False
        self._turn_finished = False
        # Provider reconnects must never silently unlock cinematic mic.
        # A short speaker tail protects against buffered Windows playback.
        self._release_at = ((time.monotonic() if now is None else now)
                            + self.tail_seconds) if hold_for_rearm else 0.0
        self._needs_rearm = bool(hold_for_rearm and self.require_rearm)

    def on_output_received(self):
        first_packet = not self._output_active
        self._output_active = True
        self._turn_finished = False
        if self.require_rearm:
            self._needs_rearm = True
        return first_packet

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
        return (self._output_active or current < self._release_at
                or (self.require_rearm and self._needs_rearm))

    def rearm(self, now=None):
        """Allow one new user turn, but never while speaker or tail is active."""
        current = time.monotonic() if now is None else now
        if self._output_active or current < self._release_at:
            return False
        self._needs_rearm = False
        return True

    def block_reason(self, now=None):
        """Read-only cockpit diagnostic: why the mic is currently blocked.

        Additive companion of mic_blocked(); logic duplication is avoided by
        deriving the reason from the same state mic_blocked inspects.
        """
        current = time.monotonic() if now is None else now
        if self._output_active:
            return "speaker"
        if current < self._release_at:
            return "tail"
        if self.require_rearm and self._needs_rearm:
            return "rearm"
        return None
