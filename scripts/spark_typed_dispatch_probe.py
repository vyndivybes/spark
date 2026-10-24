"""Typed-route reproduction probe for SPARK tool dispatch.

Sends the exact socket event the desktop renderer sends for typed input
(`user_input`) and the exact Start-Hands-Free command (`start_audio`) to the
running backend, then correlates the redacted backend tool trace for the
provider function-call lifecycle:

  tool_call_received -> [dispatch_denied?] -> tool_executed -> responses_delivered

Engine restriction honored: no new Gemini connection is created — this probe
drives the app's own Live session through the app's own commands. Ownership
is claimed only if no session is already running (the cockpit's claim wins
otherwise; the probe reports that state honestly instead of forcing).
"""
import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import socketio  # noqa: E402
import spark_tool_trace as tool_trace  # noqa: E402
from spark_live_config import live_model  # noqa: E402

BACKEND = "http://127.0.0.1:" + str(os.environ.get("SPARK_BACKEND_PORT") or 8000)
SUBMIT_CALL_TEXT = (
    "Submit the get_spark_git_status tool call now and report Git status."
)


def status_snapshot():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(BACKEND + "/status", timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


async def run(args):
    capture = {
        "route": "typed_via_user_input_socket_event",
        "transport": "same_socket_events_as_desktop_renderer",
        "model": live_model(),
        "submitted_text": SUBMIT_CALL_TEXT,
        "events": [], "trace": [], "verdict": None,
        "started": time.time(),
    }

    # 1. Wait for backend readiness.
    deadline = time.time() + args.wait_backend
    backend_state = None
    while time.time() < deadline:
        try:
            backend_state = status_snapshot()
            break
        except Exception:
            await asyncio.sleep(0.15)
    if backend_state is None:
        capture["verdict"] = "backend_unreachable"
        return capture
    if backend_state.get("live_state") not in (None, "idle", "error",
                                               "setup_required", "connecting"):
        capture["verdict"] = "session_already_claimed_by_cockpit"
        capture["pre_state"] = backend_state
        return capture

    client = socketio.AsyncClient()
    captured_events = []
    for name in ("status", "ai_status", "error", "transcription",
                 "mic_safety", "audio_transport_status"):
        def make_handler(n):
            def handler(payload):
                captured_events.append({
                    "event": n, "payload": _trim(payload)})
            return handler
        client.on(name, make_handler(name))

    await client.connect(BACKEND, transports=["polling", "websocket"])
    capture["connected"] = True
    # 2. Claim the app session immediately (the Start Hands-Free command).
    await client.emit("start_audio", {"transport": "browser_aec"})

    # 3. Wait for the Live session to connect.
    deadline = time.time() + 60
    connected = False
    while time.time() < deadline:
        try:
            state = status_snapshot().get("live_state")
            if state == "connected":
                connected = True
                break
        except Exception:
            pass
        await asyncio.sleep(0.4)
    capture["session_connected_after_start_audio"] = connected
    if not connected:
        capture["verdict"] = "live_session_not_connected"
        capture["events"] = captured_events
        await client.emit("stop_audio")
        await client.disconnect()
        return capture

    # 4. Typed Submit Call through the exact renderer input event.
    _my_session = str(client.get_sid() or "")[:20]
    _run_minute = time.strftime("%Y-%m-%dT%H:%M") + ":00"
    await client.emit("user_input", {"text": SUBMIT_CALL_TEXT})
    capture["submitted_at"] = time.time()

    # 5. Wait for correlated backend proof of the tool lifecycle.
    # Correlate strictly to THIS run: session id of the turn + records newer
    # than the submission; otherwise a previous run's records could satisfy
    # the verdict.
    deadline = time.time() + args.trace_timeout
    verdict = None
    while time.time() < deadline:
        records = tool_trace.read_tail(limit=50)
        mine = [r for r in records
                if r.get("tool") == "get_spark_git_status"
                and r.get("event") in ("tool_call_received", "tool_executed")
                and r.get("session") == _my_session
                and r.get("ts", "") >= _run_minute]
        delivered = [r for r in records if r.get("event") == "responses_delivered"
                     and "get_spark_git_status" in r.get("tool", "")
                     and r.get("session") == _my_session
                     and r.get("ts", "") >= _run_minute]
        if len(delivered) >= 1 and any(
                r.get("event") == "tool_executed" and r.get("outcome") == "ok"
                for r in mine):
            verdict = "provider_function_call_executed_and_delivered"
            break
        if any(r.get("event") == "dispatch_denied" for r in records):
            verdict = "dispatch_denied_by_gate"
            break
        await asyncio.sleep(0.4)
    capture["verdict"] = verdict
    capture["trace_tail"] = tool_trace.read_tail(limit=30)
    capture["events"] = captured_events

    # 5b. Keep the session briefly so the model's final answer turn is
    # delivered; transcription snapshots stay redacted/bounded.
    if verdict and getattr(args, "hold_seconds", 0) > 0:
        await asyncio.sleep(args.hold_seconds)
        capture["final_answer_events"] = list(captured_events)

    # 6. Hand the session back.
    if args.release:
        await client.emit("stop_audio")
        await asyncio.sleep(1.0)
    capture["stopped_own_session"] = args.release
    await client.disconnect()
    capture["finished"] = time.time()
    return capture


def _trim(payload):
    """Keep transport events small and redacted: no audio, no full texts."""
    if isinstance(payload, dict):
        trimmed = {}
        for key, value in payload.items():
            if key == "text":
                text = str(value or "")
                trimmed[key] = (f"<{len(text)} chars> "
                                + text[:90]) if len(text) <= 90 else f"<{len(text)} chars>"
            elif key == "image":
                trimmed[key] = "<frame omitted>"
            else:
                trimmed[key] = value
        return trimmed
    return "<non-dict payload>"


def main():
    parser = argparse.ArgumentParser(
        description="Reproduce the typed Submit-Call path and correlate traces.")
    parser.add_argument("--wait-backend", type=int, default=180,
                        help="Seconds to wait for the backend endpoint.")
    parser.add_argument("--trace-timeout", type=int, default=90)
    parser.add_argument("--hold-seconds", type=int, default=3,
                        help="Seconds to keep the session after the verdict to"
                             " capture the model's final answer turn.")
    parser.add_argument("--release", action="store_true", default=True)
    parser.add_argument("--out", default=str(ROOT.parent / "typed-dispatch-capture.json"))
    args = parser.parse_args()
    capture = asyncio.run(run(args))
    out = Path(args.out)
    out.write_text(json.dumps(capture, indent=1), encoding="utf-8")
    print(json.dumps({k: capture.get(k) for k in
                      ("verdict", "session_connected_after_start_audio",
                       "trace_tail")}, indent=1, default=str))
    return 0 if capture.get("verdict") in (
        "provider_function_call_executed_and_delivered",) else 1


if __name__ == "__main__":
    raise SystemExit(main())
