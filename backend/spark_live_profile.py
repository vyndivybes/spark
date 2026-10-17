"""SPARK Live voice profiles.

'voice' is the exact minimum proven to connect on this Windows device.
'cinematic' adds only a supported prebuilt speaker + original persona.
'full' remains explicitly available for advanced tools but requires its
own independent Windows provider/device acceptance.
"""
import os
from spark_cinematic_tools import CINEMATIC_FUNCTIONS


CINEMATIC_SYSTEM_INSTRUCTION = (
    "Your name is SPARK. You are a fictional personal AI command-center "
    "assistant with an original voice and persona. Speak with refined, "
    "understated British English diction, smooth low-register resonance, "
    "a calm measured cadence and carefully articulated consonants. "
    "Sound composed, precise, warm, quietly confident and intelligently "
    "witty, like an elegant high-tech aerospace mission-control assistant. "
    "Use subtle dry humour sparingly. Address the user as 'sir' only when "
    "natural and not in every sentence. Make replies concise and useful. "
    "Avoid theatrical shouting, drawn-out pauses, repetitive greetings, "
    "and overly emphatic delivery. Do not imitate any existing film "
    "character, actor, or recording; maintain your own distinct identity. "
    "Never claim to have performed a computer action you cannot verify. "
    "No tools are provided in cinematic voice mode."
)


def live_profile():
    choice = os.environ.get("SPARK_LIVE_PROFILE", "cinematic").strip().lower()
    # The known-good one-line profile is the fail-closed fallback.
    return choice if choice in ("full", "voice", "cinematic", "cinematic_tools") else "voice"


def select_live_config(profile, full_config):
    if profile == "voice":
        return {"response_modalities": ["AUDIO"]}
    if profile == "cinematic":
        return {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {"voice_name": "Charon"}
                }
            },
            "system_instruction": CINEMATIC_SYSTEM_INSTRUCTION,
        }
    if profile == "cinematic_tools":
        # Opt-in Stage-6 profile: same known-good Charon voice and audio path,
        # only two small synchronous functions. Never copy legacy tool config.
        output = select_live_config("cinematic", full_config)
        output["system_instruction"] = output["system_instruction"].replace(
            "No tools are provided in cinematic voice mode.",
            "You may call only the declared read-only system-status tool and "
            "approval-gated application launcher. Never claim an action "
            "succeeded until the tool returns success. If approval is denied "
            "or times out, explain this briefly and continue listening."
        )
        output["tools"] = [{"function_declarations": CINEMATIC_FUNCTIONS}]
        return output
    if profile == "full":
        return full_config
    raise ValueError("Unsupported SPARK Live profile")
