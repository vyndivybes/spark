# SPARK × OpenJarvis — 16-capability status matrix (A4 batch, 2026-10-22)

Branch: `codex/openjarvis-all-16-integration` (worktree `C:\Users\ASUS\spark-openjarvis16`). CI: all three jobs green (verify, intelligence ubuntu, intelligence windows) at commit `b1b8529`.
Definition-of-done framework: `docs/openjarvis-16-execution.md` (seven evidence gates).

## Score legend

| Label | Meaning |
|---|---|
| **implemented+tests** | Real backend module, owner-gated workbench actions, offline unit + wiring tests green |
| **configs-untested** | Live account/device/network acceptance still requires the founder's credentialed Windows session; honestly documented, never faked |
| **baseline-failure-untouched** | Fails on the pre-existing baseline (commit ab8ebb7) too; unrelated to the 16 modules |

## Matrix

| # | Capability | Module(s) | Workbench actions | Tests (unit + wiring) | Offline evidence | Live acceptance evidence needed |
|---|---|---|---|---|---|---|
| 01 | Morning Digest | `spark_morning_digest.py` (composes PR #48 Google snapshot), `spark_sync.py` | digest_status/run/history/ack/speech/speak/configure | 23+7 ✅ | triage, 24h delta, stale/forbidden per source, receipts, local System.Speech TTS, opt-in RSS | Real authenticated Gmail/Calendar/Drive reads + digest-speech acceptance by founder |
| 02 | WhatsApp | `spark_messaging_hub.py` (WhatsApp Cloud API + `understood_pricing` consent), docs/capability-02-whatsapp-and-hub.md | hub_status/configure/disconnect/approve/send/receive/history | 25+7 ✅ | approvals w/ nonce, rate limits, replay-protected inbound | Real Meta Business token + verified inbound/outbound message |
| 03 | Proactive agent | `spark_proactive_agent.py` (tiers, dedupe, remember, undo) | proactive_propose/decide/execute/undo/inbox/summary | 14+9 ✅ | tier gating, restricted never self-executed, restart persistence | Live notification channel push + founder approval round trip |
| 04 | OpenCode agent | `spark_opencode_agent.py` | opencode_status/run/diff/test | 15+3 (2 skip: opencode.exe not installed on host) | scoped sessions, diff capture, test prefix allowlist | opencode binary installed on host + real session run |
| 05 | Deep research | `spark_deep_research.py` | research_run (local-snapshots + obsidian-vault corpora) | 13 ✅ | 2–8 hop budget, dedupe, citations, no-evidence stop, contradiction flag | Real web/source reads over an account-bound corpus |
| 06 | Messaging hub | `spark_messaging_hub.py` (7 providers) | as 02 | (shared with 02) | per-channel states incl. configured-untested | per-channel verified reads/sends |
| 07 | Trace learning | `spark_trace_learning.py` | trace_capture/label/labeled/status, learning_propose/activate/rollback/status | 15+7 (1 honest skip) | masked capture, measured labels, held-out gate, owner activation | None required (offline evidence is complete); held-out live benchmark optional |
| 08 | Spec search | `spark_spec_search.py` | spec_search_status/run, spec_candidates/activate/rollback | 11+ (within B2 wiring) | diagnose/plan/test/gate/record loop, planner honestly not_configured, rollback | Owner grants zero-cost planner (see blockers) |
| 09 | Skill ecosystem | `spark_skill_ecosystem.py` | skill_import/review/list/run/runs/revoke/status | 14+ (B2 wiring) | license/provenance/sha256 gates, executable code refused, grant-gated pipelines, revoke | Signed skill bundle from real publisher |
| 10 | Agent runtimes | `spark_agent_runtimes.py` | agents_status/react/codeact/recursive/runs | 16+9 (within B2 wiring) | refuse-before-execute, step budgets, restricted CodeAct (not an OS sandbox — documented) | Live model-backed run with a configured provider |
| 11 | Continuous monitors | `spark_monitor_agents.py` | monitor_status/run/cancel/deliver/acknowledge | 15+9 ✅ | checkpoints, backoff, dedupe, compaction, durable cancel, JSONL notify | Restart survival on the live server process |
| 12 | Adaptive routing | `spark_trace_learning.py` (AdaptiveRouter) | router_select, learning_* | (shared with 07) | local-first, cloud permission gate, low-RAM measured fallback | A real configured local model for live routing |
| 13 | Connector catalog | `spark_connector_catalog.py` | connector_status/attach_local/configure/validate/read/freshness/revoke/events | 12 (incl. eval suites) +9 wiring | full lifecycle on two real local connectors; per-source states/rate limits/revoke | Cloud connectors reattach with founder-credentialed adapters |
| 14 | Standardized evaluations | `spark_evaluations.py` | eval_status/register/run/report/export/history | 12+ (C1 wiring) | 7 labeled suites, deterministic scoring, markdown export, provenance | Model-backed candidate runner (owner-attached) |
| 15 | Inference telemetry | `spark_inference_telemetry.py` | telemetry_status/capture/record/report | 13+ (C1 wiring) | measured-only: latency/tokens; TTFT streaming-only; energy refused without meter | Streaming engine for TTFT; hardware power meter for energy |
| 16 | Inference backends | `spark_inference_backends.py` | backend_describe/probe/generate/opt_in/events | (shared with 15) | honest per-engine states, cloud consent, optional engines hardware-gated, no downloads | Configured `SPARK_TASK_MODELS` engines on host (ollama/cloud tokens) |

## Aggregate test evidence

- All 16 capability suites: **237 passed, 4 skipped** (skips are honest: 2× OpenCode not installed, 2× policy honestly missing its own held-out gate on symmetric data).
- Full suite at HEAD: **735 passed, 30 failed, 53 skipped**.
- Baseline verification: the exact same **30 failures** exist at commit `ab8ebb7` (the PR #48 merge) — verified in a read-only temp baseline worktree, since the discrepancies between earlier 26/30 counts came from stale snapshot runs. Failure files: `test_cad_agent` (cv2), `test_web_agent` (GEMINI_API_KEY), `test_spark_tools` (cv2/GEMINI), `test_spark_holo_bridge` (HOLO source unavailable). **Zero regressions** from this work.

## Workbench superset

`backend/spark_workbench.py` dispatches **143 owner-gated actions** — all 16 capabilities are registered and dispatchable from SPARK's `workspace_action`/`integration_sync_action` socket handlers.

## UI/voice reachability audit (2026-10-22, first green CI at 5b…/b1b8529)

A full source sweep of `src/` (all React components), `electron/`, `android/`, and the backend voice grammar found that **the 16 capabilities have no UI or voice entry points today**; they are reachable over the socket layer only. Evidence:

- Every frontend `workspace_action` emit carries hard-coded action names; no component discovers actions dynamically (no `get_actions`/catalog socket event exists — `ACTION_KEYS` is used server-side only).
- Capability `digest_*`, `hub_*`, `opencode_*`, `research_run`, `proactive_*`, `monitor_*`, `trace_*`, `router_select`, `learning_*`, `spec_*`, `skill_*`, `agents_*`, `connector_*`, `eval_*`, `telemetry_*`, `backend_*` appear in **zero** frontend emit sites and **zero** `workspace_result` case handlers.
- Voice path (`backend/spark_workbench_voice.py` grammar → `server.py` `on_workbench_command`) produces only `executive_briefing`, `workbench_snapshot`, `save_preference`, `add_agenda`, `agent_snapshot`, `intelligence_health`, and MCP intents — none of the 16 groups.
- Partial exceptions: capability 01's *upstream briefing* (PR #48 Google snapshot) is surfaced through `ExecutiveBriefingPanel.jsx` (`sync_briefing`, `sync_now`) and `IntegrationSyncPanel.jsx` — but the `digest_*` actions themselves have no UI.

This means the OpenJarvis-16 definition of done ("reachable from SPARK UI/voice, not only a registered adapter") is **not yet met**; the honest current state is *backend-implemented, test-verified, socket-dispatchable, UI/voice-pending*. Surfacing them requires adding UI panels/voice intents per capability family — no backend gating changes.

## Remaining acceptance blockers (founder-side)

1. **Authenticated sessions** — Google (01, PR #48 checks), Meta WhatsApp (02), Slack/Discord/Teams (06).
2. **Host binaries** — `opencode` install (04); any local model engine config via `SPARK_TASK_MODELS` (12, 16).
3. **Hardware** — power meter with defensible measurement (15); ≥8 GB-measured RAM + explicit opt-in for optional engines llama.cpp/vLLM/SGLang (16).
4. **Data** — signed/real skill bundles from publishers (09); a live held-out benchmark corpus for routing (07/12).
5. **Restart evidence** — monitor/proposal persistence under the real server process (03/11).
6. Free-tier planner explicitly granted by the owner for capability 08 LLM-guided planning (otherwise it stays honestly `planner_not_configured`).
