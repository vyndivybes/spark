# OpenJarvis learning integration and Brahma capability check

## What OpenJarvis actually does

Inspected OpenJarvis commit `cf464de1ff13d84dede80eb07e5e45c1d06708ba`.
Its learning subsystem has real trace-based skill discovery, agent configuration
versioning, routing recommendations, optional training and optimization adapters.
This is evidence of learning implementations, not proof of unrestricted autonomous
source rewriting or measurable improvement in a deployed session.

`AgentConfigEvolver` ranks observed agent/tool performance and writes versioned
TOML configs. `LearningOrchestrator` coordinates mining, configuration updates,
optional LoRA training and optional evaluation. Important limitation: in this
revision it writes evolved configurations before evaluation, and the rejection
branch sets result fields without restoring those configurations. Without an
evaluation callback it accepts unconditionally. Spark therefore keeps its existing
tested activation and rollback engines rather than replacing them with this loop.

Source links:
- [Skill discovery](https://github.com/open-jarvis/OpenJarvis/blob/cf464de1ff13d84dede80eb07e5e45c1d06708ba/src/openjarvis/learning/agents/skill_discovery.py)
- [Configuration evolution](https://github.com/open-jarvis/OpenJarvis/blob/cf464de1ff13d84dede80eb07e5e45c1d06708ba/src/openjarvis/learning/agents/agent_evolver.py)
- [Learning orchestration](https://github.com/open-jarvis/OpenJarvis/blob/cf464de1ff13d84dede80eb07e5e45c1d06708ba/src/openjarvis/learning/learning_orchestrator.py)

## Exactly what was copied and connected

Only `skill_discovery.py` was copied, unchanged, into
`backend/vendor/openjarvis_learning/`, together with Apache-2.0 LICENSE and a
PROVENANCE.json containing the upstream commit and SHA-256 checksums. No new
third-party dependency is needed. No upstream root NOTICE exists at that revision.

Spark's original `spark_trace_learning.py` adapts it to project-local persistent
history. The existing generated-tool voice/chat gateway records consecutive tool
executions, including failures, and returns learned workflow suggestions on its
`list` operation. The SAEE ledger also exposes `learned_workflows`.

Storage: `<workspace-data>/trace-learning/<project>.json`, bounded to 500 records.
No tool inputs, outputs, user prompts or account tokens are stored there. A pair
requires at least three observations with at least 80% execution success. Only
currently active tools are suggested by the gateway. Histories stay project-local;
session adjacency resets when a new gateway is created. Repeated pairs are
observations, not independent benchmark tasks or proof of user satisfaction.

Suggestions do not execute tools, infer argument mappings or register executable
macros. Existing Python generation, expected-result testing, repair, registration
and execution remain Spark's implementation. No model weights, full OpenJarvis
runtime, training stack, configuration writer or unrestricted patcher was copied.
Restart Spark to load the Python changes; a running old backend cannot use them.

## Can Brahma reverse engineer websites and apps?

Yes, it contains dedicated integration code, with substantial limits. Inspected
commit `c8d9c0f8f1b14b67baf4c258a15be631793a7381` from the retained source archive:

- `actions/reverse_engineer.py:79`: website route uses Playwright navigation,
  accessibility snapshot text and network request listing; fallback fetches HTML.
  API discovery at lines 141–154 is a URL substring filter, not recovered backend
  source or comprehensive request/response schemas. Non-JSON request listings
  become `{raw: text}` and have no `url` key, so this branch can miss endpoints.
- Website `remake` calls model synthesis with an 8,000-character snapshot and
  detected endpoints, producing a frontend and mock backend. This cannot recover
  the original server, database, secrets or behavior that was never observed.
- Native/Electron route at line 302 dispatches ASAR/directories to REA JavaScript
  analysis, WASM to inspection, PE/native files to binary layout, and named
  functions to decompilation. These are wrappers around an external REA server,
  not a bundled native decompiler. Tool schema compatibility and required engines
  must be verified against the installed REA version.
- The binary branch does not implement a remake generator even though its text
  advertises calling `remake` for Electron modules; it returns analysis again.

[Brahma implementation](https://github.com/titechprabhasolutions/Brahma-Ai-Evo/blob/c8d9c0f8f1b14b67baf4c258a15be631793a7381/actions/reverse_engineer.py)
and [REA wrapper](https://github.com/titechprabhasolutions/Brahma-Ai-Evo/blob/c8d9c0f8f1b14b67baf4c258a15be631793a7381/actions/rea_mcp_client.py).
These are source findings, not an end-to-end installed Brahma acceptance test.
No Brahma code was copied: its personal-use/source-available license differs
from OpenJarvis's Apache-2.0 license.

## Verification

Regression tests exercise discovery thresholds, failures, persistence, project
isolation, actual gateway recording, active-tool filtering and absence of private
inputs/results in stored learning history. Related evolution/provider tests are
run with the existing Spark Python environment. A physical voice session with the
restarted Electron application remains a separate acceptance check.
