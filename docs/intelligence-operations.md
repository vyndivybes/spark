# Intelligence operations on Windows

SPARK keeps its React/Vite/Electron cockpit and Python backend. Intelligence is
an optional workspace module; it does not replace Gemini Live, Groq voice,
camera consent, authentication, CAD, printing or the browser.

## Start or restart

Close SPARK normally. If a development terminal is still running it, press
Ctrl+C in that terminal. Then, in PowerShell:

```powershell
Set-Location C:\Users\ASUS\spark
$env:SPARK_PYTHON = (Resolve-Path .venv\Scripts\python.exe).Path
npm run dev
```

For a built checkout, run `npm run build`, set `$env:NODE_ENV="production"`,
then run `npm start` in the same terminal with `SPARK_PYTHON` set as above.
The existing `start-spark.ps1` launcher also selects the isolated `.venv`.
Do not terminate unrelated Python or Node processes. Do not remove `.env`,
`backend/settings.json`, the reference image or workspace databases to restart.

Connect and authenticate, then open **Knowledge & Skills → Intelligence**.
Only the window owning the active session can use these operations. Face
authentication, when configured, is still required. Workspace calls also require
an exact local Vite origin or the per-launch desktop token. Only the root
cockpit frame can request that token through IPC; foreign websites and child
frames cannot obtain it. The backend inherits it privately at launch. Groq voice recognizes
“show my agent status” and “check system health” without task IDs. Gemini's
existing voice and core-status paths remain unchanged.

## Agents and scheduling

Create a plan, inspect its exact actions and arguments, approve it, and execute
it. A grant is bound to the plan hash. Plans contain at most 12 steps and may
depend only on earlier step indexes. Allowed actions are system status,
activated ARKUS calculation skills, project knowledge reads and host-approved
`mcp_read` calls. Shell commands and arbitrary filesystem writes are excluded.

Each completed step is checkpointed. A crash leaves an uncertain in-flight
step **interrupted**, requiring explicit review and resume. Completed steps do
not replay. Model agents propose one action per reviewed turn, retain their
session across restarts, and stop at six turns or a repeated action. Model
answers remain unverified; successful tool calls do not prove business facts.

