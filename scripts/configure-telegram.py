#!/usr/bin/env python3
"""Securely enroll @vayusparkbot on this PC.

The bot token is stored with Windows DPAPI in the current user's context;
it is never written to the repository, never logged, and never persisted in
SPARK's messaging SQLite database. A non-secret configuration is written to
``%LOCALAPPDATA%\\SPARK\\workspace\\telegram\\config.json``.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from urllib import request as urlrequest


API_ROOT = "https://api.telegram.org"


def _workspace_root():
    override = os.environ.get("SPARK_WORKSPACE_DATA_ROOT")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".spark")
    return Path(base) / "SPARK" / "workspace"


def _validate_token(token):
    token = (token or "").strip()
    if not token or ":" not in token:
        raise ValueError("That does not look like a Telegram bot token (format like 123456:ABCDEF).")
    url = f"{API_ROOT}/bot{token}/getMe"
    req = urlrequest.Request(url, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except Exception as error:
        code = getattr(error, "code", None)
        if isinstance(code, int):
            raise RuntimeError(f"Telegram Bot API returned HTTP {code}.") from None
        raise RuntimeError(
            f"Could not reach the Telegram Bot API ({type(error).__name__}).") from None
    if not isinstance(payload, dict) or not payload.get("ok"):
        description = payload.get("description") if isinstance(payload, dict) else None
        raise RuntimeError("Telegram rejected this token" + (": " + str(description)[:160] if description else "."))
    result = payload.get("result") or {}
    username = result.get("username") or ""
    if username != "vayusparkbot":
        raise RuntimeError(f"This token belongs to @{username}, not @vayusparkbot. Enroll the correct bot.")
    chat_id = result.get("id")
    return {"username": username, "id": chat_id}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Report whether a token is enrolled without changing anything.")
    parser.add_argument("--remove", action="store_true",
                        help="Delete the DPAPI-protected Telegram token from this PC.")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    sys.path.insert(0, str(backend_dir))
    from spark_credential_store import CredentialError, CredentialStore

    store = CredentialStore()
    if args.check:
        try:
            token = store.load_telegram_token()
        except CredentialError as error:
            print(f"Credential store error: {error}")
            raise SystemExit(2)
        if not token:
            print("Telegram is not enrolled on this PC.")
            raise SystemExit(1)
        info = _validate_token(token)
        print(f"Enrolled: @{info['username']} (bot id {info['id']}); DPAPI token is readable for this user.")
        return
    if args.remove:
        removed = store.delete_telegram_token()
        config_path = _workspace_root() / "telegram" / "config.json"
        if config_path.is_file():
            config_path.unlink()
        print("Telegram token removed from this PC." if removed else "No Telegram token was enrolled.")
        return

    print("SPARK Telegram secure enrollment (owner-only)")
    print("Token will be protected with Windows DPAPI for this user and stored outside the repo.")
    print("Only @vayusparkbot is accepted; only chat 6463473290 can use SPARK over Telegram.")
    print()
    token = getpass.getpass("Paste the bot token (input hidden): ")
    info = _validate_token(token)
    print(f"Validated: @{info['username']} (bot id {info['id']})")
    path = store.save_telegram_token(token)
    print(f"Token stored in DPAPI credential store: {path}")

    root = _workspace_root()
    tg_dir = root / "telegram"
    tg_dir.mkdir(parents=True, exist_ok=True)
    config_path = tg_dir / "config.json"
    config = {
        "allowed_chat_id": "6463473290",
        "bot_username": "vayusparkbot",
        "model": "gemini-3.5-flash",
        "transcribe_model": "gemini-3.5-transcribe",
    }
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Non-secret config written: {config_path}")
    print()
    print("Enrollment complete. Start SPARK and it will begin long polling this bot.")
    print("From Telegram (chat 6463473290) send /start, /status or /digest.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
