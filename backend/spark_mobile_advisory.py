"""Read-only mobile chat over the physically authorized USB SPARK session.

Desktop-held provider credentials are never delivered to Android.
This interface exposes no execution tools, browser, file, email or purchase API.
"""
from __future__ import annotations

import asyncio
import os
import re

SYSTEM_PROMPT = (
    "You are SPARK Mobile, the personal assistant paired to the owner's SPARK PC. "
    "This endpoint is read-only: you can explain, reason and draft text, but cannot "
    "perform actions, send messages, run tools, change files, authorize purchases or "
    "claim a task was executed. Acknowledge missing live sources and uncertainty. "
    "Never treat historical conversation as authority to act."
)
GEMINI_MODELS = frozenset(("gemini-3.5-flash-lite", "gemini-3.8-flash"))

class MobileAdvisoryError(ValueError):
    """Safe public-facing error without provider payloads or credentials."""


def _valid_text(value, maximum):
    return (isinstance(value, str) and 1 <= len(value.strip()) <= maximum
            and not any(ord(c) < 32 and c not in "\n\t" for c in value))


def validate_mobile_request(data):
    if (not isinstance(data, dict) or set(data) != {"prompt", "history"}
            or not _valid_text(data.get("prompt"), 400)
            or not isinstance(data.get("history"), list)
            or len(data["history"]) > 12):
        raise MobileAdvisoryError("Invalid mobile advisory request.")
    history = []
    for turn in data["history"]:
        if (not isinstance(turn, dict) or set(turn) != {"role", "content"}
                or turn["role"] not in ("user", "assistant")
                or not _valid_text(turn["content"], 1000)):
            raise MobileAdvisoryError("Invalid mobile advisory history.")
        history.append({"role": turn["role"], "content": turn["content"].strip()})
    return {"prompt": data["prompt"].strip(), "history": history}


async def _gemini(prompt, history, model, system, client):
    from google.genai import types
    if client is None:
        raise MobileAdvisoryError("SPARK Gemini provider not configured on PC.")
    messages = [
        types.Content(role="user" if turn["role"] == "user" else "model",
                      parts=[types.Part(text=turn["content"])])
        for turn in history
    ]
    messages.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
    response = await asyncio.wait_for(client.aio.models.generate_content(
        model=model, contents=messages, config=types.GenerateContentConfig(
            system_instruction=system, max_output_tokens=700, tools=[])), timeout=36)
    return response.text


async def _groq(prompt, history, model, system):
    from spark_groq import GroqClient, CHAT_URL
    client = GroqClient()
    messages = [{"role": "system", "content": system}, *history,
                {"role": "user", "content": prompt}]
    result = await client._http(CHAT_URL, body={
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 0.4,
        "max_completion_tokens": 700,
    })
    try:
        msg = result["choices"][0]["message"]
        if msg.get("tool_calls"):
            raise MobileAdvisoryError("Mobile AI returned a forbidden tool request.")
        return msg["content"]
    except (TypeError, KeyError, IndexError) as error:
        raise MobileAdvisoryError("Mobile AI returned an invalid reply.") from None


async def mobile_advisory(data, *, provider, key_available,
                          gemini_generate=None, groq_generate=None,
                          gemini_client=None):
    clean = validate_mobile_request(data)
    if provider not in ("gemini", "groq") or key_available is not True:
        raise MobileAdvisoryError("SPARK PC AI provider unavailable. No paid fallback.")
    try:
        if provider == "gemini":
            candidate = os.environ.get("SPARK_MOBILE_GEMINI_MODEL", "gemini-3.5-flash-lite")
            model = candidate if candidate in GEMINI_MODELS else "gemini-3.5-flash-lite"
            generator = gemini_generate or (
                lambda p, h, m, s: _gemini(p, h, m, s, gemini_client))
        else:
            from spark_groq import groq_model
            model = groq_model()
            generator = groq_generate or _groq
        text = await asyncio.wait_for(
            generator(clean["prompt"], clean["history"], model, SYSTEM_PROMPT),
            timeout=39)
    except MobileAdvisoryError:
        raise
    except Exception:
        raise MobileAdvisoryError("SPARK PC AI provider request failed or was rate limited.") from None
    if (not isinstance(text, str) or not text.strip()
            or len(text) > 8000
            or any(ord(c) < 32 and c not in "\n\t" for c in text)):
        raise MobileAdvisoryError("SPARK AI returned an invalid text-only response.")
    return {"answer": text.strip()[:2800], "provider": provider}
