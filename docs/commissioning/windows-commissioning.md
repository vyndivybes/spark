# Windows Commissioning — OpenJarvis all-16 integration

Real-app commissioning of the sixteen OpenJarvis capabilities (issue #49) on the
native Windows host, against the **real Electron + Python stack** in this
worktree (`codex/openjarvis-all-16-integration`, draft PR #50).

Every claim below is backed by a file under `docs/commissioning/evidence/`
(captured from the running application via the Chrome DevTools Protocol and a
socket.io workbench client). Nothing was dry-run, mocked, or reconstructed.

## Isolation guarantee (original SPARK untouched)

The user's production SPARK installation (`C:\Users\ASUS\spark`, backend on
`127.0.0.1:8000`) was **running throughout** and was never modified. The
commissioning instance ran fully isolated:

| Concern | Mechanism |
| --- | --- |
| Backend port | `SPARK_BACKEND_PORT=8010` (uvicorn + Electron health checks + renderer socket) |
| Electron profile | `--user-data-dir=<temp>\appdata\spark` (separate single-instance lock and Chromium profile) |
| Workspace data | `SPARK_WORKSPACE_DATA_ROOT=<temp>\data`, `SPARK_NOTES_DIR=<temp>\notes` |
| Auth token | Deterministic 64-hex `SPARK_WORKSPACE_TOKEN` honored by Electron (`a46dbf9`) |
| Renderer socket | Backend port injected via page query `?sparkBackendPort=` (`ec41630`) — see defect D6 |
| Painting under CDP | `--disable-features=CalculateNativeWinOcclusion` (compositor keeps producing frames for evidence capture) |

Isolation was verified by CDP `Network.webSocketCreated` inspection: the
renderer's socket.io endpoints all target `http://localhost:8010/...`, and the
original backend continued answering `GET /status → 200` on port 8000.

## Gate A — interpreter & dependency bootstrap

* PyAudio has no Python 3.14 wheel → the backend uses the system
  **Python 3.11** (`SPARK_PYTHON`), which has full wheel coverage.
* Runtime dependencies (python-socketio, fastapi, uvicorn, opencv-python,
  PyAudio, playwright, mediapipe, google-genai, …) installed into the user
  site-packages of Python 3.11. No dependency was added to or removed from the
  original SPARK installation.

## Gate B — process isolation

* `electron-root-pid.txt` tracks our root Electron PID; only that tree was
  ever killed/relaunched (`taskkill /T /F` on our own PID).
* Backend confirmed listening on **8010** owned by our child Python; the
  original stayed on **8000**.

## Gate C — all 16 Capabilities Center pages (real UI)

The CDP driver drove the real production renderer: opened `Dashboard →
Capabilities Center`, clicked **all 16 page chips (01–16)** and each page's
**Refresh status**
control (a real `workspace_action` round trip over socket.io to the isolated
backend). `pages-16-summary.json` records the per-page status and last result:

Pages with a genuine backend dispatch result or honest refusal: **16/16**

* 13 pages recorded a `"… status completed for default."` bar (digest, hub,
  opencode, skill, memory, connections, integrations, approvals, history,
  schedules, experiences, telemetry, learning…), with real JSON payloads, e.g.
  page 16 `backend_describe` → `"engines": [...]` (6 engines), page 09
  `skill_status` → operations registry JSON.
* Page 05 (Deep Research) honestly refuses an empty auto-run:
  `research run was refused: Invalid workbench action or arguments.` — the
  authorization passed (read-only allowlist); server-side validation then
  refused the empty question. `research_run` auto-dispatch with an empty
  question was removed in `646440a` (D8).
* Page 04 (OpenCode) status → real discovery JSON: binary
  `...\opencode-ai\bin\opencode.EXE`, `installed: true`.

Defects found and fixed during Gate C:

| ID | Defect | Fix |
| --- | --- | --- |
| D6 | Vite statically bundles `process.env` → renderer socket always hit port 8000 (isolation breach) | `ec41630`: port passed via page query; `sparkSocket.mjs` reads query first; Electron health-check/port-check honor `SPARK_BACKEND_PORT` |
| D7 | `Last result` panel leaked across pages (page 04's opencode discovery JSON rendered on page 05) | `646440a`: clear `lastResult` on page change |
| D8 | Page 05 auto-dispatched `research_run` with an empty question (bogus refusal on page open) | `646440a`: skip empty auto `research_run`, show honest notice instead |

Evidence: `page-01.png` … `page-16.png`, `page-04-run.png`,
`pages-16-summary.json`, `pages-16-results.json`.

## Gate D — governance chain (owner gate)

A token-authorized external socket.io client (`gate-d-results.json`):

* **Refused (owner-gated mutations)**, correct behavior without a live voice
  owner session: `opencode_run`, `hub_send` →
  `"Reconnect the Spark desktop workspace. If face lock is enabled, unlock it first."`
* **Refused safely**: unknown action → same owner-gate refusal.
* **Succeeded (by-design read-only/allowlisted voice actions)**:
  * `memory_remember` → `ok: true`, id `c30405483d663b164933a241c4a4f9ee`
  * `memory_search` → finds the stored memory (FTS5)
  * `digest_run` → a real digest record (honest `"status": "failed"` because
    no mail/RSS providers are configured — no paid APIs in commissioning)
  * `digest_history` → returns the created run
  * `telemetry_report` → real report

Known honest limitation: **live voice transcription could not be exercised**
— the host holds no GROQ/GEMINI credentials, so the audio loop reveals the
same banner shown in the cockpit (`ui-cockpit-isolated.png`,
"SPARK CORE — GEMINI KEY REQUIRED"). Governance of the whole voice command
chain (`spark_workbench_voice.py` in-process parser, owner-gating) is covered
by the test suite (`tests/test_spark_voice_capabilities.py`,
`test_spark_capability_owner_gate.py`) and the socket-level refusals above.

## Gate E — OpenCode execution

* Workbench discovery (page 04 status): binary found, `installed: true`.
* UI run attempt: the pilot prompt ("Confirm you are reachable…") was filled
  via real DOM events and `Run` clicked; `opencode_run` was **refused by the
  owner gate** — expected and correct for a mutating action without a voice
  owner session (`gate-e-results.json`, `page-04-run.png`).
* The same binary executed directly (operator-level check,
  `gate-e-cli.json`): `opencode --version` → `1.19.3`; a real `opencode run`
  session attempt spawns and honestly fails without a reachable provider
  endpoint (`Cannot connect to API…`) — the cockpit never auto-upgrades or
  downloads models at runtime, so this is the expected state until the owner
  supplies credentials.

## Gate F — restart persistence

`gate-f-post-restart.json`: the isolated app was killed (our PID tree only)
and relaunched with identical env. Post-restart:

* The pre-restart memory (`c30405483d663b164933a241c4a4f9ee`, 30-day TTL) was
  found **byte-identical** by `memory_search`.
* The pre-restart digest run (`created_at: 1792675366.0208127`) reappears in
  `digest_history` (1/1 overlap).

Both prove `SPARK_WORKSPACE_DATA_ROOT` persistence end-to-end.

## Regression status

* `node --test` UI suites: 12 pass / 0 fail (CommandCenter, navigation,
  unified workspace, Capabilities Center).
* Capability/voice/workbench suites: 37 passed / 93 subtests
  (`test_spark_evolution.py`, `test_spark_capability_owner_gate.py`,
  `test_spark_voice_capabilities.py`).
* Full-suite run (`python -m pytest -q`): 755 passed, 30 failed — the same
  30 tests (test_spark_tools / test_web_agent / test_cad_agent /
  test_spark_holo_bridge) fail identically at the `main` merge-base
  `41bcea6`, i.e. pre-existing upstream failures unrelated to this branch.
* Commissioning-time commits: `44b8112`, `2763044`, `ec41630`, `646440a`,
  `a46dbf9`.

## Not exercised (honest gaps)

1. Live microphone transcription / spoken-command happy path: blocked on
   founder-supplied GROQ/GEMINI credentials (same blocker as capabilities
   01/02/06). The refusal and banner paths are proven; the happy path is not.
2. Paid cloud inference: intentionally unconfigured (zero-cost rule); page 16
   reports the honest per-engine states.
