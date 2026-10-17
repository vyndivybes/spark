"""Cheap, bounded visualization telemetry from 16-bit PCM.

This never forwards raw audio data. It emits one integer at most 10 times
per second, without changing the PCM consumed by local speakers.
"""
import math
import struct
import time


class AudioMeter:
    def __init__(self, min_interval=0.1):
        self.min_interval = min_interval
        self.last_sent = None

    def sample(self, pcm, now=None):
        now = time.monotonic() if now is None else now
        if self.last_sent is not None and now - self.last_sent < self.min_interval:
            return None
        if not isinstance(pcm, bytes) or len(pcm) % 2:
            return None
        if not pcm:
            self.last_sent = now
            return 0
        samples = len(pcm) // 2
        power = sum(value * value for (value,) in struct.iter_unpack("<h", pcm))
        amplitude = math.isqrt(power // samples)
        self.last_sent = now
        return min(255, max(0, int(amplitude * 255 / 8000)))
