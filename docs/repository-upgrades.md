# Repository-driven Spark upgrades

In the desktop workspace, open **Build → Repositories → Learn from a repository**.

Use **Preview source without model** to inspect the sampled files and limits before requesting analysis. Preview works without an API key and does not save an analysis or execute repository code. GitHub previews make a temporary shallow clone, so they require Git and network access. **Load saved analyses** reopens reports for the current workspace; reopening a GitHub report restores its full URL.

1. Enter an absolute path to a local source checkout, **or a public `https://github.com/<owner>/<repo>` URL**. A GitHub URL is cloned for you into a throwaway directory, inspected, then deleted. Clone remote repositories locally first only if you prefer a local path.
2. Describe the behavior Spark should learn. Optionally enter up to 16 relative reference paths, one per line. Without a selection Spark samples README files, manifests and source files.
3. Choose **Analyze repository with model**. This sends the selected source sample to the configured Groq model and requires `GROQ_API_KEY`.
4. Inspect the summary, sampled source, limitations, source references, proposed Spark files and behavioral acceptance checks.
5. Choose **Generate staged Spark upgrade** for one opportunity. Spark sends bounded source excerpts and requests exact-match edits. It reconstructs complete candidate files locally, retaining original source hashes and the repository evidence identity.
6. In **Review staged repository upgrades** on the same screen, inspect the replacements, approve local regression tests, then approve activation separately. **Load staged upgrades** retrieves earlier candidates. Activation requires the active owner session, verifies the candidate again, saves backups and restores originals if validation fails. Restart Spark after activation. Use **Upgrade History** to restore a retained upgrade.

Analysis reads source without executing repository code or installing dependencies. It supports text source from multiple languages, but does not promise full understanding of every repository. It inventories at most 5,000 eligible paths across 2,000 directories and reads up to 16 UTF-8 files, 64 KiB each and 192 KiB total. Hidden files, links, common dependency/build directories, and filenames suggesting credentials or settings are excluded. These filters cannot identify every embedded secret. Share only source you intend to send to the model.

### GitHub URL import

A GitHub URL is handled by `backend/spark_repo_import.py`, which adds what the local path lacks:

- **Shallow, code-execution-free clone.** `git clone --depth 1 --single-branch --no-tags
  --recurse-submodules=no` into a temporary directory, with `core.hooksPath` pointed at the
  null device and Git LFS smudging disabled, so no repository hook, install script, submodule
  or LFS object is ever run. Only `https://github.com/<owner>/<repo>` is accepted; `http`,
  `git@`, non-GitHub hosts and local `file:` URLs are rejected.
- **License reading.** The first `LICENSE`/`COPYING` file found is classified by its text
  (MIT, Apache-2.0, BSD, ISC, MPL, LGPL, GPL, AGPL, Unlicense) and marked `permissive`,
  `weak-copyleft`, `strong-copyleft`, `unknown` or `none`. A missing license is reported as
  all-rights-reserved. This classification is textual and may be wrong — verify before reusing
  code, and never copy implementation whose license forbids the intended use.
- **Dependency map.** `package.json`, `requirements.txt` and `pyproject.toml` are parsed into a
  best-effort dependency inventory. Nothing is installed.
- **Cleanup.** The temporary checkout is deleted even if inspection fails.

Cloning happens outside the maintenance lock; the working directory is removed before the
analysis is stored. The clone itself is not a sandbox for executing code — because no
repository code is executed at all.

Analyses persist per workspace project under `%LOCALAPPDATA%/SPARK/workspace/repository-analyses/` with sampled contents and SHA-256 hashes. A staged upgrade uses that retained sample even if the external checkout changes. Stale Spark targets are rejected before application. The analysis model must cite sampled files and select existing eligible Spark targets; invented references are rejected.

Generated upgrades use the existing maintenance boundary: one to four existing `backend/*.py` files, 64 KiB each. Frontend changes, new files, dependency installation, recovery/authorization changes and automatic restart require a manual upgrade. Generated code runs only after explicit test approval. A temporary test directory is not an operating-system sandbox. Passing the existing regression suite does not independently prove every model-proposed acceptance check; review those checks before activation. The model is instructed to make original adaptations and flag license uncertainty.

The direct REA tool panel remains available for packaged applications and binaries. Source analysis does not claim to have invoked REA or verified runtime behavior.

Backend actions use the existing authenticated, owning-window `workspace_action` route:

| Action | Payload |
| --- | --- |
| `analyze_repository` | `repository`, `goal`, `reference_paths` |
| `preview_repository` | `repository`, `reference_paths` |
| `import_repository` | `url`, `reference_paths` |
| `list_repository_analyses` | empty object |
| `read_repository_analysis` | `id` |
| `stage_repository_upgrade` | `analysis_id`, zero-based `opportunity` |

`analyze_repository` accepts either a local path or a GitHub URL in `repository`. `import_repository` returns only the read-only import evidence (source sample, license verdict, dependency map) without invoking the model.

Generated candidates use `list_repair_candidates`, `test_repair_candidate`, `activate_repair_candidate` and `rollback_repair`.

Patch generation fits the serialized model messages within 9,000 UTF-8 bytes, below the adapter's 10,000-byte cap. Matching target/reference files are sent once. Analysis excerpts favor the goal's identifiers, including functions near the end of a file. The model may return one to four target patches with at most eight edits total and 8,000 bytes of old/new text. Each nonempty anchor must occur exactly once in the original file and appear in the supplied excerpt. Duplicate paths, stale hashes, overlapping edits, unchanged replacements and changes outside the selected scope are rejected before staging. Reconstruction uses original offsets, so earlier replacements cannot alter later anchor matching. Existing Python validation, candidate size limits, isolation tests, clean Git promotion requirements and rollback remain in force.
