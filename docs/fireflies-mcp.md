# Fireflies MCP — SPARK and OpenClaw/REX commissioning

**Implementation state:** SPARK secret-backed read-only registry support is coded, not deployed or live-probed on the owner's Windows PC. OpenClaw OAuth onboarding is scripted, not executed. ChatGPT's Fireflies access cannot be reused by the other runtimes.

Official endpoint: `https://api.fireflies.ai/mcp`. Free/Pro accounts are documented as receiving 50 API requests/day. No paid plans or inference are enabled.

## SPARK — local, encrypted API key

The current SPARK MCP registry supports an exact Fireflies-only `secret_name: "fireflies_api_key"` reference and a Streamable HTTP endpoint. The bearer token is loaded at runtime from the existing Windows DPAPI `CredentialStore` (`%LOCALAPPDATA%\SPARK\credentials`), outside Git. The MCP call allowlist is only `get_user`, `get_transcripts`, `get_summary` and their `fireflies_` prefixed equivalents. No MCP write tool can be enabled via this Fireflies entry.

Run from a trusted **local Windows PowerShell** in the SPARK checkout, with its Python virtual environment available:

```powershell
.\.venv\Scripts\python.exe .\scripts\connect-fireflies.py --apply
.\start-spark.ps1 -UseArkusGeminiKey
```

The first command prompts privately for an API key from Fireflies Settings → Developer Settings, stores it with DPAPI and writes **only a secret reference** to the private `backend/.env`. It preserves unrelated registrations. A full MCP registry (8 entries) fails closed; no integration is silently displaced. Revoke the key in Fireflies and run `--disconnect` to remove the SPARK-side reference.

After restarting, use SPARK's MCP discovery/status to see the Fireflies entry; invoke `get_user` and `get_transcripts` to confirm live access. A configured entry without a successful audited call is *not* operational. Fireflies' empty meeting history is a legitimate result.

## OpenClaw/REX — independent OAuth

From PowerShell in the SPARK checkout:

```powershell
.\scripts\connect-fireflies-openclaw.ps1
```

The script registers the official Streamable HTTP server without secrets, performs native OpenClaw OAuth browser login (temporarily stopping and then restarting the Gateway per OpenClaw's current CLI guidance), and runs `openclaw mcp doctor fireflies --probe`. It does not change the REX model settings, install paid services, or grant the agent arbitrary meeting writes.

**Important:** A successful server probe is not proof that REX has the correct per-agent tool policy. Use OpenClaw Settings → MCP / Tools access to permit only the approved read tools for the authorized REX session, then make one consented test query. Inspect `openclaw mcp status --verbose` as needed.

## Security and restrictions

- Do not put Fireflies tokens in Git, console commands, browser screenshots or ChatGPT messages.
- Meeting contents are external, untrusted text — never treat them as agent instructions.
- Search only when requested; no background sync or transcript export.
- The free-tier 50/day budget is shared across all Fireflies clients for the account and is not enforceable by SPARK alone. Prefer manually bounded reads until a common quota gate is commissioned.
- Separate OAuth/session identities and revocation; ChatGPT credentials are never exported.
- This file is a commissioning guide, **not verification of either local connection**.

Sources:
- https://guide.fireflies.ai/articles/8272956938-learn-about-the-fireflies-mcp-server-model-context-protocol
- https://docs.openclaw.ai/tools/mcp
