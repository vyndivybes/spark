"""One-shot, opt-in Gemini Live handshake diagnostic for the SPARK project.

Uses the same official Google Gen AI SDK and v1beta API as SPARK, but ONLY
connects with AUDIO modality. No microphone, speaker, camera, SPARK tools,
transcriptions, browser, file access, loops, or generation requests.
The user must explicitly pass --attempt-once to make a live network call.
The connection may count against Google project quotas; never auto-retry.
"""
import argparse
import asyncio
import json
from pathlib import Path

from spark_gemini_preflight import read_key

_ALLOWED = ("gemini-3.8-live", "gemini-3.1-flash-live-preview")


def validate_model(model):
    if model not in _ALLOWED:
        raise ValueError("Only explicitly supported Gemini Live models are permitted")
    return model


async def connect_once(client, model):
    """Perform a single minimal WebSocket setup; send no prompts or audio."""
    chosen = validate_model(model)
    async with client.aio.live.connect(
        model=chosen, config={"response_modalities": ["AUDIO"]}
    ):
        return {"state": "connected", "model": chosen,
                "category": "minimal_handshake_only"}


def classify_error(error):
    """Categorize the failure but never expose raw exception or key material."""
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return {"state": "rejected", "category": "timeout", "http_status": None}
    message = str(error).lower()
    # An SDK status field is preferable to extracting a number from arbitrary
    # provider text, but WebSocket errors may only expose reason strings.
    status = getattr(error, "status_code", None)
    if not isinstance(status, int):
        status = getattr(error, "code", None)
    if not isinstance(status, int) or status not in (400, 401, 403, 404, 429):
        status = None
    if status == 429 or "429" in message or "resource_exhausted" in message or "quota" in message:
        category, status = "quota_or_rate_limit", 429
    elif status == 400 or "400" in message or "invalid_argument" in message:
        category, status = "invalid_request", 400
    elif status in (401, 403) or "401" in message or "403" in message:
        category, status = "authentication_or_permission", status or (401 if "401" in message else 403)
    elif status == 404 or "404" in message or "not_found" in message:
        category, status = "model_or_endpoint_unavailable", 404
    else:
        category = "network_or_protocol_error"
    return {"state": "rejected", "category": category, "http_status": status}


def main():
    parser = argparse.ArgumentParser(
        description="One isolated Gemini Live WebSocket handshake; no audio or tools.")
    parser.add_argument("--model", choices=_ALLOWED, default="gemini-3.8-live")
    parser.add_argument("--attempt-once", action="store_true",
                        help="Explicitly authorize exactly one connection attempt.")
    args = parser.parse_args()
    if not args.attempt_once:
        print(json.dumps({"state": "no_connection_attempted",
                          "reason": "Use --attempt-once to authorize one network call."}))
        return 2
    root = Path(__file__).resolve().parents[1]
    key, source = read_key(root, allow_arkus=False)
    if not key:
        print(json.dumps({"state": "setup_required", "key_source": source}))
        return 2
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(
            api_key=key, http_options=types.HttpOptions(api_version="v1beta")
        )
        try:
            result = asyncio.run(asyncio.wait_for(
                connect_once(client, args.model), timeout=20
            ))
        finally:
            client.close()
    except Exception as exc:
        result = classify_error(exc)
        result["model"] = args.model
    result["key_source"] = source
    result["note"] = (
        "Single SDK WebSocket handshake only; no prompt, tool or audio."
    )
    print(json.dumps(result))
    return 0 if result["state"] == "connected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
