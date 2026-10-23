# Final 5P commissioning — SPARK RC `1a36a7b`

Historical capture. The current decision, operating restrictions and owner acceptance actions are in [the 2026-10-23 continuation](final-hold-resolution-20261023.md). Its Gemini-only, zero-cost and read-only restrictions supersede the future-action suggestions below.

- **Baseline release candidate:** `1a36a7b`
- **Local fix included in the tested build:** `62ebccc`
  (`UI: replace paid remote grain texture with local noise`)
- **Mode:** final Windows live commissioning, isolated from the production
  installation
- **Evidence:** [`evidence/rc-1a36a7b/`](evidence/rc-1a36a7b/)
- **Capture window:** 2026-10-22 18:37–19:33 UTC (2026-10-23 local)

## Decision

**Production readiness: HOLD — not approved for production.**

The isolated local RC is stable for the read-only cockpit and security-gated
workflows that were exercised. It is **not** production-ready as a complete
16-capability system: most provider-, account-, hardware-, and owner-gated
happy paths have no live success evidence. The production install, data,
credentials, original processes, and original backend port were not modified.

**Local RC acceptance: CONDITIONAL PASS** for:

- isolated startup and rendering;
- all 16 Capabilities Center destinations and all 22 Command Center
  destinations;
- read-only status/history actions;
- owner-gate refusals and token rejection;
- local no-evidence Deep Research;
- bounded code-skill propose/test/activate/run/deactivate;
- restart persistence and recovery startup;
- no remote texture dependency after the local-grain fix.

It is **not** an acceptance of live email, WhatsApp, cloud model, voice,
Gmail/Calendar/Drive, Graphiti/Hermes/Obsidian, VAOS/VEDM/VYNDI business
operations, Workbench data, OpenCode mutations, model-generated code skills,
Python tools, SAEE autonomy, or PC actions.

## 5P execution

| Phase | What was done |
| --- | --- |
| **Plan** | Defined isolation gates (port 8010, separate Electron profile, workspace data root, notes directory, 64-hex token), the 16-page/22-destination UI matrix, security-refusal criteria, persistence checks, and HOLD rules for absent credentials or hardware. |
| **Prepare** | Built the production renderer (`npm run build`), launched Electron with `NODE_ENV=production`, started the Python backend on `127.0.0.1:8010`, verified `/status`, and confirmed the original process tree was still alive. |
| **Proceed** | Exercised every Capabilities Center page and every Command Center destination; captured screenshots, Socket.IO traffic, request failures, and logs. Ran read-only external-token acceptance and owner-gate refusal tests. |
| **Perform** | Ran local research, the controlled code-skill lifecycle, memory persistence, restart/persistence, recovery-journal checks, and final diagnostics. Fixed one genuine pre-fix UI defect (paid remote grain texture returning HTTP 402) and retested the affected UI. |
| **Persist** | Restarted the isolated tree, rechecked `/status`, renderer isolation, memory/skill persistence, OpenCode sessions, and security gates. Sanitized the final evidence and committed the verified UI fix and regression test locally. |

## Isolation and safety

| Control | Result |
| --- | --- |
| Backend port | `127.0.0.1:8010` only; original backend port 8000 was not listening during this run. |
| Electron profile | Separate temporary `--user-data-dir`; separate single-instance lock and Chromium profile. |
| Workspace data | Separate `SPARK_WORKSPACE_DATA_ROOT`; separate `SPARK_NOTES_DIR`. |
| Auth token | Random 64-hex workspace token, supplied only through the temporary launch environment; not copied into evidence. |
| Renderer | `file:///…/dist/index.html?sparkBackendPort=8010`; backend port injected through the page query, not a static Vite value. |
| Socket traffic | Only `ws://localhost:8010/socket.io/…` was observed. Final reload used the 8010 websocket; final evidence has no failed application requests after connection. |
| Original SPARK | PIDs 24824 and 16360 were alive before and after every isolated restart. No original process was killed, restarted, or modified. |
| Original data | No production database, backup, credential, note, or workspace file was written. |
| External side effects | No real email, WhatsApp message, purchase, paid API enablement, deployment, merge, or uncontrolled self-modifying run. |
| Caveat | The isolated backend inherited the host Graphify MCP registration and spawned a read-only child that read the existing shared `graphify-out/graph.json`. No writes were observed, and the child exited with the isolated tree. This is an isolation caveat for future packaging, not a production-data write. |

The original production backend was not answering `/status` during this run
because port 8000 was not listening. The original Electron/process tree was
alive, and no cross-instance request was made.

## Startup, recovery, and warnings

Final isolated runtime:

- Electron root PID **25552**
- Python backend PID **22168**
- `/status`: `running`
- Uvicorn: `http://127.0.0.1:8010`
- Frontend: loaded successfully

