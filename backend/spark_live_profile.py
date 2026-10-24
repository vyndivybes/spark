"""SPARK Live voice profiles.

'voice' is the exact minimum proven to connect on this Windows device.
'cinematic' adds only a supported prebuilt speaker + original persona.
'full' remains explicitly available for advanced tools but requires its
own independent Windows provider/device acceptance.
"""
import os
from spark_cinematic_tools import (
    insight_function_declarations,
    live_function_declarations,
    live_integration_summary,
)


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
    "You remember your ongoing conversation with this user and carry its "
    "context naturally, so a returning user feels recognised rather than "
    "greeted cold. Reference earlier topics, decisions and preferences only "
    "when relevant, never by reciting them back as a list; if genuinely "
    "relevant history was supplied, let it warm and inform your reply the way "
    "a person who was listening would. Never invent past exchanges. "
)

# The ONLY tools the plain cinematic profile may call, enforced again at
# dispatch by allowed_live_tool(). Everything below is read-only.
CINEMATIC_INSIGHT_NOTE = (
    "You have only this read-only inspection toolbox: get_spark_git_status, "
    "get_spark_backend_health, get_spark_policy, get_spark_release_history, "
    "inspect_self, search_source_code, read_source_file and "
    "list_project_files. For any question about SPARK's version, Git state, "
    "backend health, evolution policy, releases or its own source code, call "
    "the matching tool first and answer only from its evidence; for the name "
    "of a code symbol use search_source_code, and read_source_file only "
    "against files the search already located. Distinguish three cases "
    "plainly: a tool you could not call is unavailable, a tool that reported "
    "an error means the access failed, and a tool that reported not-found "
    "means the requested thing does not exist. Never claim you inspected, "
    "read or verified anything without a successful tool result, and never "
    "claim a symbol is missing until search_source_code returned no match."
)


def live_profile():
    choice = os.environ.get("SPARK_LIVE_PROFILE", "cinematic").strip().lower()
    # The known-good one-line profile is the fail-closed fallback.
    if choice == "cinematic_search":
        # Grounding can incur charges on a paid-tier Google AI project.
        # Never enable it without the launcher's explicit second opt-in.
        return "cinematic_search" if os.environ.get("SPARK_ENABLE_GOOGLE_SEARCH") == "1" else "cinematic_tools"
    return choice if choice in ("full", "voice", "cinematic", "cinematic_tools") else "voice"


def select_live_config(profile, full_config):
    if profile == "voice":
        return {"response_modalities": ["AUDIO"]}
    if profile == "cinematic":
        output = {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {"voice_name": "Charon"}
                }
            },
            "system_instruction": CINEMATIC_SYSTEM_INSTRUCTION + CINEMATIC_INSIGHT_NOTE,
        }
        # Exactly one read-only declaration block; caller-supplied tools can
        # never leak through: full_config is deliberately not used here.
        output["tools"] = [{"function_declarations": insight_function_declarations()}]
        return output
    if profile == "cinematic_tools":
        # Opt-in Stage-6 profile: same known-good Charon voice and audio path,
        # the read-only inspection toolbox plus two small synchronous
        # functions. Never copy legacy tool config.
        output = select_live_config("cinematic", full_config)
        output["system_instruction"] = output["system_instruction"].replace(
            CINEMATIC_INSIGHT_NOTE,
            "You may call the read-only system-status and SPARK graph tools, plus the "
            "approval-gated application launcher. Never claim an action "
            "succeeded until the tool returns success. If approval is denied "
            "or times out, explain this briefly and continue listening."
        )
        output["system_instruction"] = (
            output["system_instruction"] + CINEMATIC_INSIGHT_NOTE.rstrip(".") + "."
        )
        output["system_instruction"] += (
            " IMPORTANT: For ANY question about SPARK's own code, architecture, "
            "modules, files, dependencies, wiring, or how components connect "
            "(including Jarvis, the voice loop, Groq, the backend, Electron, or "
            "Graphify), you MUST call the query_spark_graph tool FIRST and answer "
            "ONLY from the evidence it returns, citing the file paths. Do not say "
            "the information is unavailable before calling query_spark_graph. "
            "Never answer architecture questions from memory. If the tool fails, "
            "say so plainly; never invent a graph lookup."
            " For questions about the user's OWN project history, decisions, "
            "hardware, timelines, or 'what did we decide/when/change', use "
            "search_spark_timeline. For questions about a specific named thing "
            "(device, project, part, decision), use get_spark_entity_history. "
            "Always report Graphiti results as recorded history (note if facts "
            "were superseded) and say plainly if nothing is found."
        )
        # Only describes services this launch actually registered, so the model
        # is never invited to call a tool that would answer 'not configured'.
        output["system_instruction"] += live_integration_summary()
        # Read-only inspection declarations first, then this launch's
        # synchronous/integration declarations; nothing is widened by callers.
        output["tools"] = [{"function_declarations":
                            insight_function_declarations() + live_function_declarations()}]
        return output
    if profile == "cinematic_search":
        if os.environ.get("SPARK_ENABLE_GOOGLE_SEARCH") != "1":
            raise ValueError("Google grounding requires explicit SPARK_ENABLE_GOOGLE_SEARCH opt-in")
        # Gemini Live docs support native Grounding with Google Search
        # alongside synchronous function calling. Preserve Stage-6 actions.
        output = select_live_config("cinematic_tools", full_config)
        output["tools"] = [{"google_search": {}}] + output["tools"]
        output["system_instruction"] += (
            " Use Google Search for recent or uncertain external facts. "
            "Ground factual claims in retrieved sources; when grounding is "
            "unavailable, say you could not verify the information. "
            "Use approved local tools only for the exact actions requested. "
            "Do not invent source titles, links or search results."
        )
        return output
    if profile == "full":
        return full_config
    raise ValueError("Unsupported SPARK Live profile")
