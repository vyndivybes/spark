"""One-shot, opt-in live Gemini tool-invocation demonstration for SPARK.

Unlike scripts/spark_live_handshake.py (handshake only), this proves the
repaired conversation-to-tools chain against the real Gemini Live service:

  config  = select_live_config(live_profile(), ...)   (exact SPARK handshake)
  model   = live_model()                              (exact SPARK model)
  connect -> one text turn asking SPARK-internal questions (Git/policy/source)
  -> Gemini returns tool_call(s)
  -> dispatched through the REAL AudioLoop.answer_mcp_tool()
  -> returned via the REAL session.send_tool_response()
  -> model answers from the returned evidence.

Caps that are never exceeded: exactly ONE connection attempt, one user turn,
at most two tool-call rounds, one session, short timeouts, one process.
No microphone, speaker, camera, Electron, generation loops or shell.
The user must pass --attempt-once to authorize the single network call.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def classify_error(error):
    """Same honest classification as the handshake diagnostic, no raw detail."""
    message = str(error).lower()
    status = getattr(error, "status_code", None)
    if not isinstance(status, int):
        status = getattr(error, "code", None)
    if not isinstance(status, int) or status not in (400, 401, 403, 404, 429):
        status = None
    if status == 429 or "429" in message or "resource_exhausted" in message or "quota" in message:
        return {"state": "rejected", "category": "quota_or_rate_limit", "http_status": 429}
    if status == 400 or "400" in message or "invalid_argument" in message:
        return {"state": "rejected", "category": "invalid_request", "http_status": 400}
    if status in (401, 403):
        return {"state": "rejected", "category": "authentication_or_permission",
                "http_status": status}
    if status == 404 or "not found" in message or "1008" in message:
        return {"state": "rejected", "category": "model_or_endpoint_unavailable",
                "http_status": 404}
    return {"state": "rejected", "category": "network_or_protocol_error", "http_status": None}


async def demo_session(client, model, config):
    from google.genai import types
    import spark
    loop = spark.AudioLoop()
    evidence = {"model": model,
                "declared_tools": [tool["name"] for tool in
                                   (config.get("tools") or [{}])[0].get(
                                       "function_declarations", [])],
                "dispatched": [], "rounds": 0, "turn_audio_parts": 0,
                "turns_completed": 0}
    turn = (
        "Report SPARK's actual Git status now, the current evolution-policy "
        "setting for upgrades, and tell me the exact source file where "
        "EchoGate.block_reason is defined. Use your inspection tools and "
        "answer only from the evidence they return."
    )
    deadline = time.monotonic() + 90.0
    async with client.aio.live.connect(model=model, config=config) as session:
        session.send_client_content(
            turns=types.Content(role="user",
                                parts=[types.Part(text=turn)]),
            turn_complete=True)
        rounds = 0
        answered = False
        while time.monotonic() < deadline and not answered:
            turn_iterator = session.receive()
            async for response in turn_iterator:
                if time.monotonic() >= deadline:
                    answered = True
                    break
                if response.tool_call:
                    rounds += 1
                    function_responses = []
                    for fc in response.tool_call.function_calls or []:
                        answer = await loop.answer_mcp_tool(
                            fc.name, dict(fc.args or {}))
                        evidence["dispatched"].append({
                            "tool": fc.name,
                            "args_preview": {key: str(value)[:60]
                                             for key, value in (fc.args or {}).items()},
                            "result_head": str(answer)[:140],
                        })
                        function_responses.append(types.FunctionResponse(
                            id=fc.id, name=fc.name, response={"result": answer}))
                    await session.send_tool_response(
                        function_responses=function_responses)
                    evidence["rounds"] = rounds
                    if rounds >= 2:
                        answered = True
                        break
                content = response.server_content
                if content is None:
                    continue
                parts = (content.modelTurn and content.modelTurn.parts) or []
                for part in parts:
                    if getattr(part, "text", None):
                        evidence["turn_audio_parts"] += 1
                if getattr(content, "turnComplete", False):
                    evidence["turns_completed"] += 1
                    answered = True
                    break
                if response.go_away is not None:
                    answered = True
                    break
    return evidence


def main():
    parser = argparse.ArgumentParser(
        description="One isolated live Gemini tool-invocation demonstration.")
    parser.add_argument("--attempt-once", action="store_true",
                        help="Authorize exactly one live network attempt.")
    args = parser.parse_args()
    if not args.attempt_once:
        print(json.dumps({"state": "no_connection_attempted",
                          "reason": "Use --attempt-once to authorize one live call."}))
        return 2
    from spark_live_config import live_model
    from spark_live_profile import live_profile, select_live_config
    from spark_gemini_preflight import read_key
    key, source = read_key(ROOT, allow_arkus=False)
    if not key:
        print(json.dumps({"state": "setup_required", "key_source": source}))
        return 2
    config = select_live_config(live_profile(), {"response_modalities": ["AUDIO"]})
    model = live_model()
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key,
                              http_options=types.HttpOptions(api_version="v1beta"))
        try:
            evidence = asyncio.run(asyncio.wait_for(
                demo_session(client, model, config), timeout=150))
        finally:
            client.close()
        evidence["state"] = "completed"
    except Exception as exc:
        import traceback
        print("[demo] provider error, single attempt respected: "
              + type(exc).__name__, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        evidence = classify_error(exc)
        evidence["model"] = model
    evidence["key_source"] = source
    evidence["attempt_policy"] = "one_connection_total_no_retry"
    print(json.dumps(evidence, indent=1))
    return 0 if evidence.get("state") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
