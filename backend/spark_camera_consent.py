"""Session-bound authorization for sending webcam frames to Gemini Live.

Opening the preview or authenticating locally never implies AI sharing consent.
This function is pure, so the server enforces the same decision on every frame.
"""


def can_stream_camera(*, provider, owner_sid, sender_sid, sharing_sid,
                      session_ready, authenticated):
    return bool(
        provider == "gemini"
        and owner_sid
        and sender_sid == owner_sid
        and sharing_sid == owner_sid
        and session_ready
        and authenticated
    )
