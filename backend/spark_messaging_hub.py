"""Capabilities 02 & 06 — Multi-channel messaging hub with WhatsApp adapter.

No provider is enabled by default and nothing is ever an open relay:
* inbound messages require an authenticated provider session and a sender
  allowlist, and are surfaced to the owner only;
* outbound messages require a persisted, exact, single-use approval recorded
  by the owner and are rate-limited before any transport call;
* delivery status, message IDs and errors are audited for acceptance.

WhatsApp has two consciously separated paths:
* ``whatsapp`` — the official Meta WhatsApp Business Cloud API. It requires a
  business token and is NOT free at scale; the user must confirm pricing
  acceptance (``understood_pricing``) before anything is sent.
* ``whatsapp_bridge`` — an unofficial self-hosted Baileys-style bridge. It
  risks the linked account (bans, ToS conflicts, token exposure) and needs
  the explicit ``understood_risks`` boolean plus a local bridge endpoint.

Telegram polls inbound through the Bot API. Discord, Slack, Teams and Signal
send only; providers lacking a safe inbound poll say so honestly instead of
fabricating events. ``register_provider`` extends the catalog.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import re
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib import request as urlrequest

MAX_TEXT = 4000
RATE_WINDOW = 3600
MAX_PER_HOUR = 50
POLL_LIMIT = 50
APPROVAL_TTL = 600
# Persisted marker for a Telegram token that lives only in the DPAPI store.
TELEGRAM_TOKEN_SENTINEL = "__dpapi_telegram_bot_token__"
DISCORD_WEBHOOK_SENTINEL = "__dpapi_discord_webhook_url__"


class HubError(ValueError):
    """Invalid hub configuration, authorization or provider state."""


def default_transport(method, url, *, headers=None, body=None, timeout=15):
    """The real HTTP transport (stdlib only); tests inject a fake."""
    data = None if body is None else body.encode("utf-8")
    request = urlrequest.Request(url, method=method, data=data)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        response = urlrequest.urlopen(request, timeout=timeout)
    except HTTPError as error:
        # HTTP failures still carry provider responses (auth, conflicts,
        # retry_after). Let each adapter classify them; connection failures
        # continue to propagate without exposing credential-bearing URLs.
        response = error
    with response:
        return response.status, response.read(200_000).decode("utf-8", "replace")


def _store_config(config):
    """Sanitize persisted provider configuration; secrets stay local."""
    if not isinstance(config, dict):
        raise HubError("Provider configuration must be a mapping.")
    clean = {}
    for key, value in config.items():
        if not isinstance(key, str) or len(key) > 40 or not re.fullmatch(r"[a-z0-9_]+", key):
            raise HubError("Unsupported configuration key.")
        if isinstance(value, str):
            if len(value) > 4096:
                raise HubError("Configuration value too long.")
            clean[key] = value.strip()
        elif isinstance(value, bool):
            clean[key] = value
        else:
            raise HubError("Configuration value must be a string or a boolean.")
    return clean


class Provider:
    """Base adapter. Subclasses implement send and optionally receive."""

    name = None
    inbound_polling = False

    def __init__(self, hub=None):
        self.hub = hub

    def _require(self, config, *keys):
        missing = [key for key in keys if not config.get(key)]
        if missing:
            raise HubError("Missing provider configuration: " + ", ".join(missing))

    def send(self, config, recipient, text):
        raise NotImplementedError

    def receive(self, config):
        raise NotImplementedError


class TelegramProvider(Provider):
    name = "telegram"
    inbound_polling = True

    def send(self, config, recipient, text):
        self._require(config, "bot_token", "allowed_chat_id")
        allowed = str(config["allowed_chat_id"]).split(",")
        if str(recipient) not in allowed:
            raise HubError("Recipient is not on the channel allowlist.")
        try:
            status, body = default_transport(
                "POST", f"https://api.telegram.org/bot{config['bot_token']}/sendMessage",
                headers={"Content-Type": "application/json"},
                body=json.dumps({"chat_id": recipient, "text": text[:MAX_TEXT]}))
        except (OSError, TimeoutError) as error:
            # urllib errors can contain the request URL, which includes the
            # bot token. Never persist or surface that detail.
            raise HubError("Telegram transport failed (" + type(error).__name__ + ").") from None
        payload = json.loads(body)
        if status != 200 or not payload.get("ok"):
            raise HubError("Telegram rejected the message: " + str(payload)[:200])
        return {"message_id": str(payload.get("result", {}).get("message_id", "")),
                "recipient": str(recipient), "channel": self.name, "state": "sent"}

    def receive(self, config):
        self._require(config, "bot_token", "allowed_chat_id")
        allowed = {str(chat) for chat in str(config["allowed_chat_id"]).split(",")}
        try:
            status, body = default_transport(
                "POST", f"https://api.telegram.org/bot{config['bot_token']}/getUpdates",
                headers={"Content-Type": "application/json"},
                body=json.dumps({"limit": POLL_LIMIT, "timeout": 5,
                                 "allowed_updates": ["message"]}),
                timeout=30)
        except (OSError, TimeoutError) as error:
            raise HubError("Telegram inbound transport failed ("
                           + type(error).__name__ + ").") from None
        payload = json.loads(body)
        if status != 200 or not payload.get("ok"):
            raise HubError("Telegram inbound failed: " + str(payload)[:200])
        events = []
        for update in payload.get("result", []):
            message = update.get("message") or {}
            chat = str((message.get("chat") or {}).get("id", ""))
            if chat not in allowed:
                events.append({"external": True, "sender": chat,
                               "provider_message_id": str(update.get("update_id", "")),
                               "state": "rejected_not_allowed"})
                continue
            events.append({"external": False, "sender": chat,
                           "provider_message_id": str(update.get("update_id", "")),
                           "text": str(message.get("text", ""))[:MAX_TEXT],
                           "state": "received"})
        return events


class WhatsAppCloudProvider(Provider):
    """Official Meta Cloud API. Not zero-cost; requires the user's own token."""

    name = "whatsapp"
    inbound_polling = False

    def send(self, config, recipient, text):
        self._require(config, "access_token", "phone_number_id", "allowed_recipient")
        if config.get("understood_pricing") is not True:
            raise HubError("Confirm WhatsApp Cloud API pricing acceptance first; "
                           "business messaging is not free at scale.")
        if str(recipient) != str(config["allowed_recipient"]):
            raise HubError("Recipient is not on the verified allowlist.")
        status, body = default_transport(
            "POST", f"https://graph.facebook.com/v21.0/{config['phone_number_id']}/messages",
            headers={"Authorization": f"Bearer {config['access_token']}",
                     "Content-Type": "application/json"},
            body=json.dumps({"messaging_product": "whatsapp", "to": str(recipient),
                             "type": "text", "text": {"body": text[:MAX_TEXT]}}))
        payload = json.loads(body)
        if status < 200 or status >= 300:
            error = (payload.get("error") or {}).get("message", "")
            state = (f"auth_failure({status})" if status in (401, 403)
                     else f"provider_error({status})")
            raise HubError(f"WhatsApp cloud send failed: {state} {error}"[:200])
        message_id = str(((payload.get("messages") or [{}])[0]).get("id", ""))
        return {"message_id": message_id, "recipient": str(recipient),
                "channel": "whatsapp", "state": "sent", "transport": "cloud_api"}

    def receive(self, config):
        raise HubError("WhatsApp Cloud inbound requires the owner's own webhook "
                       "endpoint; SPARK polls nothing without explicit configuration.")


