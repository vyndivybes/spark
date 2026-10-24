# Sprk integration setup, 23 October 2026

The active desktop was launched from this checkout. Its loopback `/status`
confirmed Gemini and Groq credentials present, Graphify, Graphiti, Hermes and
Obsidian ready, and browser AEC selected. Runtime readiness does not prove every
provider action or device workflow.

## Configured and checked

- Eight host MCP registrations: Graphiti, Hermes, GitHub, Gmail, Google Drive,
  Google Calendar, Slack and Graphify. Actual MCP discovery confirmed every
  approved read tool exists. Google, GitHub and Slack account reads succeeded.
- Graphiti reported installed dependencies and configured credentials. Hermes
  reported available. These checks did not perform cloud graph extraction.
- The saved Google registrations now include daily briefing, Gmail search and
  Drive search. Account reconnection preserves those tools in future.
- All 13 integration snapshot entries were current after refresh, including
  four real Obsidian notes. Morning Digest completed with fresh Google sources.
  Google Tasks remains unconfigured.
- Workspace search and the Obsidian vault connector were configured and their
  local account validation passed.
- Ollama's installed `gemma3:1b` passed health and real generation. It returned
  exactly `42`, with 18 input and 4 output tokens reported by the engine.
  Generation requires a successful model probe in the same runtime session.
- Fourteen distinct capability status actions succeeded. These cover the
  status interfaces shared by the sixteen capability pages, with research
  checked separately. Research retrieved twelve documents in two bounded hops;
  its result remained explicitly unverified.

Sanitized evidence: `remaining-integrations-20261023.json` and
`remaining-capabilities-20261023.json`. Provider payloads, account identities and
credentials are excluded.

## Messaging accounts still required

All seven existing messaging adapters have entries in the private local file:

`C:\Users\ASUS\AppData\Local\SPARK\accounts\messaging.json`

| Adapter | Required account configuration |
| --- | --- |
| Telegram | Bot token and allowed chat ID |
| WhatsApp Cloud | Access token, phone number ID, allowed recipient, pricing acceptance |
| WhatsApp bridge | Running bridge URL, allowed recipient, risk acceptance |
| Slack | Allowed channel; importer can reuse the existing host Slack token |
| Discord | Webhook URL and allowed channel ID |
| Teams | Webhook URL and allowed channel name |
| Signal | Running signal-cli RPC URL, account and allowed recipient |

Fill the matching entry and set `enabled` to `true`. Keep credentials in this
local file. Apply with:

```powershell
.\.venv\Scripts\python.exe scripts/configure-integrations.py --apply
```

The importer preserves existing registrations and grants, skips incomplete
accounts, and sends no messages. Imported accounts remain configured but
untested until a separately approved real send succeeds. Existing WhatsApp Web
session diagnostics returned `unknown`, with sending disabled; this does not
prove the browser account is disconnected. The existing Slack read connection
is verified, but no destination was selected on the owner's behalf.

## Capability boundaries still open

| Capability | Remaining requirement |
| --- | --- |
| 01 Morning Digest | Digest verified; Google Tasks and scheduled notification acceptance remain open |
| 02 WhatsApp / 06 messaging | Credentials, explicit destinations and real delivery acceptance |
| 03 proactive agent / 11 monitors | Real proposal approval, delivery and restart workflow acceptance |
| 04 OpenCode | CLI installed; model-backed scoped session and patch acceptance unverified |
| 05 research | Local retrieval exercised; remote research sources are not attached |
| 07 learning / 12 adaptive routing | Real labeled outcomes and independent held-out benchmark |
| 08 specification search | Workbench still uses its fixture case set without an attached LLM planner; configuration alone cannot complete this |
| 09 skills | Real publisher bundle, provenance and explicit tool grants |
| 10 agent runtimes | Guarded adapters respond; model-backed end-to-end scenario remains unverified |
| 13 connectors | Local identities validated; cloud catalog lifecycle requires provider-specific adapters beyond MCP registrations |
| 14 evaluations | Real model candidate and labeled unseen dataset |
| 15 telemetry | Token evidence exists; streaming TTFT and hardware energy measurement remain open |
| 16 inference | Ollama generation verified; cloud task engines and optional inference engines remain unconfigured |

## Continuation results

- Fixed local telemetry capture. The action now recognizes local models,
  probes their current runtime health and records inference without cloud
  consent. Cloud calls still require explicit consent before any provider
  request. A real local capture recorded 6,761.6 ms end-to-end latency and four
  output tokens. TTFT and energy remain unmeasured.
- Ran the actual snapshot-freshness monitor. It completed with zero new events
  and saved its next checkpoint. No artificial notification was generated.
- Added an explicitly host-selected local evaluation runner through
  `SPARK_EVALUATION_MODEL=local-gemma`. It sends fixture inputs and a response
  contract to the local model. Expected answers and case identifiers stay in
  the evaluator. The candidate is `model-local-gemma` in Evaluations.
- The initial two-case memory evaluation failed JSON decoding. After accepting
  a complete JSON Markdown block and clarifying the response wrapper, the real
  model passed both cases. Both attempts remain recorded with distinct prompt
  fingerprints. This is a two-case fixture result, not a held-out production
  qualification. The report is exported under the local workspace's
  `evaluations/reports/` directory.
- Discovered the existing OpenCode configuration and its stopped local
  OmniRoute gateway. Started the installed gateway headlessly on loopback
  port 20128. After startup completed, authenticated model listing returned
  HTTP 200 and included the configured free model. A standalone OpenCode
  session returned `SPARK_READY` with exit code zero. Tools and inherited MCP
  services were disabled for that disposable acceptance session. No patch
  workflow has been accepted.
- Pinned the existing OpenCode free model in the local project configuration.
  Unrelated inherited MCP services are disabled for this project. The new
  `EnableOpenCodeGateway` local startup preference starts the existing gateway
  without opening a browser, reuses its verified listener and leaves foreign
  listeners alone. It does not install providers or change their credentials.
- A separate-process model-agent attempt was refused. Model-driven agent
  execution remains unaccepted; guarded runtime status and tests still pass.

These results supersede the earlier OpenCode model-session, evaluation-runner
and local-telemetry gaps. Messaging accounts, destinations, production
benchmarks, specification-planner wiring and hardware-dependent measurements
still require the inputs listed above.

VAOS and VYNDI business sessions were not authenticated by this setup. Their
earlier sign-in requirements remain open. No paid service was provisioned,
external message sent, business record changed or learned policy activated.

## Verification

Runtime dependency preflight passed. The focused capability, account, Google,
messaging and configuration batch ran 269 tests: 265 passed, four skipped,
zero failures. An outdated Google briefing fixture was corrected to initialize
the adapter's optional credential directory. Diff whitespace checks passed.
Existing unrelated working-tree changes were preserved.

Continuation verification ran 275 Python tests: 271 passed, four skipped,
zero failures. Ten desktop/startup Node checks passed. PowerShell syntax
checks passed, and the gateway starter reused the existing loopback service.
Sanitized restart and capability evidence is included in
`remaining-capabilities-20261023.json`.

The owned desktop was restarted. The running backend confirmed all optional
knowledge integrations ready. Authenticated, read-only workspace checks
returned the new `model-local-gemma` evaluation candidate, telemetry status,
OpenCode status and one healthy persisted monitor checkpoint. No voice session
was opened by the verification client. Eleven configured integration entries
include the eight host MCP services and three Electron-managed references;
that count does not certify those business account sessions.
