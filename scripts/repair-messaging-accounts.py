"""Local hidden-input enrollment; verifies identities without sending messages."""
import getpass
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from spark_credential_store import CredentialStore
from spark_messaging_hub import MessagingHub


def setup_telegram(store, workspace):
    print("\nTelegram: obtain the current API token for @vayusparkbot from BotFather.")
    token = getpass.getpass("Telegram bot token (hidden; Enter skips): ").strip()
    if not token:
        print("Telegram skipped; existing credential unchanged.")
        return
    spec = importlib.util.spec_from_file_location("telegram_enrollment", ROOT / "scripts/configure-telegram.py")
    enrollment = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(enrollment)
    info = enrollment._validate_token(token)
    store.save_telegram_token(token)
    path = workspace / "telegram/config.json"
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    config.setdefault("allowed_chat_id", "6463473290")
    config["bot_username"] = info["username"]
    config.setdefault("model", "gemini-3.5-flash")
    config.setdefault("transcribe_model", "gemini-3.5-transcribe")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print("Telegram identity verified; token stored using Windows DPAPI.")


def setup_discord(store, workspace):
    print("\nDiscord: paste an incoming webhook URL for the intended channel.")
    print("This enables approval-based outbound messages, not inbound Discord chat.")
    webhook = getpass.getpass("Discord webhook URL (hidden; Enter skips): ").strip()
    if not webhook:
        print("Discord skipped; existing configuration unchanged.")
        return
    parts = urlsplit(webhook)
    if (parts.scheme != "https" or parts.netloc != "discord.com" or parts.query or parts.fragment
            or not re.fullmatch(r"/api/(?:v\d+/)?webhooks/\d+/[A-Za-z0-9_.-]+", parts.path)):
        raise ValueError("Use a direct https://discord.com/api/webhooks/... URL.")
    import httpx
    try:
        response = httpx.get(webhook, timeout=20, follow_redirects=False, trust_env=False)
        if response.status_code != 200:
            raise ValueError("Discord webhook verification returned HTTP " + str(response.status_code) + ".")
        identity = response.json()
    except httpx.HTTPError:
        raise ValueError("Discord could not be reached; no configuration saved.") from None
    except (TypeError, json.JSONDecodeError):
        raise ValueError("Discord returned an invalid webhook identity.") from None
    channel = identity.get("channel_id") if isinstance(identity, dict) else None
    if not isinstance(identity, dict) or identity.get("type") != 1 or not isinstance(channel, str) or not channel.isdigit():
        raise ValueError("This is not an incoming channel webhook.")
    print("Verified Discord channel ID:", channel)
    if input("Connect Spark to this channel? [y/N]: ").strip().lower() != "y":
        print("Discord unchanged.")
        return
    MessagingHub(workspace, secret_store=store).configure("discord", {
        "webhook_url": webhook, "allowed_channel_id": channel})
    print("Discord configured. Webhook protected using Windows DPAPI; no message sent.")


def main():
    if not sys.stdin.isatty():
        raise SystemExit("Run in an interactive local terminal so credentials stay hidden.")
    workspace = Path(os.environ.get("SPARK_WORKSPACE_DATA_ROOT") or
                     Path(os.environ["LOCALAPPDATA"]) / "SPARK/workspace")
    store = CredentialStore()
    print("SPARK messaging repair — credentials are hidden and remain on this PC.")
    for name, setup in (("Telegram", setup_telegram), ("Discord", setup_discord)):
        try:
            setup(store, workspace)
        except Exception as error:
            # Never print arbitrary HTTP exceptions: they can contain secret URLs.
            print(name + " setup failed: " + (str(error) if isinstance(error, ValueError)
                                               else type(error).__name__))
    print("\nSetup finished. Restart Spark to load any replaced Telegram credential.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nLocal setup cancelled.")
