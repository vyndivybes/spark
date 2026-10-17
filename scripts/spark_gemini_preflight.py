"""Stage 1: safe local Gemini readiness check for SPARK.

Only contacts Google's official models endpoint; does not open a billable
generation or Live session. Never prints or stores the API key.
"""
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
import urllib.parse

MODEL = "gemini-3.8-live"
API = "https://generativelanguage.googleapis.com/v1beta/models"


def read_key(project_root, allow_arkus=False):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key, "environment"
    env_file = Path(project_root) / "backend" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip(chr(34)).strip(chr(39))
                if key:
                    return key, "backend/.env"
    if allow_arkus:
        appdata = os.environ.get("APPDATA", "")
        cfg = Path(appdata) / "arkus" / "config.json" if appdata else None
        if cfg and cfg.is_file():
            try:
                key = str(json.loads(cfg.read_text(encoding="utf-8")).get("api_key") or "").strip()
                if key:
                    return key, "ARKUS opt-in"
            except (ValueError, OSError):
                pass
    return None, "missing"


def classify_http(code):
    return {
        400: "Invalid API request. Confirm API project and endpoint.",
        401: "Authentication failed: check API key.",
        403: "Access denied: check Gemini API permissions/project restrictions.",
        404: "Models endpoint unavailable.",
        429: "Rate limit/quota hit. Do not retry repeatedly.",
    }.get(code, "Google models API returned an HTTP error.")


def probe(key, timeout=12, max_pages=10):
    # The Google Models endpoint returns only 50 records by default. Query up
    # to 1000 per page, and follow nextPageToken before concluding that a
    # particular model is absent from this project's visible model catalog.
    # API key stays exclusively in a header: never URL, log or JSON response.
    names = set()
    seen_tokens = set()
    token = None
    pages_checked = 0
    exhausted = False
    for _ in range(max_pages):
        params = {"pageSize": 1000}
        if token:
            params["pageToken"] = token
        url = API + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url, headers={"x-goog-api-key": key, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            return {
                "state": "error", "http_status": exc.code,
                "pages_checked": pages_checked, "reason": classify_http(exc.code)
            }
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return {
                "state": "error", "pages_checked": pages_checked,
                "reason": "Network/TLS/API response failure; check connectivity and system time."
            }
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            return {"state": "error", "pages_checked": pages_checked,
                    "reason": "Unexpected Models API response."}
        pages_checked += 1
        for item in payload["models"]:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.add(item["name"].rsplit("/", 1)[-1])
        if MODEL in names:
            exhausted = True
            break
        token = payload.get("nextPageToken")
        if not token:
            exhausted = True
            break
        if not isinstance(token, str) or token in seen_tokens:
            break
        seen_tokens.add(token)

    # Keep the response manageable while including specific Live alternatives.
    live_models = sorted(n for n in names if "live" in n.lower())
    visible_models = sorted(names)[:50]
    found = MODEL in names
    state = "model_visible" if found else (
        "model_not_listed" if exhausted else "pagination_incomplete"
    )
    if found:
        reason = "Target model is visible through this project's Models API."
    elif exhausted:
        reason = "Target model is absent from every returned page for this project."
    else:
        reason = "Model listing was incomplete; cannot determine target model availability."
    return {
        "state": state, "model": MODEL,
        "listed_models": len(names), "pages_checked": pages_checked,
        "available_models": visible_models,
        "available_live_models": live_models,
        "reason": reason,
    }


def main():
    parser = argparse.ArgumentParser(description="Check SPARK Gemini connectivity without generating tokens.")
    parser.add_argument("--use-arkus-key", action="store_true", help="Opt in to reading local ARKUS credential, without copying it.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    key, source = read_key(root, allow_arkus=args.use_arkus_key)
    if not key:
        print(json.dumps({"state": "setup_required", "key_source": source, "next_step": "Set GEMINI_API_KEY privately or pass --use-arkus-key."}))
        return 2
    result = probe(key)
    result["key_source"] = source
    result["note"] = "This is API model visibility only, not a successful WebSocket, microphone, speaker or paid-tier authorization test."
    print(json.dumps(result))
    return 0 if result["state"] == "model_visible" else 1


if __name__ == "__main__":
    raise SystemExit(main())