class WhatsAppBridgeProvider(Provider):
    """Unofficial bridge. High security/account risk; strict opt-in only."""

    name = "whatsapp_bridge"
    inbound_polling = False

    def send(self, config, recipient, text):
        self._require(config, "bridge_url", "allowed_recipient")
        if config.get("understood_risks") is not True:
            raise HubError("The unofficial WhatsApp bridge requires an explicit "
                           "informed opt-in for account and security risks.")
        if str(recipient) != str(config["allowed_recipient"]):
            raise HubError("Recipient is not on the bridge allowlist.")
        status, body = default_transport(
            "POST", str(config["bridge_url"]).rstrip("/") + "/send/text",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"chatId": str(recipient), "text": text[:MAX_TEXT]}))
        if status < 200 or status >= 300:
            raise HubError(f"WhatsApp bridge failed with HTTP {status}.")
        return {"message_id": body[:200], "recipient": str(recipient),
                "channel": "whatsapp", "state": "sent", "transport": "bridge"}

    def receive(self, config):
        raise HubError("Bridge inbound is intentionally not implemented; "
                       "an unofficial bridge risks the linked account.")


class SlackProvider(Provider):
    name = "slack"
    inbound_polling = False

    def send(self, config, recipient, text):
        self._require(config, "bot_token", "allowed_channel")
        if str(recipient) != str(config["allowed_channel"]):
            raise HubError("Channel is not on the Slack allowlist.")
        status, body = default_transport(
            "POST", "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {config['bot_token']}",
                     "Content-Type": "application/json"},
            body=json.dumps({"channel": str(recipient), "text": text[:MAX_TEXT]}))
        payload = json.loads(body)
        if not payload.get("ok"):
            raise HubError("Slack rejected the message: " + str(payload)[:200])
        return {"message_id": str(payload.get("ts", "")), "recipient": str(recipient),
                "channel": "slack", "state": "sent"}


