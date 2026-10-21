# Integration acceptance — 21 October 2026

This record distinguishes direct acceptance from configuration and from account authorization. Machine-specific configuration is in ignored `backend/.env` and `spark.local.json`. Provider keys and GitHub credentials are not copied into source control.

| Connection | Acceptance in this session | Remaining boundary |
|---|---|---|
| Graphify | Live MCP discovery returned 10 tools; recent successful operation already audited. | Architecture graph freshness depends on its last rebuild. |
| Gemini | Model catalog accessible and real `gemini-3.8-live` WebSocket handshake passed. | Audible browser session and interruption still need user acceptance after restart. |
| Groq | Real `openai/gpt-oss-20b` generation passed through HTTPX with direct transport. | Initial urllib request returned HTTP 403; this is not treated as credential failure after the successful supported transport. Camera interpretation was not tested. |
| Ollama | Downloaded `gemma3:1b`, probed it through Spark Models, and generated `OK.`. Registered as `local-gemma`. | Model answers remain unverified content; model probes must be run in each new Spark runtime before task routing. |
| Graphiti | Four MCP tools discovered; `graph_status` returned installed and credential readiness; native bounded Kuzu query passed; a synthetic-only cloud extraction added one episode with zero failures. | No personal project records were ingested in this check. Graph retrieval/contradiction quality is not independently qualified. |
| Hermes | Installed in `.venv-hermes`; three MCP tools discovered; `hermes_learning_status` returned available through Spark Integrations. | Zero learned skills and memories on this machine. This reader does not turn Hermes into an autonomous executor. |
| REA | Actual cached REA MCP discovery returned 207 tools. | Individual reverse-engineering actions still require selected targets and their existing controls. |
| Obsidian | Created `~/Documents/Spark Vault`, configured it, and verified local note search. VAOS, VYNDI OS and VEDM have source-linked notes. | These are local notes and portal links, not automatic business-record synchronization. |
| GitHub | Registered three read-only tools through the existing GitHub CLI sign-in; a real repository read succeeded for `vyndivybes/spark`. | This adapter is restricted to the host-selected repository and has no write tools. |
| Webcam | Opened the local camera and received a 640 × 480 frame. | Image was neither saved nor uploaded. Face authentication and hand tracking were not accepted by this test. |
| Microphone | Enumerated devices and read a real local microphone buffer. | Audio was neither saved nor uploaded. Speaker audibility needs a user listening check. |
| CAD/browser prerequisites | `build123d` and Playwright are installed. | No physical print, slicer, live browser-agent task or smart-home operation was performed. |
| VAOS / Jarvis | Verified from the running Spark desktop: its existing isolated VAOS session returned a real response to the default workforce-status question. The panel displayed “VAOS advisory received. No business action was executed.” | This validates advisory access. The panel invokes Electron directly, so its success is not recorded in the backend MCP audit used by Connections. Separate generic VAOS MCP registration remains absent. |
| VYNDI OS | Portal returned HTTP 200. Its actual `/api/runtime/health` returned database OK, schema current, and governed IBPE run present. Added isolated portal control in Spark. | The user signed in within Spark’s isolated portal; the authenticated Command Centre rendered successfully. This verifies interactive portal access. The built-in read_vyndi_engineering_authority tool now passes live authenticated reads. Its seeded authority graph remains separate from live business ledgers; automatic record synchronization is not implemented. |
| VEDM | Engineering-library portal returned HTTP 200. Added isolated portal control and a local source-linked vault note. | The VEDM Engineering Home rendered successfully inside Spark’s isolated portal without a new sign-in prompt. The built-in read_vedm_library tool now passes through Spark’s MCP path and reads the final published library state. It does not provide automatic synchronization or engineering release authority. VYNDI OS source exposes GET /api/engineering/authority behind requireBusinessActor("view"); it reports a seeded authority graph and must not be presented as a live engineering ledger. |
| Gmail / Google Drive / Google Calendar | Spark Desktop OAuth authorized for the user-selected personal Google account with read-only scopes. Encrypted CLI credentials stored outside the repo. Gmail API enabled. All three real account checks passed; bounded list reads returned 10 mail IDs, 10 files and 2 calendars. Registered six read-only MCP tools across three services. | Reopen Spark to load the saved host registry. No mail, file or event writes are exposed. |
| Slack | Read-only account adapter implemented and tested; workspace selected as vyndi. | Spark app A0CAU4KNH0A installed in vyndi (T0C0T8YQLLT) after user approval, with only channels:read and no event subscriptions. The user saved its bot token through the local hidden-input setup. Both slack_account_status and slack_list_channels passed through Spark MCP; the latter returned six public channels. The host registry and successful audit records are saved. Reopen Spark to load the connection. No token was included in chat or source code. |
| Kasa / printer | Existing integrations retained. | No configured physical device was supplied for acceptance. |

## Fixes

- Graphiti loads the checkout's private provider configuration in its isolated MCP process.
- Its status request checks package presence without loading the inference stack on the MCP event loop.
- Kuzu uses a 128 MiB buffer pool, two worker threads and a 2 GiB database bound instead of reserving approximately 80% of host RAM. The adapter is tied to the already pinned graphiti-core 0.31.x constructor; query/schema/operation implementations remain upstream's.
- Hermes receives EOF on its own stdin, rather than inheriting Spark's live MCP pipe and blocking until timeout.
- Launcher registration preserves host account adapters while adding bundled sidecars. Ignored local preferences persist Graphiti, Hermes and Obsidian selections.
- VAOS's Electron-managed bridge is recognized by the connectivity inventory even without a stdio registration.
- Obsidian read/search containment rejects sibling paths sharing the vault's filename prefix.
- VYNDI OS and VEDM use separate sandboxed sessions and fixed origins. Opening a portal does not create business API authority.

