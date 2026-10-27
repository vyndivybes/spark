# Spark messaging connection repair

Use Spark's existing accounts. OpenClaw channel accounts are separate and were
not configured or given Spark's credentials.

## Local account setup

From the Spark folder, run:

```powershell
.\.venv\Scripts\python.exe scripts\repair-messaging-accounts.py
```

The interactive terminal hides both credential inputs. Enter the current
BotFather token for `@vayusparkbot`, then the incoming Discord webhook URL.
Press Enter at either secret prompt to leave that account unchanged. Telegram
identity is verified before replacing its credential. Discord's webhook
identity is checked with a GET request and the destination channel ID must be
confirmed locally. Both credentials use Windows DPAPI outside the repository;
Discord's messaging database stores a reference instead of the webhook secret.

Restart Spark after replacing the Telegram token. Its single polling worker
loads the protected token at startup. Do not run another consumer for that bot.

## Supported behavior and verification

- Telegram: owner-only private text/voice chat and existing Spark commands.
  `http://127.0.0.1:8000/status/telegram` reports whether long polling is running.
- WhatsApp: the previously linked Spark WhatsApp Web partition, with bounded
  read-only previews. `http://127.0.0.1:8000/status/whatsapp` checks that session.
  Automated sending remains unavailable on this linked-device adapter.
- Slack: the existing `vyndi` MCP account can verify identity and list public
  channels. Its existing read permissions do not establish chat-history or
  outbound-message access.
- Discord: the existing messaging-hub adapter supports outbound incoming
  webhooks with exact per-message approval. It has no inbound Discord listener.
  Successful webhook identity verification is not a delivery test.

Provider HTTP error responses now retain their status and body, allowing
Telegram to distinguish rejected credentials (401/403), a competing poller
(409), and retryable rate limits (429) from network failures. Secret-bearing
request URLs are not included in Telegram error messages.

No external acceptance messages are sent by local setup.
