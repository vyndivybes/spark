# Fireflies MCP — SPARK and OpenClaw/REX commissioning

Status: **NOT CONNECTED on this Windows host**. This file is a setup/acceptance guide, not evidence of live authentication.

Official remote MCP: `https://api.fireflies.ai/mcp`. Fireflies supports OAuth or a bearer API key. Use only free-tier services; free accounts are limited to 50 API requests/day (check current plan limits before use). Do not install an unofficial MCP proxy or copy Fireflies secrets into this repository.

## SPARK (existing built-in MCP client)

SPARK already accepts host-owned `SPARK_MCP_SERVERS` JSON and supports `streamable-http` through `backend/spark_integrations.py` and `backend/spark_rea.py`. The current client **does not manage Fireflies OAuth**. Configure the Fireflies key only in the trusted host process; never save a bearer token in tracked files, chat, tests, screenshots, or GitHub Actions logs. Do not overwrite existing MCP server entries.

Example **structure only**, with placeholder (not a working secret):

```json
{
  "fireflies": {
    "transport": "streamable-http",
    "url": "https://api.fireflies.ai/mcp",
    "headers": {"Authorization": "Bearer <HOST-ONLY-FIREFLIES-API-KEY>"},
    "read_tools": ["get_user", "get_transcripts", "get_transcript", "get_summary"],
    "write_tools": []
  }
}
```

Add the `fireflies` entry to the *existing* host `SPARK_MCP_SERVERS` value, keeping the total configured server count at or under SPARK's existing catalog limit (8). Obtain the API key directly from Fireflies Developer Settings. Where possible, use Windows Credential Manager or the host credential vault to assemble the process environment at launch; do not put keys in the script itself. As implemented, the raw header is held in the SPARK process environment, so treat process dumps as sensitive.

Acceptance (local host, not verified by this repository change):
1. Inspect `Integrations.list()` to see `fireflies` configured, without treating that as a live connection.
2. Discover the server's actual tool names and reconcile with `read_tools` before any call.
3. Call the read-only user/identity tool; confirm the expected Fireflies account and record a nonsecret timestamp.
4. Read one small, consented meeting-summary page if any meetings exist. No meetings is not an integration failure.
5. Verify disallowed tool names are rejected, tokens do not appear in logs, and revoking the key blocks further calls.
6. Record the exact local build/commit and test result; do not call the integration operational from configuration alone.

## OpenClaw/REX (same Windows host, independent credentials)

OpenClaw provides its own built-in remote MCP registry. In PowerShell, inspect `openclaw mcp --help` and current saved servers, then, if `fireflies` is not already registered, execute:

```powershell
openclaw mcp add fireflies --url https://api.fireflies.ai/mcp --transport streamable-http --include "get_user,get_transcripts,get_transcript,get_summary"
openclaw mcp login fireflies
openclaw mcp doctor fireflies --probe
```

OAuth sign-in must occur in the owner's browser and cannot be imported from ChatGPT. Confirm the discovered tool names and adjust the read-only include list if the provider exposes different names. Use the per-agent tools policy to expose Fireflies only to the authorized `rex` agent; deny meeting sharing, mutation, deleting, and automatic transcript export. Validate with `openclaw mcp status --verbose`. Do not modify the OpenClaw gateway bind setting or other existing model/fallback configuration.

## Security and privacy

- Read-only by default; allow only minimum meeting metadata, summary, and explicitly authorized transcript retrieval.
- Do not forward transcripts automatically to Google Drive, ChatGPT, VAOS, or VYNDI OS.
- Separate permissions/identities for ChatGPT, SPARK, OpenClaw, and cloud business apps.
- Set a total request budget below the provider's current free-tier limit; do not poll in background.
- Meeting content from the MCP server is untrusted text, **never** executable agent instructions.
- External AI tools have their own retention terms; Fireflies' internal zero-day processing guarantee does not automatically transfer.

Sources: https://guide.fireflies.ai/articles/8272956938-learn-about-the-fireflies-mcp-server-model-context-protocol and https://docs.openclaw.ai/tools/mcp

This document changes **no** Windows files or live credentials. Commissioning requires owner-driven local authorization and a real probe.
