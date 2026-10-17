"""Validate consented SPARK webcam frames before forwarding to Gemini."""
import base64
import binascii

MAX_FRAME_BYTES = 2 * 1024 * 1024
JPEG_HEADER = bytes((0xff, 0xd8, 0xff))


def validate_camera_frame(value):
    """Return JPEG bytes or raise ValueError without exposing frame contents."""
    if isinstance(value, str):
        if value.startswith("data:image/jpeg;base64,"):
            value = value.split(",", 1)[1]
        try:
            frame = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid camera frame encoding") from exc
    elif isinstance(value, bytes):
        frame = value
    else:
        raise ValueError("Invalid camera frame type")
    if not frame or len(frame) > MAX_FRAME_BYTES:
        raise ValueError("Camera frame empty or exceeds 2 MB limit")
    if not frame.startswith(JPEG_HEADER) or not frame.endswith(bytes((0xff, 0xd9))):
        raise ValueError("Camera frame is not a complete JPEG")
    return frame