class DiscordProvider(Provider):
    name = "discord"
    inbound_polling = False

    def send(self, config, recipient, text):
        self._require(config, "webhook_url", "allowed_channel_id")
        if str(recipient) != str(config["allowed_channel_id"]):
            raise HubError("Channel is not on the Discord allowlist.")
        status, _ = default_transport(
            "POST", str(config["webhook_url"]), headers={"Content-Type": "application/json"},
            body=json.dumps({"content": text[:MAX_TEXT]}))
        if status < 200 or status >= 300:
            raise HubError(f"Discord webhook failed with HTTP {status}.")
        return {"message_id": "", "recipient": str(recipient),
                "channel": "discord", "state": "sent"}


class TeamsProvider(Provider):
    name = "teams"
    inbound_polling = False

    def send(self, config, recipient, text):
        self._require(config, "webhook_url", "allowed_channel_name")
        if str(recipient) != str(config["allowed_channel_name"]):
            raise HubError("Channel is not on the Teams allowlist.")
        status, _ = default_transport(
            "POST", str(config["webhook_url"]), headers={"Content-Type": "application/json"},
            body=json.dumps({"text": text[:MAX_TEXT]}))
        if status < 200 or status >= 300:
            raise HubError(f"Teams webhook failed with HTTP {status}.")
        return {"message_id": "", "recipient": str(recipient),
                "channel": "teams", "state": "sent"}


class SignalProvider(Provider):
    """Local signal-cli JSON-RPC only; no third-party cloud service."""

    name = "signal"
    inbound_polling = True

    def send(self, config, recipient, text):
        self._require(config, "rpc_url", "account", "allowed_recipient")
        if str(recipient) != str(config["allowed_recipient"]):
            raise HubError("Number is not on the Signal allowlist.")
        status, _ = default_transport(
            "POST", str(config["rpc_url"]), headers={"Content-Type": "application/json"},
            body=json.dumps({"jsonrpc": "2.0", "id": "spark", "method": "send",
                             "params": {"account": config["account"],
                                        "recipient": [str(recipient)],
                                        "message": text[:MAX_TEXT]}}))
        if status < 200 or status >= 300:
            raise HubError(f"signal-cli RPC failed with HTTP {status}.")
        # Delivery receipts require signal-cli's own history; honesty first.
        return {"message_id": "", "recipient": str(recipient),
                "channel": "signal", "state": "sent", "delivery_receipt": "not_available"}