Startup found the recovery call in `backend/server.py:32`
(`Maintenance(...).recover()`) and **no pending maintenance journals**. No
recovery action was required. Recovery/repair review actions remain
owner-gated and were not exercised.

Non-blocking observations, preserved honestly:

1. **False “backend offline” line.** Electron logs
   `SPARK core backend offline. Launching UI anyway; check Python dependencies.`
   before Uvicorn binds. The backend then starts and the renderer connects.
   This is a startup health-probe timing warning, not a failed backend.
2. **Missing `spark.ico`.** Electron warns that it cannot load the icon. The
   file is a generated, ignored asset (`npm run icon` produces it); the app
   still renders and functions. This should be fixed before packaging.
3. **Gemini alert.** The cockpit displays `SPARK CORE — GEMINI KEY REQUIRED`.
   This is expected missing-credential behavior, not a startup exception.
4. **No 402 after the fix.** The earlier remote grain texture request returned
   HTTP 402. The final build makes no remote grain request and has no 402 log
   entries.
5. **No blocking exceptions.** The final startup log scan found no
   `Traceback`, `Unhandled`, or `FATAL` entries. It did contain normal Python
   deprecation warnings.
6. **Transient reload polling refusals.** During one cold reload, Socket.IO
   logged a few polling `ERR_CONNECTION_REFUSED` entries before the 8010
   websocket connected. The final 16-page and 22-destination runs had 0 failed
   requests; no application action was lost.

## UI acceptance

### Capabilities Center — 16/16

All 16 pages reached the correct heading and completed the expected read-only
status action. The run sent 19 actions: 16 page status actions, one manual
Deep Research run, and three automatic read-only workspace list actions. There
were **0 exceptions, 0 log errors, 0 failed requests**, and **0 remote-noise
requests** in the final post-fix run.

Screenshots: `rc4-page-01.png` … `rc4-page-16.png` in the evidence directory.
Machine-readable results: `rc4-pages-16-summary.json` and
`rc4-pages-16-results.json`.

### Command Center navigation — 22/22

All 22 destinations reached the correct breadcrumb and heading, including
the Workspace, Build, Evolution, Systems, and Governance groups. The final
post-fix run had **0 exceptions, 0 log errors, 0 failed
requests**, and no remote grain request. Workbench deliberately returned its
owner-gate refusal; that is security evidence, not a navigation failure.

Screenshots: `rc4-nav-01-overview.png` through the selected key destinations
in the evidence directory. Machine-readable results: `rc4-nav-smoke.json`.

## Capability matrix

Legend:

- **PASS** — live evidence of the stated bounded behavior.
- **HOLD** — not exercised, or blocked by absent credentials/hardware/service,
  owner authorization, or an owner gate. A refusal is security PASS, but not
  capability PASS.
- **FAIL** — observed failure without a successful mitigation.

“Wiring PASS” means the page rendered, the expected action was sent, and the
result/notice was handled without an exception. It does not imply a successful
external workflow.

| # | Capability | Wiring | Live outcome | Acceptance |
| --- | --- | --- | --- | --- |
| 01 | Morning Digest | PASS | `digest_status` loaded. The recorded `latest_run.status` is `failed`; there was no successful live digest run. News is disabled and no schedule is set. | **HOLD** |
| 02 | WhatsApp Gateway | PASS | `hub_status` loaded; no account/session and no real message was sent. | **HOLD** |
| 03 | Proactive Agent | PASS | `proactive_summary` loaded; no live proactive action was approved or run. | **HOLD** |
| 04 | OpenCode Agent | PASS | Installed, sessions `0`; UI and external `opencode_run` were refused by the owner gate. | **HOLD** (security PASS) |
| 05 | Deep Research | PASS | Local run completed with 0 documents/citations and returned “No evidence retrieved… stopping rather than inventing.” No cloud call. | **PASS** for local no-evidence behavior; **HOLD** for cloud-backed research |
| 06 | Messaging Hub | PASS | `hub_status`/history loaded; no real send was authorized. | **HOLD** |
| 07 | Trace Learning | PASS | `trace_status`/labeled data loaded; no live learning cycle was run. | **HOLD** |
| 08 | Spec Search | PASS | `spec_search_status`/candidates loaded; no live specification query was accepted. | **HOLD** |
| 09 | Skill Ecosystem | PASS | Controlled code skill `86dac63709a8b931a8b6fe46` passed propose → test (2/2) → activate → run (`{"total":3,"passed":2}`) → deactivate; `generate_code_skill` was refused because Groq is not configured. | **PASS** for bounded code skill; **HOLD** for model-generated skills |
| 10 | Agent Runtimes | PASS | `agents_status`/runs loaded; `agents_react` was owner-gated and no agent execution occurred. | **HOLD** |
| 11 | Continuous Monitors | PASS | `monitor_status` loaded; `monitor_run` was owner-gated and no monitor was started. | **HOLD** |
| 12 | Adaptive Routing | PASS | `learning_status` loaded; `router_select` was owner-gated and no live route was chosen. | **HOLD** |
| 13 | Connector Catalog | PASS | `connector_status` loaded: two connectors disabled; only `obsidian-vault` and `workspace-search` adapters are attached. Cloud connectors require a consented, credentialed session. | **HOLD** |
| 14 | Standardized Evaluations | PASS | `eval_status`/history loaded; `eval_register` was owner-gated and no evaluation was run. | **HOLD** |
| 15 | Inference Telemetry | PASS | `telemetry_status` loaded with `entries: 0`; energy is `not_measured` and no inference was measured. | **HOLD** |
| 16 | Inference Backends | PASS | `backend_describe` loaded six engines; Ollama/Gemini/Groq are not configured, and llama.cpp/vLLM/SGLang are declared but inactive. | **HOLD** |

