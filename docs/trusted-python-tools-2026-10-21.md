# Trusted Python tools, live registration and evolution effects

Verified locally on 2026-10-21 (Asia/Calcutta). Changes are saved in the checkout, not committed or pushed.

## Added

- Full Python tools with imports, installed packages, asynchronous functions and HTTP/API access through `run(inputs)`.
- Original model-generated source, explicit expected-result examples, revision persistence, test/reject/activate/deactivate lifecycle and older-revision reactivation.
- One automatic source-repair attempt when a newly generated tool fails its tests. The repair cannot replace the original expected test cases, package requirements or environment declaration.
- A stable `spark_generated_tool` gateway for voice/chat. It lists fresh active tools and their input shapes, forges a missing requested capability, and runs a named tool. Individual generated names do not require provider-schema replacement or an application restart.
- Groq tool-call execution and Gemini Live declaration/dispatch wiring. Existing PC-autonomy calls retain their original path.
- Live generation, testing, repair, registration, execution and failure events. Upgrade Studio contains the full Python panel; a global HUD displays actual events in the cockpit or workspace.
- Voice-reactive edge glow driven by the existing approved voice session. Removed the unconditional second SpeechRecognition listener and corrected Graphify node palette colors.
- Python runtime stop policy, including termination of an owned running tool worker. Background source patching has a separate stop control.
- Fixed Groq response reading: it now consumes fragmented HTTP bodies through EOF under the existing size limit, instead of trying to parse the first received chunk.

## Enabled locally

The workspace Python-tool policy has `enabled=true` and `auto_forge=true`.

Background source evolution has model-assisted changes enabled, a five-minute interval and no daily upgrade cap. Limits are also persisted in a separate file so an older running backend cannot discard them while rewriting its legacy state. The new scheduler and gateway code load after Spark restarts.

Background evolution is **not unrestricted across the whole repository or PC**. It handles detected syntax failures and explicitly queued source goals through the existing selected-backend-file staging, regression tests, activation, health checks and rollback pipeline. Recovery, authorization and runtime-policy code stays protected. It does not invent unrelated source changes when healthy and no goal is queued. REA background activity remains catalog discovery; individual REA operations retain their existing explicit invocation boundary.

## Execution/access model

Full Python is intentionally different from the restricted data-skill interpreter. It executes trusted generated Python with the local OS user's permissions. A timeout, working directory and separate process are **not a filesystem/network security sandbox**; Python code can access files and networks permitted to that Windows user.

Only declared environment names are forwarded in addition to basic process variables. That filtering is process hygiene, not credential confinement against arbitrary Python running as the same user. Known declared credential values are redacted from returned data, and credential-shaped output fields are masked. Do not embed credentials in generated source.

Automatic voice/chat forging activates standard-library/already-installed tools after passing their expected examples. A tool declaring package installation or credential environment access is retained for review in Upgrade Studio before execution. Declared packages are prepared in a per-revision virtual environment; dependencies are not installed into Spark's application environment. Package setup has bounded timeouts and was not exercised against a live package registry in this acceptance run.

Generated examples alone do not prove general correctness. Add independent cases through Revise. Source patches still require their actual regression suite; a model-reported success is not sufficient.

## Acceptance evidence

- The real configured Groq generator invented `import_math_summary`, revision `92a7ee41dc801de31df172df` in the default local project, using Python's math import.
- Its generated examples passed real workers. Independent input n=9 returned factorial 362880 and square root 3.0.
- The real Groq chat tool-call path subsequently invoked that active tool with n=6 and reported the worker's factorial 720 and square root 2.449489742783178. It did not need a registry restart.
- A separate worker test called a local HTTP JSON API through urllib and returned its actual value.
- Tests verify rejection of wrong expected results, automatic repair while preserving expected examples, declared-environment filtering, inactive/disabled execution denial, authorization loss, owned-worker termination, fragmented HTTP responses and background-limit persistence.
- Affected Python suite: 96 passed, 1 skipped, 15 subtests passed. JavaScript suite: 120 passed, 1 skipped. Backend syntax and production build pass. The final small persistence/registry changes were rechecked with their focused suites.
- The panel and animated HUD were visually checked in a labelled browser preview using sample progress events. Screenshot: `docs/evidence/python-tools-progress-preview.png`. The screenshot is not evidence of a live Electron tool operation; real provider execution was separately verified above.
- No new physical microphone conversation or Gemini Live generated-tool turn was performed. Those remain device/provider acceptance checks after reopening Spark.

## Use

Reopen Spark once to load the new backend/UI, then open **Upgrade studio → Python tools**. Load tools/policy to see saved active revisions. New tools created after this initial reload register without further application restarts.

Example voice/chat request: “Create a Python tool using math to calculate factorial and square root, test it, then run it for six.”

For API tools, specify the endpoint, JSON input/output contract, offline fixture payloads for deterministic tests, and any required environment-variable names. Review packages and credential access in the panel when requested.

The YouTube Short could not be retrieved. The implemented effects follow the user's selected behaviors—voice glow, live skill/repair progress and automatic skill creation/execution—rather than a verified frame-for-frame recreation.
