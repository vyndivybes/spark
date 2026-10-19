# OpenJarvis integration audit

Inspected upstream revision: `2817faa5fe9dbf0612f56be46f77d7c5c38e271c` from
https://github.com/open-jarvis/OpenJarvis, Apache-2.0. Spark baseline is
`0d103d1`, one commit ahead of default branch `654c60c`, plus the preserved local
Workbench/recovery implementation. Local printer, camera-capability and settings
edits predate this assignment and must not be overwritten or published.

Baseline Python: 171 tests, 170 passed, one skipped, native Python 3.11.9.
The inspected source areas contain 153 files and 139 top-level Python definitions.
CI currently runs Ubuntu JS/build checks and selected lightweight Python suites.
OpenJarvis declares Python >=3.10,<3.14 and native Windows installation support.
Its default dependencies include datasets, telemetry, and model provisioning;
these are inappropriate for mandatory installation on this resource-constrained
device. No upstream installer or model-download command is executed.

| Capability | Spark implementation | OpenJarvis implementation | Integration method | Dependencies | Security risk | Acceptance |
|---|---|---|---|---|---|---|
| Agent lifecycle/checkpoints | Approved transient task engine and durable routines | agents/native_react.py, operative.py, manager.py | Extend exact action grants with persistent structured checkpoints | SQLite/asyncio | Stale grants, uncertain effects | Resume, cancel, duplicate execution, project isolation |
| Scheduling | Local agenda only | agents/scheduler.py, scheduler/store.py | Optional persistent scheduler, one worker, read-only job grants | Optional croniter | Unattended mutations | Restart, once/interval/cron, no overlapping runs |
| Learning | Skill examples/revisions | learning/agents/{dspy,gepa,ace}_optimizer.py | Verified traces and supervised candidate evaluation; optional engines gated | Optional research extras | Self-awarded scores/permissions | Real baseline/candidate comparisons, approval and rollback |
| Health/recovery | Diagnostics and source rollback | agents/errors.py, loop_guard.py | Bounded backoff/circuits/heartbeats and explicit owned-service recovery | Standard library | Retry storms/unknown side effects | Outage, timeout, circuit-open, escalation |
| Memory | ARKUS SQLite FTS5 BM25 | tools/storage/hybrid.py, connectors/hybrid_search.py | Reuse FTS5, adapt RRF, optional offline embeddings/FAISS, TTL task/session memory | Optional local embedding packages | Private context disclosure | Citations, deduplication, isolation, fallback, deletion |
| Routing | Fixed Gemini/Groq voice paths | learning/routing/{complexity,router}.py | Separate opt-in task router; existing live sessions untouched | Existing clients, optional local HTTP | Silent cloud fallback | Context/privacy/cost constraints, outage |
| Skills | Tested declarative arithmetic | skills/{parser,dependency,executor,security}.py | Reviewed SKILL.md and existing allowlisted pipelines | Optional PyYAML | Instruction injection/unapproved shell | No permission escalation, activation and rollback |
| MCP/business | Host-configured stdio and REA | mcp/{client,transport,protocol}.py | Extend current bridge with per-tool policy, HTTP, audit and health | Existing optional MCP SDK | Mutations/credential leakage | Read-only default, schema and host scopes |
| Evaluation | Regression suite only | evals/, telemetry/ | Local exportable measured outcomes, latency and retrieval benchmarks | Standard library | Fabricated measurements | Exact results; energy/TTFT unavailable unless measured |
| Upgrades | Repair directly applies tested changes | learning artifacts and versioned policies | Stage/inspect/test/approve activation; snapshot/rollback; separate PR | Git/current test runner | Unreviewed production edits | Candidate rejection and previous-version restoration |

The implementation manifest tracks each capability individually. This audit
establishes design inputs; it is not evidence that any new feature already works.
Research optimizers, model-weight training, unavailable business endpoints,
physical devices and unmeasured energy remain explicitly optional or blocked.
No upstream unrestricted shell/filesystem executor is exposed to Spark agents.

Final implementation and qualification: see `openjarvis-integration-manifest.json`
and `intelligence-verification.md`. CI now adds Python 3.11 Windows and Ubuntu
intelligence jobs. VAOS (`06bdb059d01b6ea85b985f133db55041ad1f2bbd`)
and VYNDI OS (`cb4051542b4e94ab583153c18022ef51f32ea2eb`) were inspected
through their actual repositories. VYNDI requires signed governed request
context; no generic adapter credentials were invented or copied. No proprietary
business source was copied into Spark.