Aggregate: **16/16 UI wiring PASS**; **2 bounded local workflows PASS**
(Deep Research local no-evidence and controlled code-skill lifecycle);
**14 capability outcomes HOLD**. No external/provider-dependent capability
has a live end-to-end PASS.

## Security and refusal evidence

The external Socket.IO acceptance client used the isolated workspace token and
the local 8010 origin. It exercised 52 actions:

- **40 allowed** read/status actions, including history, telemetry, diagnostics,
  memory search, skill listing, and connectivity reporting.
- **12 refused** by the owner gate. These included `opencode_run`, `hub_send`,
  `agents_react`, `monitor_run`, `router_select`,
  `connector_attach_local`, `eval_register`, `telemetry_record`,
  `backend_probe`, `learning_activate`, `skill_import`, and
  `workbench_snapshot`.
- **Wrong token refused:** `Invalid workbench action or arguments.`
- **Missing token refused:** `Reconnect the Spark desktop workspace. If face
  lock is enabled, unlock it first.`
- **UI OpenCode run refused** with the same reconnection/face-lock message;
  `opencode_status.sessions.count` remained `0`.
- **Workbench snapshot owner-gated**; live Workbench data remains HOLD.
- **SAEE autonomy disabled**: `enabled:false`, `last_status:not_run`,
  `running:false`; no autonomous code changes were run. The SAEE registry
  reports 17 capability records, 3 deliberate gaps, and `measured:false`; it
  explicitly says runtime behavior and security are not independently verified.
- **Python tools disabled**: `{enabled:false, auto_forge:false}`;
  `list_python_tools` and `list_repository_analyses` were empty.
- **PC autonomy not authorized**: `pc_autonomy_session_authorized:false`; no PC
  action was executed.

These refusals are recorded as security PASS, not as capability failures.
Security checks were not bypassed to manufacture a success.

## Persistence and recovery

After a full isolated restart:

- `/status` returned `running`.
- Memory marker `6a1b837d280f9e91a6f04a12e630cc36` was still retrievable.
- Code skill `86dac63709a8b931a8b6fe46` was still present and `inactive`.
- Its two test results were still `[{"passed":true},{"passed":true}]`.
- `opencode_status.sessions.count` remained `0`.
- SAEE status remained disabled.
- The final Socket.IO connection was to 8010; no failed application requests
  remained after the connection.
- No maintenance journal was present, so no recovery or rollback was pending.

## Pre-fix defect and retest

**Defect:** the cinematic grain used
`https://grainy-gradients.vercel.app/noise.svg`. In the earlier navigation
capture, the third-party asset returned HTTP 402 and produced a console log
error. This is an external paid dependency and an unnecessary production
failure mode.

**Fix:** `62ebccc` replaces the remote background URL with a local
`.spark-noise` data-URI SVG texture in `src/index.css`, updates the three
components that used it, and adds
`tests/local-noise-asset.test.cjs` to prevent a remote texture from returning.

**Retest:**

- `node --test tests/local-noise-asset.test.cjs tests/command-center-ui.test.cjs`
  passed 2/2.
- `npm run build` succeeded.
- `dist` contains `.spark-noise` and the local data SVG; it contains no
  `grainy-gradients` or `noise.svg` reference.
- The final 16-page run and 22-destination navigation run had no remote-noise
  request, no 402, no log error, and no failed request.

This was the only functional UI defect fixed during commissioning. The
missing generated icon and the false startup offline warning remain
non-blocking warnings. No security control was relaxed.

## Verification status