PROVIDERS = {
    "telegram": TelegramProvider,
    "whatsapp": WhatsAppCloudProvider,
    "whatsapp_bridge": WhatsAppBridgeProvider,
    "slack": SlackProvider,
    "discord": DiscordProvider,
    "teams": TeamsProvider,
    "signal": SignalProvider,
}


def register_provider(name, provider_class):
    """Extension point for additional adapters; names are validated."""
    if not re.fullmatch(r"[a-z0-9_]{2,30}", name):
        raise HubError("Provider name must be a short lowercase token.")
    if not issubclass(provider_class, Provider):
        raise HubError("Providers must subclass the Provider interface.")
    PROVIDERS[name] = provider_class


class MessagingHub:
    """Persisted, consenting, allow-listed messaging hub."""

    def __init__(self, root, *, clock=time.time, secret_store=None):
        self.root = Path(root) / "messaging-hub"
        self.clock = clock
        # When supplied, Telegram's bot token is written only through the
        # user-scoped DPAPI store; SQLite keeps a non-secret marker instead.
        self.secret_store = secret_store
        if self.root.is_symlink():
            raise HubError("Linked messaging storage is prohibited.")

    # -- storage ---------------------------------------------------------
    @contextlib.contextmanager
    def _db(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "messages.sqlite3"
        if path.is_symlink():
            raise HubError("Linked messaging storage is prohibited.")
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS messages("
                           "id TEXT PRIMARY KEY,direction TEXT,channel TEXT,"
                           "message_id TEXT,sender TEXT,recipient TEXT,text TEXT,"
                           "state TEXT,error REAL,created REAL,external INTEGER)")
                db.execute("CREATE TABLE IF NOT EXISTS approvals("
                           "id TEXT PRIMARY KEY,channel TEXT,recipient TEXT,"
                           "text TEXT,expires INTEGER,used INTEGER DEFAULT 0)")
                db.execute("CREATE TABLE IF NOT EXISTS provider_config("
                           "channel TEXT PRIMARY KEY,config TEXT NOT NULL,updated REAL)")
                db.execute("CREATE TABLE IF NOT EXISTS activity("
                           "channel TEXT PRIMARY KEY,last_out REAL,last_in REAL,"
                           "last_fail REAL,failures INTEGER DEFAULT 0)")
            yield db
            db.commit()
        finally:
            db.close()

    # -- configuration ---------------------------------------------------
    def _protect_config(self, channel, config):
        """Keep Telegram outbound credentials in DPAPI, never in SQLite."""
        if channel == "discord" and self.secret_store is not None:
            webhook = config.get("webhook_url")
            if webhook == DISCORD_WEBHOOK_SENTINEL:
                return config
            if not isinstance(webhook, str) or not webhook.strip():
                raise HubError("A Discord webhook URL is required.")
            try:
                self.secret_store.save("discord_webhook_url", webhook.strip())
            except Exception:
                raise HubError("Discord webhook could not be protected.") from None
            return {**config, "webhook_url": DISCORD_WEBHOOK_SENTINEL}
        if channel != "telegram" or "bot_token" not in config:
            return config
        token = config.get("bot_token")
        if token == TELEGRAM_TOKEN_SENTINEL:
            return config
        if self.secret_store is None:
            # Backwards-compatible local hubs without a secret store keep the
            # pre-existing behaviour; the production workbench always injects
            # the DPAPI store, so the plaintext path is never used there.
            return config
        if not isinstance(token, str) or not token.strip():
            raise HubError("A Telegram bot token is required.")
        try:
            self.secret_store.save_telegram_token(token.strip())
        except Exception as error:
            raise HubError("Telegram credential could not be protected ("
                           + type(error).__name__ + ").") from None
        return {**config, "bot_token": TELEGRAM_TOKEN_SENTINEL}

    def _load_telegram_token(self):
        try:
            resolved = self.secret_store.load_telegram_token()
        except Exception as error:
            raise HubError("Telegram credential could not be read ("
                           + type(error).__name__ + ").") from None
        if not resolved:
            raise HubError("Telegram is not enrolled. Run the secure Telegram "
                           "configuration script on this PC first.")
        return resolved

    def _resolve_config(self, channel, config):
        """Resolve the DPAPI marker for a transport call, migrating legacy rows."""
        if channel == "discord" and config.get("webhook_url") == DISCORD_WEBHOOK_SENTINEL:
            try:
                webhook = self.secret_store.load("discord_webhook_url")
            except Exception:
                raise HubError("Discord webhook could not be read.") from None
            if not webhook:
                raise HubError("Discord webhook credential is missing. Run local setup again.")
            return {**config, "webhook_url": webhook}
        if channel != "telegram" or self.secret_store is None:
            return config
        token = config.get("bot_token")
        if token == TELEGRAM_TOKEN_SENTINEL:
            return {**config, "bot_token": self._load_telegram_token()}
        if isinstance(token, str) and token:
            # Scrub a plaintext token persisted by an older SPARK build.
            protected = self._protect_config(channel, config)
            if protected.get("bot_token") == TELEGRAM_TOKEN_SENTINEL:
                with self._db() as db:
                    db.execute("UPDATE provider_config SET config=? WHERE channel=?",
                               (json.dumps(protected), channel))
                return {**config, "bot_token": self._load_telegram_token()}
        return config

    def _scrub_legacy_secrets(self):
        """Move plaintext Telegram tokens left by older builds into DPAPI."""
        if self.secret_store is None:
            return
        try:
            with self._db() as db:
                rows = db.execute("SELECT channel,config FROM provider_config"
                                  ).fetchall()
                for row in rows:
                    try:
                        config = json.loads(row["config"])
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(config, dict):
                        continue
                    if config.get("__kind") != "telegram":
                        continue
                    token = config.get("bot_token")
                    if not isinstance(token, str) or not token.strip():
                        continue
                    if token == TELEGRAM_TOKEN_SENTINEL:
                        continue
                    try:
                        self.secret_store.save_telegram_token(token.strip())
                    except Exception:
                        # Keep the old row rather than lose the credential; a
                        # later status read retries the migration.
                        continue
                    protected = {**config, "bot_token": TELEGRAM_TOKEN_SENTINEL}
                    db.execute("UPDATE provider_config SET config=? WHERE channel=?",
                               (json.dumps(protected), row["channel"]))
        except (sqlite3.Error, OSError):
            # Status must stay readable even if the local audit store is
            # damaged; no credential is ever logged or returned.
            return

    def configure(self, channel, config):
        if not isinstance(channel, str) or channel not in PROVIDERS:
            raise HubError("Unknown messaging provider: " + str(channel))
        adapter = PROVIDERS[channel]
        config = _store_config(config)
        config = self._protect_config(channel, config)
        config["__kind"] = channel
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO provider_config VALUES(?,?,?)",
                       (channel, json.dumps(config), self.clock()))
        return {"channel": channel, "configured": True,
                "inbound_polling": PROVIDERS[channel].inbound_polling,
                "credential_store": ("dpapi" if (channel == "telegram"
                                     and config.get("bot_token") == TELEGRAM_TOKEN_SENTINEL)
                                     or (channel == "discord"
                                     and config.get("webhook_url") == DISCORD_WEBHOOK_SENTINEL)
                                     else "provider")}

    def disconnect(self, channel):
        if not isinstance(channel, str) or channel not in PROVIDERS:
            raise HubError("Unknown messaging provider: " + str(channel))
        with self._db() as db:
            db.execute("DELETE FROM provider_config WHERE channel=?", (channel,))
        return {"channel": channel, "configured": False,
                "revoked_at": self.clock(),
                "note": ("Locally stored credentials for this channel were "
                         "removed; revoke provider-side credentials separately.")}

    def _config(self, channel):
        if not isinstance(channel, str):
            raise HubError("Unknown messaging provider: " + str(channel))
        with self._db() as db:
            row = db.execute("SELECT config FROM provider_config WHERE channel=?",
                             (channel,)).fetchone()
        if not row:
            raise HubError("This channel is not configured. Enable it explicitly first.")
        config = json.loads(row["config"])
        if config.get("__kind") not in PROVIDERS:
            raise HubError("The configured provider type is not registered.")
        return self._resolve_config(channel, config)

    # -- approvals -------------------------------------------------------
    def approve_outbound(self, channel, recipient, text, *, ttl=APPROVAL_TTL):
        """Record the owner's explicit, exact, single-use outbound approval."""
        if not isinstance(channel, str) or channel not in PROVIDERS:
            raise HubError("Approve a message on a real channel.")
        if not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT:
            raise HubError("Message text must be 1-4000 characters.")
        if not isinstance(recipient, str) or not recipient:
            raise HubError("Approve a real recipient.")
        nonce = secrets.token_hex(6)
        approval_id = "apr-" + hashlib.sha256(
            f"{channel}|{recipient}|{text}|{self.clock()}|{nonce}".encode("utf-8")
        ).hexdigest()[:12]
        expires = int(self.clock()) + ttl
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO approvals VALUES(?,?,?,?,?,0)",
                       (approval_id, channel, recipient, text, expires))
        return {"approval_id": approval_id, "channel": channel,
                "recipient": recipient, "expires": expires}

    # -- outbound --------------------------------------------------------
    def send(self, channel, approval_id):
        """Send a previously approved, exact message; audit the result."""
        config = self._config(channel)
        adapter = PROVIDERS[config["__kind"]]
        with self._db() as db:
            row = db.execute("SELECT * FROM approvals WHERE id=? AND used=0",
                             (approval_id,)).fetchone()
            if not row:
                raise HubError("Approval not found, already used or revoked.")
            if row["expires"] < self.clock():
                raise HubError("The approval expired; request a new one.")
            if row["channel"] != channel:
                raise HubError("Approval does not belong to this channel.")
            db.execute("UPDATE approvals SET used=1 WHERE id=?", (approval_id,))
        self._rate_limit(channel)
        try:
            result = PROVIDERS[config["__kind"]](self).send(
                config, row["recipient"], row["text"])
        except HubError as error:
            self._note_activity(channel, "fail")
            self._audit("out", channel, "", "", row["recipient"], row["text"],
                        "failed", str(error)[:200])
            raise
        except (OSError, TimeoutError, json.JSONDecodeError, ValueError) as error:
            self._note_activity(channel, "fail")
            self._audit("out", channel, "", "", row["recipient"], row["text"],
                        "failed", str(error)[:200])
            raise HubError("Provider transport failed: " + str(error)[:150]) from None
        self._audit("out", channel, result.get("message_id", ""), "",
                    row["recipient"], row["text"], result.get("state", "sent"), None)
        self._note_activity(channel, "out")
        return {**result, "approval_id": approval_id}

    def _rate_limit(self, channel):
        with self._db() as db:
            sent = db.execute(
                "SELECT COUNT(*) c FROM messages WHERE channel=? AND direction='out' "
                "AND created>? AND state='sent'",
                (channel, self.clock() - RATE_WINDOW)).fetchone()["c"]
        if sent >= MAX_PER_HOUR:
            raise HubError("Channel rate limit reached (50/hour). Retry later.")

    # -- inbound ---------------------------------------------------------
    def receive(self, channel):
        config = self._config(channel)
        adapter = PROVIDERS[config["__kind"]]
        if not adapter.inbound_polling:
            raise HubError("This provider cannot poll inbound messages; inbound "
                           "requires its own authenticated webhook/feed.")
        fresh = []
        try:
            events = PROVIDERS[config["__kind"]](self).receive(config)
        except (OSError, TimeoutError, json.JSONDecodeError, HubError) as error:
            self._note_activity(channel, "fail")
            raise HubError("Inbound feed failed: " + str(error)[:150]) from None
        self._note_activity(channel, "success")
        with self._db() as db:
            for event in events:
                external = bool(event.get("external"))
                direction = "in-external" if external else "in"
                identity = self._identity(direction, channel,
                                          str(event.get("provider_message_id", "")),
                                          str(event.get("sender", "")), "",
                                          event.get("text"))
                exists = db.execute("SELECT 1 FROM messages WHERE id=?",
                                    (identity,)).fetchone()
                if exists:
                    continue  # Replay protection: one update is never doubled.
                state = "rejected_not_allowed" if external else "received"
                self._audit(direction, channel,
                            str(event.get("provider_message_id", "")),
                            str(event.get("sender", "")), "",
                            event.get("text"), state,
                            "Sender is not on the allowlist." if external else None)
                fresh.append({**event, "channel": channel})
        return {"channel": channel, "events": fresh, "state": "connected",
                "note": "Owner-visible only; no automatic forwarding or actions."}

    # -- audit and status ------------------------------------------------
    @staticmethod
    def _identity(direction, channel, message_id, sender, recipient, text):
        digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:10]
        return "|".join((channel, direction, str(message_id), str(sender),
                         str(recipient), digest))

    def _audit(self, direction, channel, message_id, sender, recipient, text,
               state, error):
        identity = self._identity(direction, channel, message_id, sender,
                                  recipient, text)
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (identity, direction, channel, message_id, sender, recipient,
                        text, state, error, self.clock(),
                        1 if direction == "in-external" else 0))

    def _note_activity(self, channel, kind):
        with self._db() as db:
            row = db.execute("SELECT last_out,last_in,last_fail,failures "
                             "FROM activity WHERE channel=?", (channel,)).fetchone()
            now = self.clock()
            last_out = row["last_out"] if row else None
            last_in = row["last_in"] if row else None
            last_fail = row["last_fail"] if row else None
            failures = int(row["failures"] or 0) if row else 0
            if kind == "out":
                last_out = now
            elif kind == "in":
                last_in = now
            elif kind == "fail":
                last_fail = now
                failures += 1
            db.execute("INSERT OR REPLACE INTO activity VALUES(?,?,?,?,?)",
                       (channel, last_out, last_in, last_fail, failures))

    def history(self, *, limit=50):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise HubError("Request between 1 and 200 audit entries.")
        with self._db() as db:
            rows = db.execute("SELECT direction,channel,message_id,sender,recipient,"
                              "text,state,error,created,external FROM messages "
                              "ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return {"messages": [dict(row) for row in rows], "count": len(rows),
                "note": "Envelope audit for delivery evidence, retained locally."}

    def status(self):
        self._scrub_legacy_secrets()
        with self._db() as db:
            configured = {row["channel"]: json.loads(row["config"]).get("__kind")
                          for row in db.execute(
                              "SELECT channel,config FROM provider_config")}
            activity = {row["channel"]: dict(row)
                        for row in db.execute("SELECT * FROM activity")}
        channels = {}
        for channel, kind in configured.items():
            adapter = PROVIDERS.get(kind or channel)
            counts = activity.get(channel) or {}
            last_out = counts.get("last_out")
            last_fail = counts.get("last_fail")
            if last_out is None and (counts.get("last_fail") is None):
                state = "configured, untested"
            else:
                state = "connected" if (last_out or 0) >= (last_fail or 0) else "failed"
            channels[channel] = {"state": state,
                                 "inbound_polling": bool(
                                     adapter.inbound_polling if adapter else False),
                                 "last_outbound": last_out,
                                 "last_inbound": counts.get("last_in"),
                                 "failures": int(counts.get("failures") or 0)}
        return {"schema": "spark.messaging_hub.v1", "channels": channels,
                "providers": sorted(PROVIDERS),
                "policy": ("allowlisted inbound; approved and rate-limited outbound; "
                           "no open relay; nothing enabled by default")}
