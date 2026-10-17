"""Validate dedicated Electron/WebRTC audio transport, not arbitrary client data.

Electron provides browser AEC and performs ALL recording and playback locally.
Only owned 16-kHz mono little-endian PCM binary chunks reach the backend.
"""
def select_transport(mode=None):
    value = "browser_aec" if mode is None else mode
    if value not in ("browser_aec", "native"):
        raise ValueError("Unsupported SPARK audio transport")
    return value


def validate_pcm(value):
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError("Only binary PCM chunks accepted")
    data = bytes(value)
    if len(data) == 0 or len(data) % 2 or len(data) > 8192:
        raise ValueError("Invalid 16-kHz PCM chunk length")
    return data