## Validation and activation

Production Vite build passed. Full JavaScript run: 107 passed, zero failed, one skipped. Twenty connectivity regressions plus five new focused Python tests passed. A PowerShell execution check verified that account adapter registrations and local preferences survive launcher assembly. Native MCP, model, camera, microphone and public-portal checks are recorded above.

The running Spark backend was idle but still used its old launch configuration (`graphiti_ready` and `hermes_ready` false). The tool policy rejected the process-stop/restart command before execution. Close Spark normally and reopen the SPARK desktop shortcut to activate the saved configuration and updated Electron business portal controls. Then open VAOS Jarvis and sign in directly. Credentials and account sign-in have not been manufactured or bypassed.

## Google account acceptance update

The selected account was verified through Gmail profile before each service read. Registration was written only after all three service checks passed. All three account-status tools also passed through Spark’s actual MCP execution and wrote successful audit records. The account-adapter and connectivity regression batch passed 26 tests. Google OAuth client JSON and encrypted credentials remain outside the repository; no provider token or client secret was included in this record.

## Business reference read implementation

Added two built-in Electron-session tools without consuming extra stdio registry slots: `read_vyndi_engineering_authority` and `read_vedm_library`. Both are available through Spark Integrations and the Jarvis panel after restart. The VYNDI read uses the confirmed authenticated `/api/engineering/authority` contract and explicitly labels its seeded reference provenance. The VEDM read projects the final `VEDM_LIBRARY` state from the fixed-origin sandboxed portal after its published overlays execute normally. Parsing the initial JavaScript literal was rejected after a live check showed that it would omit subsequent revision updates.

The bridge accepts only two fixed portal IDs, requires the existing launch token, rejects extra arguments, bounds response size, and keeps cookies in Electron. Connectivity probes for these built-ins require an actual successful read; discovery alone is insufficient. No record writes, synchronization, credential export, or release authorization are added.

Validation: production build passed; 29 focused Python checks and seven Electron checks passed after the final changes. The broader JavaScript batch passed 111 tests with one skipped before the final VEDM projection adjustment; the affected seven tests passed again afterward. Live VYNDI authority read passed in the restarted Spark panel: schema VYNDI_VEDM_AUTHORITY_GRAPH_V1, valid true, releaseReady false. After the final restart, VEDM read passed in the running Spark panel and returned the overlaid issuedAt value 2026-09-28T02:05:33+05:30 with preserved development and release holds. Connections displayed both VYNDI OS and VEDM as verified operational. The actual backend SQLite audit independently recorded successful mcp_call operations for read_vyndi_engineering_authority and read_vedm_library. Both new reference tools are live-verified. Portal sign-in and the existing VAOS advisory are separately verified above.

## Automatic pull synchronization

User selected pull updates into Spark, not two-way writes. Added a persistent SQLite snapshot cache under the local workspace, an application-lifetime scheduler, and a fixed allowlist of provider reads. Host settings enable a 300-second interval. VAOS Jarvis advisory has a 900-second minimum interval, including manual refresh. Failures retain the prior successful data and back off to at most one hourly retry. Identical snapshots keep their version, pause/settings survive restart, and no arbitrary MCP write or refresh-graph tool is scheduled. Model/device connections contribute status only; no automatic sensor capture or physical actuation is added.

Connections, Knowledge and Memory now include a cache status browser, pause/interval controls, manual refresh, local search and source inspection. These account snapshots remain separate from manually imported project documents and separately approved HOLO/model publication. Reads of this cache use the trusted workspace nonce and existing face-auth requirement without requiring an active voice model. VEDM background reads use a hidden sandboxed portal. Successful local workspace reads also clear the stale connect banner.

Live pre-activation pull: 13 feeds succeeded (Graphiti status, Hermes skills and memory cards, GitHub repository/PRs/issues, Gmail IDs, Drive files, Calendar listings, Slack public-channel metadata, Graphify tool availability, bounded Obsidian note excerpts and connection status). Existing readers retain their bounded result limits; this is not a full mailbox/archive mirror. Business-session sources join the automatic scheduler inside Electron after restart.

Validation: 36 focused Python checks passed; 37 workspace/auth/API tests with 122 subtests passed; the scheduler tests include a second scheduled pull without manual refresh and authorization denial. Full JavaScript batch: 111 passed, one skipped. Seven affected Electron tests passed after the hidden-portal change. Final production build passed. Live acceptance passed after restart: all 16 planned feeds have successful snapshots, including VAOS Jarvis, VYNDI OS and VEDM. SQLite settings confirm enabled=true and interval=300. Running Spark Connections renders the enabled automatic-pull control and current source rows. A real local cache search for VEDM returned source-backed results while the voice engine was unavailable, confirming that cache access does not require an active voice session. An adjacent audio-engine startup error was observed and remains outside this synchronization change.

## Workspace access independent of voice

The repository-screen authentication error was caused by requiring audio_loop.session for every workspace action. Added a separate, strictly per-launch-token-validated path for local documents, knowledge and bounded repository reads. Optional face authentication remains required. Execution, device, REA execution and upgrade operations retain their existing active-owner/session gates. Origin alone does not authorize the offline path. Synchronization access now uses the same strict token and face-auth check.

Verification: 51 Python tests and 126 subtests passed, including actual extracted socket-handler requests with no audio loop, valid/missing tokens, locked face authentication and rejected execution. Four workspace wiring/root-token checks passed. Runtime activation requires a backend restart. The audio-engine startup failure itself is not changed by this access fix.
