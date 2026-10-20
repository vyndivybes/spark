# Repository-driven Spark upgrades

In a connected Spark session, open **Knowledge & Skills → Recovery & REA → Learn from a repository**.

1. Enter an absolute path to a local source checkout. Clone remote repositories locally first.
2. Describe the behavior Spark should learn. Optionally enter up to 16 relative reference paths, one per line. Without a selection Spark samples README files, manifests and source files.
3. Choose **Analyze repository with model**. This sends the selected source sample to the configured Groq model and requires `GROQ_API_KEY`.
4. Inspect the summary, sampled source, limitations, source references, proposed Spark files and behavioral acceptance checks.
5. Choose **Generate staged Spark upgrade** for one opportunity. Spark reads the current target files and generates complete replacements. It retains the original source hashes and the repository evidence identity with the candidate.
6. Inspect the replacements, approve local regression tests, then approve activation separately. Activation verifies the candidate again, saves backups and restores originals if validation fails. Restart Spark after activation. Use **Refresh backups → Roll back** to restore a retained upgrade.

Analysis reads source without executing repository code or installing dependencies. It supports text source from multiple languages, but does not promise full understanding of every repository. It inventories at most 5,000 eligible paths across 2,000 directories and reads up to 16 UTF-8 files, 64 KiB each and 192 KiB total. Hidden files, links, common dependency/build directories, and filenames suggesting credentials or settings are excluded. These filters cannot identify every embedded secret. Share only source you intend to send to the model.

Analyses persist per workspace project under `%LOCALAPPDATA%/SPARK/workspace/repository-analyses/` with sampled contents and SHA-256 hashes. A staged upgrade uses that retained sample even if the external checkout changes. Stale Spark targets are rejected before application. The analysis model must cite sampled files and select existing eligible Spark targets; invented references are rejected.

Generated upgrades use the existing maintenance boundary: one to four existing `backend/*.py` files, 64 KiB each. Frontend changes, new files, dependency installation, recovery/authorization changes and automatic restart require a manual upgrade. Generated code runs only after explicit test approval. A temporary test directory is not an operating-system sandbox. Passing the existing regression suite does not independently prove every model-proposed acceptance check; review those checks before activation. The model is instructed to make original adaptations and flag license uncertainty.

The direct REA tool panel remains available for packaged applications and binaries. Source analysis does not claim to have invoked REA or verified runtime behavior.

Backend actions use the existing authenticated, owning-window `workspace_action` route:

| Action | Payload |
| --- | --- |
| `analyze_repository` | `repository`, `goal`, `reference_paths` |
| `list_repository_analyses` | empty object |
| `read_repository_analysis` | `id` |
| `stage_repository_upgrade` | `analysis_id`, zero-based `opportunity` |

Generated candidates use `list_repair_candidates`, `test_repair_candidate`, `activate_repair_candidate` and `rollback_repair`.
