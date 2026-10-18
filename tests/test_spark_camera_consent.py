"""Explicit session-level permission for frames sent to the selected AI."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_camera_consent import can_stream_camera


class CameraConsentTests(unittest.TestCase):
    def test_valid_gemini_owner_may_stream_only_after_consent(self):
        self.assertTrue(can_stream_camera(
            provider="gemini", owner_sid="owner", sender_sid="owner",
            sharing_sid="owner", session_ready=True, authenticated=True))

    def test_local_preview_does_not_implicitly_grant_consent(self):
        self.assertFalse(can_stream_camera(
            provider="gemini", owner_sid="owner", sender_sid="owner",
            sharing_sid=None, session_ready=True, authenticated=True))

    def test_groq_voice_must_never_receive_camera_frames(self):
        self.assertFalse(can_stream_camera(
            provider="groq", owner_sid="owner", sender_sid="owner",
            sharing_sid="owner", session_ready=True, authenticated=True))

    def test_cross_client_frame_and_stale_owner_consent_blocked(self):
        for owner_sid, sender_sid, sharing_sid in (
            ("owner", "other", "owner"),
            ("owner", "owner", "other"),
            (None, "owner", "owner"),
            ("owner", None, "owner"),
        ):
            with self.subTest(sender_sid=sender_sid, sharing_sid=sharing_sid):
                self.assertFalse(can_stream_camera(
                    provider="gemini", owner_sid=owner_sid, sender_sid=sender_sid,
                    sharing_sid=sharing_sid, session_ready=True, authenticated=True))

    def test_closed_session_and_authentication_lock_block_stream(self):
        for session_ready, authenticated in ((False, True), (True, False)):
            self.assertFalse(can_stream_camera(
                provider="gemini", owner_sid="owner", sender_sid="owner",
                sharing_sid="owner", session_ready=session_ready,
                authenticated=authenticated))


if __name__ == "__main__":
    unittest.main()