Scheduling is **off by default**. Approve a ready plan, create a once, interval
or cron schedule, then explicitly enable the scheduler. Intervals are at least
60 seconds. Cron uses five fields and an IANA timezone. Optional cron support:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-intelligence.txt
```

The backend resumes an enabled scheduler when it next starts. It does not
install a Windows service, scheduled task or login entry. The backend must be
open for jobs to run. Missed intervals/cron times coalesce into one execution.
Once schedules reserve their claim durably before execution. Failures stop
the schedule for review; there are no endless retries. Cancel a workload or
disable the scheduler to stop future runs. Archive terminal workloads to free
the active-workload allowance. Retention is 200 active and 200 archived jobs,
and the latest 200 traces, model events, route events, configuration snapshots
and retrieval benchmarks per namespace.

Default job concurrency is one. A host operator may set
`SPARK_AGENT_CONCURRENCY=2` before launch; larger values are rejected. Keep one
on this laptop. A native OS file lease prevents another backend from taking
the same intelligence store. A leftover `worker.lock` filename is normal;
the operating system releases the actual lease when the process exits.

Set `SPARK_INTELLIGENCE_ENABLED=0` before launch to disable this module while
retaining the established assistant. Optional modules do not auto-install.

## Optional task models

No task model is registered or started automatically. Host configuration uses
`SPARK_TASK_MODELS`; the UI cannot supply executables, endpoints or secrets.
For an **already installed** Ollama model, an example registration is:

```powershell
$env:SPARK_TASK_MODELS='{"local":{"provider":"ollama","base_url":"http://127.0.0.1:11434","model":"YOUR_EXISTING_MODEL","context":4096,"quality_tier":1,"additional_memory_mb":512}}'
```

Supported provider values are `ollama`, `openai_local`, `groq` and `gemini`.
OpenAI-compatible local endpoints must be loopback HTTP URLs. Cloud endpoints
are fixed to their official providers. Cloud keys stay in host environment
variables; defaults are `GROQ_API_KEY` and `GEMINI_API_KEY`, or a host-selected
`api_key_env`. Choose a model already approved for your account and budget.
SPARK does not purchase credits or activate billing.

Discover configuration, select a model, and explicitly probe it. An unprobed,
unavailable or context-incompatible model cannot run. Routing previews prefer
local models and consider context estimates, declared quality/memory needs,
measured probe latency and availability. These declarations are estimates,
not independent model-quality or cost measurements. Only the specifically
selected cloud model is eligible when cloud consent is enabled. There is no
silent provider fallback and established live voice sessions never switch.

Task requests are serialized, bounded to 512 requested output tokens and a
20-second network timeout. Ollama receives `keep_alive: 0` to release its model
after the response. Failures clear availability; recovery requires an explicit
probe. Repeated failures open a circuit with increasing, bounded cooldowns.
Model usage journals retain metadata and provider-reported token counts, not
the submitted prompts or returned answers.

## Learning, skills and memory

Learning can stage a user-written prompt or generate a prompt/few-shot proposal
from execution classifications. The proposal generator receives action names,
verification flags and failure classes, excluding private tool outputs.
Candidates do not activate automatically. Supply 1–5 independent expected
answers and a probed model; each case executes a baseline and candidate call.
Exact trimmed equality is the documented scoring rule. Any regression, lower
score or zero correct answers rejects the candidate. Inspect evidence before
activation. Rollback restores the preceding active artifact. This is prompt
configuration improvement, not model-weight training. DSPy, GEPA and ACE
optimizer execution remains deferred; no research stack is installed.

Instructional SKILL.md imports support a bounded scalar-frontmatter subset:
`name`, `description`, `license`, `compatibility`, and comma-separated `depends`.
Unknown, duplicate or permission-granting metadata is rejected. Validation
checks metadata/dependencies, not the truth of natural-language instructions.
Inspect and approve activation separately. Running such a skill supplies
instructions to the selected model and returns text; it grants no tools.
Hermes/OpenClaw-specific executable extensions are not imported. Existing
ARKUS calculation skills retain their tests, versioning, activation and rollback.

Memory is project-isolated and local. Task/session/observation records have
provenance, deduplication, bounded retention and deletion. Default expiration
is 30 days. ARKUS remains the document authority, using SQLite FTS5 BM25.
RRF combines ranked results with citations. `KnowledgeBase` accepts bounded
`chunk_size`/`chunk_overlap` options for subsequent imports; defaults remain
850/100 characters.

Optional semantic retrieval requires compatible preinstalled dependencies and
an existing model directory in `SPARK_EMBEDDING_MODEL_DIR`. Loading uses
`local_files_only=True`, CPU execution and `trust_remote_code=False`; there are
no model downloads. A native free-RAM check requires at least 1.5 GiB before
loading an embedding model. The index examines at most 1,000 local records.
`SPARK_FAISS_ENABLED=1` selects FAISS only when its dependency is installed.
Missing dependencies, insufficient RAM or invalid vectors fall back to FTS5.
Real embedding-model/FAISS qualification has not been performed on this laptop.

RAG is a separate action requiring explicit consent to send relevant excerpts
to the selected model, plus cloud consent when applicable. Only the current
project is searched. The response includes source identifiers and remains
unverified. HOLO/Brain Map publication still requires its existing separate
sharing operation. Retrieval benchmarks execute local searches against your
independent expected source IDs; no datasets are downloaded.

## Neural Atlas (Graphify-backed, read-only)

Opening "Neural Atlas → notes graph" no longer renders the sample notes
vault. Each launch regenerates an atlas vault from the packaged Graphify
business inventory embedded in the VAYU workspace page
(`vendor/vayu-workspace/VAYU-Knowledge-Sphere-Live.html`) through
`scripts/neural_atlas_vault.py` and `backend/spark_neural_atlas.py`, then the
unmodified Brain Map viewer graphs it. The atlas therefore maps your real
VAOS/Vyndios universe: the Vayu Shastr organisation, its divisions, projects
(VAOS, Vyndios, VEDM, Studio, Altitude), contacts, indexed documents,
decisions and the event record, with every Graphify edge as a wiki link and
one cluster per node type. Files carry status, confidence, tags, properties,
timeline and backing-source notes; titles become node labels, ids keep
everything unique, and stale rebuilds are replaced wholesale.

The original local-notes flow is untouched elsewhere: HOLO Deck still uses
the published Spark-notes folder, Obsidian still browses the local vault, and
VAYU actions and imports remain separate. The extraction is read-only over
the packaged page; nothing is uploaded, and the vault lives under the SPARK
user-data directory. Graphify's hosted `query_graph` read tool remains the
voice/interaction path (`_graphify_registered()` in `backend/server.py`).

## MCP and business connections

`SPARK_MCP_SERVERS` is host-only configuration. Stdio entries use `command`,
`args`, optional scoped `env`, and an explicit `read_tools` list. Streamable
HTTP entries use `transport: "streamable-http"`, `url`, optional scoped
`headers`, and `read_tools`. Remote HTTP must use HTTPS; unencrypted HTTP is
allowed only on loopback. Catalogs never disclose credentials or headers.

Unknown/write tools are denied by default. Read-tool declarations must be
verified by the host operator; server annotations do not grant authority.
Input schemas are checked before calls, and external schema references are
rejected. Calls have bounded queues/timeouts and cancellation closes the
owned transport. The latest 200 audit events persist locally without tool
arguments, results or credentials. An approved reconnect restarts only the
owned client/stdio child and verifies discovery; it does not restart remote
business services.

VAOS, VYNDI OS, VEDM, VAOS Jarvis, Gmail, Drive, Calendar, GitHub and Slack
cards are explicitly unconnected until a real endpoint and authorization are
configured. Existing Codex connector credentials are not exported into SPARK.
VAOS/VYNDI remain authoritative for business records. Their governed/signed
business authorization must not be replaced by a generic local approval.

The separate direct REA console retains explicit per-call confirmation and
full tooling for approved analysis. The cached `rea-agents@6.5.0` runtime
actually returned 207 tool schemas during this integration. Autonomous REA
reads require registration through the same host-approved MCP read boundary;
agent plans cannot grant themselves arbitrary REA execution.

## Upgrades and rollback

Version/license visibility and `pip check` are read-only inspections. Public
GitHub release checks run only on request and install nothing. They are not a
vulnerability scan or independent license audit.

Generated source repairs stay staged. Inspect complete replacements before
approving local regression-test execution. A temporary directory is **not an
OS security sandbox**: approve tests only for code you have reviewed. Testing
receives a reduced environment that excludes provider credentials. Activation
is a separate approval and repeats validation. The fixed regression runner's
default timeout is 180 seconds; a host may set `SPARK_REPAIR_TEST_TIMEOUT` to
60–600 seconds. There are no model-selected shell commands.

Original source bytes/hashes and transaction journals precede live writes.
Failed activation restores originals. Interrupted applying transactions recover
before imports on startup. Manual rollback refuses to overwrite subsequent
human edits. Restart SPARK after a retained source repair or rollback. Generated
calculation skills also stay tested until separately activated in Skill Forge.

Scheduler configuration snapshots contain no credentials and require approved
restore. Intelligence schema version 1 is recorded with SQLite `user_version`;
a newer schema is rejected rather than silently downgraded. Before replacing
application versions or recovering damaged data, close the backend and copy
`%LOCALAPPDATA%\SPARK\workspace` to a private backup. Do not publish that folder.
Git source rollback does not delete or downgrade user databases. No production
merge, deployment, credential change or automatic updater is added here.

## Autonomous evolution engine (SAEE)

`backend/spark_saee.py` is the orchestration layer over the engines above. It
adds a capability registry, an advisory planner and a durable evolution ledger;
it does not add a new authority. Every source-changing step still runs through
the staged repository/repair engines and their existing approvals.

Discovery (`saee_discover`) matches a natural-language upgrade request against a
local inventory of capabilities that are actually present, reports genuine gaps
honestly (for example automatic deployment, weight training and file
organization have no engine), and returns a risk assessment plus a plan whose
steps name existing engine actions. It executes nothing; `executed` is always
false. A request with no matching engine is reported as `medium` risk needing a
new design, never as covered.

The ledger records attempts (one row per pipeline stage), deduplicated error
signatures with any verified repair, repairs and before/after benchmarks across
the master-prompt pipeline (`request → inspect → plan → risk_check → isolate →
develop → test → security_check → benchmark → release_gate → deploy → verify →
monitor`). `saee_failures` lists signatures with no verified repair. Records are
project-isolated JSON under `%LOCALAPPDATA%\SPARK\workspace\saee` written with
the same atomic write used by maintenance, and linked storage directories are
rejected. These actions are exposed to the authorized workspace session through
the existing evolution dispatch; no shell, merge, deploy or credential action is
ever automatic. Capability presence and test coverage come from the local
inventory and are not an independent security audit.

`saee_inventory` goes further than the static registry: it scans the real
checkout read-only, confirming each declared capability's engine module exists
and locating a test that names it, and it collects the action keys other modules
actually expose. It reports `missing_modules` and `untested` honestly and never
imports or executes the scanned code. A "present" result is not a security
audit.

## Windows file organization

`backend/spark_file_organizer.py` implements the file organization agent to the
same standard as the rest of the workspace. It never deletes and never recurses:
a scan touches one directory, top-level plain files only, and groups them into
category folders (Documents, Images, Audio, Video, Archives, Installers, Code,
`_Others`). Unknown extensions fall back to `_Others`.

Scanning is read-only and returns a proposal; no file moves. A plan moves only
for the exact reviewed `plan_hash` and an explicit approval, one directory at a
time. A durable journal is written before the first move, so a failed run rolls
back and an applied run is reversible with `organize_undo`, which refuses to undo
if a file has since reappeared or changed. Name collisions and folders are
skipped, not overwritten. Moving files requires the same session PC autonomy as
other mutating PC actions; scanning and history only need a trusted session. The
root is confined to `SPARK_FILE_ORG_ROOT` (default: the user's home folder), and
whole drives, the home folder as a target, symlinks and relative paths are
rejected.

Not supported deliberately: recursive organization, scheduling, file deletion,
and any move outside the named directory. These are listed as honest gaps in
SAEE rather than approximated.

## File intelligence (read-only)

`backend/spark_file_intelligence.py` reports on an approved directory tree
without changing anything: exact duplicates (SHA-256), **near-duplicates**
(opt-in shingle/Jaccard similarity over text-like files, size-bucketed so it
stays far from O(n²)), large files, old files, temporary files, **redundant
installers** (multiple versions of the same app family) and **duplicate
downloads** (`report (1).pdf` / `notes - copy.txt` style copies), plus a
`reclaimable_bytes` estimate and an aggregated advisory `recommendations` list.
It shares the organizer's allowed root and refuses whole drives and the home
folder as scan targets.

Duplicate detection groups files by byte size first, so only files that share a
size are ever hashed; a directory of unique-size files is effectively not read
beyond its metadata. The walk is bounded (depth 8, 20000 files), never follows
symlinks, and returns `truncated` when a limit is hit. Nothing is written to
disk: results are returned to the caller, not stored. The `files_intelligence_scan`
action only needs a trusted session — it is read-only.

Acting on findings is a separate, approved, journalled operation: moves go
through the file organizer (`organize_*`) and any other change through the PC
access path. This module never deletes anything, and no automatic cleanup is
performed. Recursive organization remains an honest SAEE gap
(`recursive_file_organization`); the near-duplicate and natural-language-search
gaps are now closed.

Natural-language filesystem search (`files_search` action) parses a query into a
machine-readable intent — size thresholds ("larger than 50 mb", "90 bytes"),
age ("older than 3 months", "newer than a week"), extensions (".pdf",
"excel files", "csv") — and free keywords (stopwords dropped). It runs the same
guarded, bounded walk over the approved directory, filters by the parsed intent,
scores substring matches on the name (3) and parent path (1), and returns at
most 100 results with their scores and the parsed intent. Read-only: nothing is
indexed to disk, opened, or modified, and whole-drive/home targets are refused.
An empty result is not an error; a query with no recognisable signal is rejected.

## Security scanning (read-only)

`backend/spark_security_scan.py` is the `security_check` stage made real. It runs
two heuristic layers over text without importing or executing it:

* `scan_secrets` — high-confidence token shapes (AWS, GitHub, Google, Slack,
  OpenAI, Stripe, JWTs, private-key blocks, `password=`/`api_key=` assignments)
  plus a Shannon-entropy check on long literals, with obvious placeholders
  (`changeme`, `example`, `test…`) filtered out.
* `scan_code` — AST checks for `eval`/`exec`/`os.system`/`shell=True`/
  `pickle.loads` and regex checks for hard-coded private IPs and `verify=False`.

`scan_sources` returns findings plus a verdict: **any secret blocks**, code
findings are advisory. This is wired into `Maintenance._validate`, so every
staged repair candidate is scanned before it can be tested or activated — a
credential can never reach the release gate. Findings never include the full
secret, only a redacted prefix, and the verdict carries a stable `signature` for
the ledger. The read-only `security_scan` action (one to sixteen `backend/*.py`
paths) exposes it on demand.

This is a heuristic linter, not a proof: it cannot certify the absence of secrets
or vulnerabilities, and it does not run antivirus or a full SCA. It reduces risk
and says so.

## Environmental self-diagnosis (read-only)

`backend/spark_self_healing.py` covers the §3E self-healing items that are *not*
about source code the engine writes itself — the running environment:

* `check_startup` — required backend modules present and parseable; a missing or
  unparseable core module is a startup failure.
* `check_dependencies` — optional/platform imports (`psutil`, `faiss`,
  `croniter`, …) reported present/absent via `find_spec` only; nothing is
  installed.
* `check_runtime` — Python version floor and the stdlib features the safety code
  relies on (`Path.is_relative_to`, `ast.parse`).
* `check_resources` — RAM/disk headroom against configurable floors, sourced from
  host vitals; low headroom is a warning.
* `check_connectivity` — opt-in DNS/TCP reachability of a fixed, tiny provider
  set. A `probe` function is injected so tests never touch the network; without
  one, connectivity is reported as not-checked.

`diagnose(deep=…)` aggregates these and returns a `healthy` verdict plus a note
that **no repair is performed here**. Repair still flows through the maintenance
and repository approval gates.

`RepairGate` implements §3E's "never repeatedly execute the same failing repair
without new evidence": an identical `(signature, evidence)` attempt is refused
(`identical_repair_without_new_evidence`); a changed evidence digest is new
evidence and is allowed. `repeated_failures()` surfaces signatures attempted more
than once for escalation. State is supplied by the caller (the SAEE ledger), so
the gate is pure and testable.

`disk_forecast(free_gb, used_gb_per_day, horizon_days)` projects free space at a
constant daily growth and warns when the disk is projected to empty within the
horizon — pure arithmetic, used for §5 disk-space forecasting.

These are exposed as read-only actions `self_heal_diagnose` (`deep`),
`self_heal_recover` (replays interrupted rollback journals) and `disk_forecast`.

## Self-optimization profiling (read-only)

`backend/spark_profiler.py` is the §3F measurement half — evidence *before* any
optimization recommendation:

* `ProfileRecorder` collects named timing samples (seconds) and summarises
  `count`/`min`/`mean`/`p50`/`p95`/`max`, so tail latency is visible, not just the
  average. Its clock is injected, so tests are deterministic.
* `profile_callable` runs a callable N times and records each run.
* `import_cost` measures the wall time to import a module in a fresh subprocess
  against the current interpreter — a real SPARK-owned cost. No profiler daemon.
* `compare(name, before, after, tolerance)` is tolerance-gated: a change only
  counts as `improved`/`regressed` when it clears the relative tolerance floor;
  otherwise it is `no_measurable_change`, so noise is never reported as a win.
  The verdict is directly consumable by the SAEE ledger's `record_benchmark`.
* `resource_delta` compares two host-vitals snapshots (RAM/disk) and flags
  meaningful growth.

Everything is read-only and advisory. Acting on a recommendation still flows
through the maintenance and repository approval gates. Exposed as the read-only
actions `profile_import_cost` (`module`, `repeats`) and `profile_compare`
(`name`, `before`, `after`, `tolerance`).

## Specialist agent workforce (§6, shared task interface)

`backend/spark_workforce.py` turns the master prompt's specialist agents into
**logical roles executed by the shared dispatcher** — no new model instance and
no second trust path. Roles are governance, not execution: each role declares an
allowlist of existing engine actions, and `workforce_assign`
(`role`, `action`, `payload`) routes the inner action through the evolution
dispatcher only after the role check, so payload validation, approval gates and
journalling are inherited unchanged.

Roles: `planner` (SAEE discovery/registry), `researcher` (read-only repository
analysis, imports, MCP/REA discovery), `architect`, `developer` (staged
candidates, heal), `tester` (run approved candidate tests), `security_auditor`
(secrets + diagnostics), `repair_agent` (diagnose/rollback/self-heal),
`performance_engineer`, `system_monitor`, `release_manager` (activation review
and rollback).

Safety rules:

* Out-of-scope and unknown roles are refused.
* **No self-approval**: an inner `approved: true` is rejected; real approvals use
  the trusted route (direct, authenticated session actions).
* No nesting: `workforce_assign`/`workforce_roles` cannot be routed by a role.
* Titles whose engines route elsewhere (memory via the intelligence service, MCP
  via voice tools, files via the organizer) are deliberately absent rather than
  given a second path.

`workforce_roles` lists the registry read-only.






## System connectivity classification (old section 10, read-only)

`backend/spark_connectivity.py` classifies every integration the master prompt
names - Graphify, Graphiti, Hermes, REA, Obsidian, VAOS, VYNDI OS, VEDM, GitHub,
Google Drive, Gmail, the LLM providers and the voice/multimodal stack - into the
six required labels: `verified operational`, `partially operational`,
`installed but disconnected`, `not installed`, `failed verification` and
`unknown`.

Static evidence (default report, no processes or network):

* Registration under the host `SPARK_MCP_SERVERS` value; an invalid value marks
  the affected entries `unknown` instead of guessing.
* Successful MCP audit calls within the last 7 days lift a registered service to
  `partially operational`. Nothing is claimed `verified operational` without a
  live probe.
* Local install markers (`graphify-mcp.exe` plus the architecture graph, the
  optional `.venv-graphiti`/`.venv-hermes` environments) separate
  `installed but disconnected` from `not installed`.
* Credential presence for Groq and Gemini drives the provider entries; keys are
  only ever described as configured or missing, never echoed.
* Obsidian reads the configured vault location; a present vault is
  `partially operational` because searches verify themselves when invoked.

The probed report (`deep: true`) runs bounded `mcp_discover` round trips for
each registered MCP service through the existing `Integrations` execute path, so
circuit breakers and the audit trail apply unchanged. Success moves the entry to
`verified operational`; failure marks it `failed verification` with a truncated
message and keeps everything read-only. Probe counts are returned with the
report. From the Command Center UI, probes are opt-in behind a confirmation
checkbox.


## Windows management-agent inventories (old section 5)

`backend/spark_pc_inventory.py` supplies the missing Windows Management Agent
evidence, strictly read-only. Startup entries come from the native registry API
(`HKCU`/`HKLM` Run and RunOnce in both registry views, plus the user and common
Startup folders); the running-process list comes from one fixed, bounded
PowerShell `Get-Process` call - no elevation, no writes, no background polling.

A pure advisory layer combines host vitals, both inventories and the disk
forecast into PC-optimization findings: RAM or disk pressure, resource-heavy
processes and startup load. A protected-process list (csrss, lsass, services,
Explorer, Defender and friends) marks system and security software as
leave-alone; only user-closable applications are suggested, and every finding
states that SPARK closes nothing by itself. Findings are evidentiary text, so
the user acts through the owning application or an explicitly confirmed action
elsewhere.

`pc_startup_inventory`, `pc_process_inventory` and `pc_advisory` are registered
in the evolution dispatcher with empty payloads, so the Command Center's
Windows PC Manager screen can pull each inventory separately without a model
call or any state change.
