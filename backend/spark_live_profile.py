"""Safe, opt-in SPARK Live connection profiles.

The 'voice' profile duplicates the verified one-shot Gemini Live handshake's
configuration exactly. It still uses the normal microphone and speaker
streaming paths after connecting, but it offers no model-initiated tool use,
grounding or transcription until explicitly restored by the 'full' profile.
"""
import os


def live_profile():
    choice = os.environ.get("SPARK_LIVE_PROFILE", "full").strip().lower()
    return choice if choice in ("full", "voice") else "full"


def select_live_config(profile, full_config):
    if profile == "voice":
        return {"response_modalities": ["AUDIO"]}
    if profile == "full":
        return full_config
    raise ValueError("Unsupported SPARK Live profile")
