# SPARK vs. Brahma AI Evo / Project Ultron — evidence review

**Reviewed:** 2026-11-18
**Scope:** GitHub source-level inspection, not execution of Brahma, REA MCP, or SPARK on the founder's Windows workstation.
**Primary repositories:** `vyndivybes/spark` (`main`); `titechprabhasolutions/Brahma-Ai-Evo` (`main`).
**Disposition:** Independent-design reference only. The upstream licence prohibits distribution, commercial use, and transmission of its source. No Brahma source, templates, prompts, or assets are included here.

## Executive conclusion

SPARK already contains much of the broad Ultron workflow: project-scoped generated Python tools, constrained code skills, AST checks, expected-result tests, activation controls, source repair, rollback, REA MCP bridge and bounded repository comparisons. Starting a second self-evolution framework would duplicate this architecture. The valuable upgrades are **license-safe structural investigation**, **stronger isolation of executable generated code**, **evidence-bound gap identification**, and **observable feature qualifications**.

### Capabilities substantiated in the inspected source

| Brahma / Ultron claim | Reference implementation inspected | Closest SPARK implementation | Finding |
| --- | --- | --- | --- |
| Natural-language skill synthesis | `core/skill_forge.py` calls a synthesizer, assembles a specification, handles repair loops and saves approved output | `backend/spark_python_tools.py`, `backend/spark_code_skills.py`, `backend/spark_evolution.py` | **Present in SPARK in different implementations**; no live model quality measurement in this audit |
| Pre-activation checks | `core/skill_crucible.py` parses AST, checks patterns and runs subprocess cases | `backend/spark_code_skills.py`, `backend/spark_python_tools.py`, `backend/spark_maintenance.py` | **Present; risk remains**: subprocess execution as the OS user is not a hardened OS sandbox |
| Hot registration | `core/dynamic_registry.py` discovers and dispatches stored skills | `backend/spark_python_tools.py` generated-tool gateway and activation policy | **Present in some SPARK interaction modes**; full voice/desktop acceptance pending |
| Exception-driven self-heal | `actions/auto_heal_engine.py` diagnoses failures and describes patch/backup flows | `backend/spark_maintenance.py`, `backend/spark_auto_evolution.py`, `backend/spark_self_healing.py` | **Present with different authorization and recovery policies**; no equivalence proven |
| Audio reactive HUD | `ui.py` and project README | `src/` voice/visual components, `backend/spark_audio_meter.py` | **Partial comparative evidence**; no side-by-side audiovisual test |
| Desktop action orchestration | `actions/` and `main.py` | `backend/server.py`, SPARK PC autonomy and reviewed skills | **Partially present**; elevated OS controls should be separately qualified |
| Memory across sessions | `memory/` | SPARK workspace, project memory, Graphiti/Obsidian links | **Present in SPARK**, but different persistence and privacy semantics |
| Hardware assembly, Android phone proxy, 3D flight globe | `actions/circuit_assembler.py`, `actions/call_assistant.py`, `actions/geospatial_globe.py` per reference docs | No matching end-to-end SPARK acceptance found | **Not verified in SPARK**; not a first-priority Ultron gap |

**Evidence standard:** A class, function, declaration or README claim is **source present**, not **working feature**. For *verified*, require a deterministic test and, where relevant, Windows/UI/provider acceptance on the configured device.

## REA and source-analysis boundary

SPARK's `backend/spark_rea.py` implements bounded, persistent MCP discovery/calls; `electron/rea-evidence.cjs` reads opt-in local REA summaries. The existing `backend/spark_repo_import.py` and `backend/spark_repo_upgrade.py` are the correct mechanisms to inspect Python source, since REA is not a general-purpose Python code execution verifier. Direct REA binary/CDP routines are not required for a public Python repository.

The new `backend/spark_feature_inventory.py` deliberately records only **public symbol names, file paths, counts and parse outcomes**, without importing external modules, executing code, including docstrings or exporting code bodies. `spark_repo_import.import_evidence()` returns this under `python_api`. The imported non-permissive or unknown-license source must not be forwarded to a model by the `analyze_repository` or previously saved `stage_repository_upgrade` flows; there is no consent shortcut for a third-party licence. Local owner-supplied projects are not affected by this imported-reference rule.

This is a narrow protective improvement, not a claim that third-party licensing can be fully classified by a regex. Manual licence review remains necessary even when the heuristic reports permissive.

## Priority upgrades and acceptance criteria

1. **P0 — License-safe comparative analysis (this branch):** Collect bounded offline Python public-symbol inventory. Block model-assisted sharing/staging of imported non-permissive or unclassified source. Tests must confirm no protected source body appears in the `python_api` result or reaches a mocked model.
2. **P1 — Evidence-backed feature matrix:** Pair static public symbols with SPARK's already present code and label each item `source-present`, `tested`, `hardware-hold` or `missing`. Do not infer functionality from matching symbols. Keep first-party design decisions independent of upstream implementation details.
3. **P1 — Generated-code isolation:** SPARK's `spark_python_tools.py` explicitly notes it runs as the local OS user and **not** a security sandbox. Before offering third-party-inspired autonomous code, require a no-network / nonprivileged OS isolation option, per-tool capability grants, resource quotas and explicit review for dependencies and outgoing data.
4. **P2 — Quality gates:** Validate generated skills with seeded independent cases, bounded fuzz tests, subprocess termination, source integrity checks, negative permission tests, and durable rollback.
5. **P2 — Windows live acceptance:** Confirm actual SPARK voice tool invocation, restarts, REA availability, Graphify/Graphiti evidence links, Electron UI visibility and regression status on the user's machine. This review did **not** perform those steps.

## Verification in this change

- `python -m unittest discover -s tests -p test_spark_feature_inventory.py -v` — **6/6 PASS** in isolated Python 3.13 environment.
- Additional repository integration checks are in `tests/test_spark_reference_boundary.py` and require the SPARK repository's full Python test dependencies / CI.
- No Brahma code was executed or copied into SPARK. No production or local Windows deployment was performed.

### Official source links

- Brahma root: https://github.com/titechprabhasolutions/Brahma-Ai-Evo
- Brahma licence: https://github.com/titechprabhasolutions/Brahma-Ai-Evo/blob/main/LICENSE
- Brahma implementation references: `core/skill_forge.py`, `core/skill_crucible.py`, `core/dynamic_registry.py`, `actions/auto_heal_engine.py`
- SPARK: https://github.com/vyndivybes/spark
- Prior SPARK comparison: `docs/repository-feature-audit.md` (2026-10-19).

**Release gate:** A green PR CI run and explicit Windows live acceptance are still required before declaring the new analysis pipeline fully qualified. Do not confuse code review, static inventory or GitHub merge with proof that REA is connected on the founder's PC.
