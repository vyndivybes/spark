# Evidence index — SPARK RC 1a36a7b

This directory contains the sanitized evidence used by
`docs/commissioning/5p-final-commissioning-62ebccc.md`.

- Baseline release candidate: `1a36a7b`
- Local, un-pushed fix included in the final build: `62ebccc`
  (`UI: replace paid remote grain texture with local noise`)
- Capture window: 2026-10-22 18:37 UTC through 2026-10-22 19:33 UTC
  (2026-10-23 local time)
- Runtime: isolated Electron profile, Python backend on `127.0.0.1:8010`,
  separate workspace data root and notes directory, 64-hex workspace token
  supplied only through the temporary launch environment.

The original production SPARK process tree remained alive and was not
modified. The original backend port 8000 was not listening during this run; no
request was sent to the original backend. The isolated backend inherited a
configured Graphify MCP registration and read the existing shared
`graphify-out/graph.json` artifact; that is recorded as an isolation caveat,
not as a production data write.

## Sanitization

- Absolute local paths are replaced with `<rc>`, `<home>`,
  `<commission-temp>`, `<original-spark>`, or `<opencode-binary>`.
- The workspace token is not present in this directory.
- Private IPv4 addresses and email addresses were removed.
- Screenshot fields use `<evidence>/<filename>`.
- Raw logs and the temporary token remain outside the repository.

## UI and startup evidence

| File | Meaning |
| --- | --- |
| `rc4-restart-dashboard.png` | Final post-fix isolated cockpit after restart. |
| `rc4-page-01.png` … `rc4-page-16.png` | The 16 Capabilities Center pages after the local-grain fix. |
| `rc4-capabilities-center.png` | Final Capabilities Center state. |
| `rc4-nav-01-overview.png` | Command Center Overview. |
| `rc4-nav-05-capabilities-center.png` | Capabilities Center destination. |
| `rc4-nav-10-system-health.png` | System health destination. |
| `rc4-nav-14-workbench.png` | Workbench destination; owner-gated snapshot refusal. |
| `rc4-nav-15-recovery-rea.png` | Recovery & REA destination. |
| `rc4-nav-20-integrations.png` | Integrations destination. |
| `startup-log-excerpt.txt` | Sanitized startup lines, including the non-blocking false offline warning and missing `spark.ico` warning. |

`rc4-pages-16-summary.json` and `rc4-pages-16-results.json` contain the
per-page action, notice, status, result, clicks, request URLs, log errors, and
DOM checks. `rc4-nav-smoke.json` contains all 22 navigation destinations,
including the Workbench owner-gate refusal.

## Runtime, security, and persistence evidence

| File | Meaning |
| --- | --- |
| `02-isolation.json` | First-launch isolation proof: renderer URL, only `localhost:8010` Socket.IO websocket, no failed requests after load. The pre-fix remote noise request is retained as the defect record. |
| `pre-fix-402.json` | The pre-fix remote `noise.svg` 402 log entry. |
| `rc4-post-restart.json` | Final restart: `/status`, Socket.IO websocket, localStorage/RAM checks, memory/skill persistence, OpenCode session count, SAEE status, and no remote noise in the DOM. |
| `rc4-final-status.json` | Final `/status`, `get_diagnostics` snapshot, and `connectivity_report` called with `{deep:false}`. |
| `rc4-final-audit.json` | Clean final read-only audit: SAEE, Python tools, integrations, Workbench refusal, memory, code skills, OpenCode, diagnostics, connectivity, and maintenance directory state. |
| `socket-acceptance.json` | 52-action external Socket.IO acceptance: 40 allowed read/status actions and 12 owner-gate refusals; wrong and missing tokens refused. |
| `skill-acceptance.json` | Controlled code-skill lifecycle and model-dependent generation refusals. |
| `ui-refusal-opencode.json` | Final UI-level `opencode_run` refusal and session count. |

## Limits of this evidence

The evidence supports the UI wiring, isolation, refusal behavior, persistence,
and local no-evidence research result. It does **not** provide live happy-path
evidence for Gmail, Calendar, Drive, Slack, GitHub, WhatsApp, live voice,
Graphiti, Hermes, Obsidian, VAOS/VEDM/VYNDI beyond reachability/read-only
checks, Workbench data, OpenCode mutations, model-generated code skills,
Python tools, or autonomous SAEE/PC actions. Those remain HOLD and are listed
in the commissioning report.
