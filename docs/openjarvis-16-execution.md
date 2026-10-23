# SPARK × OpenJarvis — all 16 capabilities integration execution

**Tracking issue:** [#49](https://github.com/vyndivybes/spark/issues/49)  
**Baseline:** current SPARK `main`, with review/reconciliation of existing [Google briefing PR #48](https://github.com/vyndivybes/spark/pull/48)  
**Policy:** Windows 11 only, zero-cost / explicitly verified free-tier only, no forced WSL/Docker/heavy models, no uncontrolled side effects.  
**Source:** [OpenJarvis](https://github.com/open-jarvis/OpenJarvis), Apache-2.0; retain license and attribution for any reused source.  

## Definition of done (all 16, not 16 placeholders)

Each capability must pass **seven evidence gates**:
1. **Design:** define action contracts, permissions, failure modes, Windows requirements and data provenance.
2. **Implementation:** real code reachable from SPARK UI/voice, not only a registered adapter or a cloned repository.
3. **Unit tests:** deterministic success and failure cases, including credentials denied, timeout and rollback.
4. **Integration tests:** actual service/engine call through SPARK's signed session and audit system.
5. **Device/account acceptance:** when dependent on credentials or real hardware, perform a genuine read/action with the founder's configured account and explicit authorization.
6. **Observability:** display `not configured`, `configured, untested`, `connected`, `verified read`, `verified action`, `stale`, `blocked` or `failed` accurately; record trace ID, last success, source timestamp, failure reason and required intervention.
7. **Release:** code review, regression CI green, safe rollback, dependency/license scan, successful Windows startup and performance check.

Never relabel pending implementation as complete based on a fabricated response, an API schema discovery, a mocked fixture or a source-file match.

## Existing SPARK building blocks (extend; do not duplicate)

| Existing module | Use for |
|---|---|
| `spark_intelligence/runtime.py` / `service.py` | guarded agents, checkpoints, scheduling |
| `spark_sync.py` / `spark_google_mcp.py` | authorized Google snapshot reads and account identity |
| `spark_task_engine.py` / `spark_workforce.py` | task approvals, work orchestration |
| `spark_intelligence/memory.py` / `spark_grounding.py` | retrieval with source provenance |
| `spark_intelligence/models.py` / `policy.py` | task-model selection and quality gates |
| `spark_intelligence/skills.py` / `arkus_skill_forge.py` | skill review and stage/test/activate |
| `spark_evolution.py` / `spark_auto_evolution.py` / `spark_maintenance.py` | controlled self-repair and rollback |
| `spark_integrations.py` / `spark_connectivity.py` | MCP connectivity and allowed calls |
| `spark_host_vitals.py` / `spark_profiler.py` | measured host/resource health |

Existing `docs/openjarvis-integration-manifest.json` tracks earlier bounded adaptations only and cannot be interpreted as complete parity with the 2026 upstream repository.

## Delivery order and dependencies

| Wave | Capability IDs | Primary work | Acceptance owner |
|---|---|---|---|
| A1 | 01, 13 | Google auth and source read correctness; Morning Digest timeline/history | Real account authorization |
| A2 | 06, 02 | event bus, typed messages, WhatsApp and other channel adapters | Inbound/outbound test + consent |
| A3 | 04, 05 | OpenCode execution session + grounded deep research | Real working directory + source test |
| A4 | 03, 11 | scheduled proactive/long-running agents with durable approvals | Restart, escalation and notifications |
| B1 | 07, 12 | redacted traces and measured adaptive routing | Held-out task quality |
| B2 | 08, 09 | specification optimization and skill ecosystem | Side-by-side regression gate |
| B3 | 10 | advanced ReAct/CodeAct/recursive and external agents | Isolated runtime + tool restrictions |
| C1 | 14, 15 | standardized evaluations, inference latency/energy where available | Reproducible actual measurements |
| C2 | 16 | common backend layer with optional engines | Real opt-in inference + resource test |

All **16** are in scope even when a wave is blocked on credentials/devices. CI green is not permission to deploy or send external communications.

## Acceptance detail

**01 Morning Digest:** authenticated Gmail subject/snippet/body as consented; action triage, past 24-hour delta, reply-required candidates (never assert reply status without thread inspection), 48-hour calendar, task due dates, optional RSS and Drive changes; source URL, account and freshness; persisted job states and user-requested local speech. Reuse PR #48, but verify local runtime and 403 reason separately.

**02 & 06 Messaging:** permission-scoped message bus; configured providers attach connectors only when the user explicitly opts in. Before an outbound message, show recipient/channel/content and log message ID/delivery status. No unofficial WhatsApp bridge without informed opt-in about account restrictions and security; Meta Business API pricing cannot be assumed free.

**03 & 11 Agent execution:** daemon/job host with authenticated owner, persisted trigger, lease, checkpoint, no overlapping duplicate action, retries only for idempotent steps, cooldown, recovery after restart, digest to notification channel and approval queue. Device actions, business writes, shell and installations are never self-authorized.

**04 OpenCode:** discover installed `opencode` on Windows, controlled process lifecycle, allowlisted repo checkout, timeout and cancellation, output/diff capture, tests, human approval before activation. OpenCode should use the user's currently configured zero-cost provider, not automatically provision one.

**05 Deep research:** 2–8 bounded hops, local index + approved connector reads, deduplication, citations, contradictory evidence, and hard cutoff when facts cannot be verified.

**07, 08, 12 Optimization:** learn only from measured outcomes; compare baseline/candidate using held-out fixture and real source traces, hard regression thresholds, costs/quota guard and rollbacks. Do not confuse updated code with demonstrated intelligence improvement.

**09, 10 Skills/agents:** reviewed license, provenance, signing/checksum, explicit tool grants, scoped runtime; never activate arbitrary downloaded SKILL.md instructions as command authority. Sandboxing requires an actual OS boundary, not just a subprocess timeout.

**13 Connectors:** each new provider starts disabled. Scope, account identity, timestamps, pagination, revoke, rate limiting and failure states are individual, not inherited by a generic "Google connected" flag.

**14 Evaluations:** curated benchmark cases for email triage, meeting inference, research citations, safe software modifications, agent tool policy, memory retrieval and self-repair. Dashboard must show pass rate, sample count, failures and provenance.

**15 Telemetry:** real TTFT, tokens/sec, latency, RAM, CPU; energy (J or Wh) only if a supported device sensor provides defensible measurement. No made-up FLOPs or savings.

**16 Engines:** Ollama/Gemini/Groq current transports preserved. llama.cpp, vLLM, SGLang are optional lazy-loaded adapters and must be explicitly compatible with the user's available hardware. No model downloads or cloud fallback without authorization.

## Execution procedure for local OpenCode

Open SPARK's actual repository at `C:\Users\ASUS\spark`. First inspect `git status --short`, local branch, upstream branches, protected changes and any pending PRs. Do **not** reset or overwrite work in progress. Use feature branches/PRs; develop one testable vertical capability at a time. Run Windows Python and JavaScript regression tests in every batch; repair failures and post exact evidence to issue #49. Use existing `docs/intelligence-verification.md` as prior context but do not recycle old test numbers as current acceptance.

Use `python backend/spark_openjarvis_readiness.py` as an **unverified-by-default source inventory**. It intentionally does not make network calls and does not count source files as completed features. A future live verifier must attest each capability through account/device-specific execution evidence and display any blockers.

## Non-goals

- No standalone replacement for SPARK.
- No full OpenJarvis installer, unrestricted agent shell or unsandboxed autonomous code execution.
- No automatic merger of PR #48 or other active development work.
- No WhatsApp, email or external business writes without explicit scope and approval.
- No claim that a feature is "done" when it only exists in documentation or a static inventory.