| Check | Result |
| --- | --- |
| GitHub Actions for `1a36a7b` | Run `39830447107` passed `verify` and `intelligence` on Ubuntu and Windows. |
| PR #51 | Still open/draft and mergeable; not merged. |
| Local fix `62ebccc` | Committed locally only; not pushed, not CI-tested, not merged. |
| Final build | Production renderer built successfully; local noise asset present. |
| Targeted regression tests | 2/2 passed. |
| Full suite | Not rerun end-to-end in this commissioning pass; CI results above are for `1a36a7b`, not the local fix. |

## Host resource caution

Final diagnostics:

- CPU: **69.6%**
- RAM: **90.5% used**, **0.73 GB available** of 7.7 GB
- Disk: **10.02 GB free**
- Battery: 100%, AC connected
- `live_state`: `setup_required`
- `hands_free_ready`: `false`

The app remained responsive, but the low RAM headroom is a production risk
for live model, voice, browser, and agent workloads. It should be addressed
before any production promotion.

## Connectivity and integration limits

Final `connectivity_report` (`{deep:false}`) contained 16 entries:

- Graphify: **partially operational**
- Graphiti, Hermes, Obsidian: **not installed** in the RC runtime
- REA: installed but disconnected
- VEDM: partially operational
- VAOS, VYNDI OS, VAOS Jarvis: installed but disconnected
- GitHub, Google Drive, Gmail, Google Calendar, Slack: not installed
- LLM providers: not installed/configured
- Voice and multimodal services: installed but disconnected

`list_integrations` showed Graphify configured as read-only stdio, and
VAOS-Jarvis, VYNDI-OS, and VEDM as session-managed. Gmail, Drive, Calendar,
GitHub, Slack, and VAOS were unconnected. These are live-service HOLDs, not
claims of success.

## What would clear the HOLD

1. Configure Gemini/Groq and the owner-approved live model, then run successful
   model and voice paths.
2. Configure and consent to Gmail, Calendar, Drive, GitHub, Slack, and WhatsApp
   test accounts; run non-destructive send/read tests with explicit owner
   approval.
3. Install/configure Graphiti, Hermes, Obsidian, and the VAOS/VEDM/VYNDI
   services; verify live data paths and write boundaries.
4. Provide an authorized owner Workbench session and exercise its read/write
   path with a snapshot.
5. Authorize and test OpenCode mutations, agent reactions, monitor runs,
   routing, evaluations, telemetry recording, Python tools, and SAEE only in a
   bounded test workspace with rollback.
6. Generate `public/spark.ico` in the package pipeline and fix the startup
   health probe so the false offline warning is not emitted.
7. Re-run CI on commit `62ebccc` (or the final release commit), obtain
   independent SAEE runtime/security measurement, and resolve the Graphify
   shared-artifact isolation caveat.
8. Re-check host RAM/disk headroom for production workloads.

## Evidence index

All paths below are relative to this report:

- [`evidence/rc-1a36a7b/README.md`](evidence/rc-1a36a7b/README.md)
- [`evidence/rc-1a36a7b/rc4-pages-16-summary.json`](evidence/rc-1a36a7b/rc4-pages-16-summary.json)
- [`evidence/rc-1a36a7b/rc4-pages-16-results.json`](evidence/rc-1a36a7b/rc4-pages-16-results.json)
- [`evidence/rc-1a36a7b/rc4-nav-smoke.json`](evidence/rc-1a36a7b/rc4-nav-smoke.json)
- [`evidence/rc-1a36a7b/rc4-post-restart.json`](evidence/rc-1a36a7b/rc4-post-restart.json)
- [`evidence/rc-1a36a7b/rc4-final-status.json`](evidence/rc-1a36a7b/rc4-final-status.json)
- [`evidence/rc-1a36a7b/rc4-final-audit.json`](evidence/rc-1a36a7b/rc4-final-audit.json)
- [`evidence/rc-1a36a7b/socket-acceptance.json`](evidence/rc-1a36a7b/socket-acceptance.json)
- [`evidence/rc-1a36a7b/skill-acceptance.json`](evidence/rc-1a36a7b/skill-acceptance.json)
- [`evidence/rc-1a36a7b/ui-refusal-opencode.json`](evidence/rc-1a36a7b/ui-refusal-opencode.json)
- [`evidence/rc-1a36a7b/02-isolation.json`](evidence/rc-1a36a7b/02-isolation.json)
- [`evidence/rc-1a36a7b/pre-fix-402.json`](evidence/rc-1a36a7b/pre-fix-402.json)
- [`evidence/rc-1a36a7b/startup-log-excerpt.txt`](evidence/rc-1a36a7b/startup-log-excerpt.txt)
- Screenshots: `rc4-page-01.png` … `rc4-page-16.png`,
  `rc4-restart-dashboard.png`, `rc4-capabilities-center.png`, and selected
  `rc4-nav-*.png` files.
