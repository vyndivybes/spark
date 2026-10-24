# REA analysis and original app workflow

Implementation updated 24 October 2026. Source and build verification passed; live browser/provider acceptance and activation are pending.

Open **Recovery & REA > REA - understand and rebuild**.

## Analyze an exact target

Select **Existing public website tab** or **Local app package or binary**, enter the exact target, and choose **Analyze selected target automatically**. The existing manual REA catalog and argument controls remain available.

Website analysis uses only REA's advertised `list_browser_targets` and passive `inspect_web_page` operations. It requires one already-open page matching the exact public HTTPS URL and a host-configured `SPARK_REA_CDP_ENDPOINT` using `http://127.0.0.1:PORT`. It does not open/navigate tabs, enable browser debugging, evaluate page scripts, click controls, or collect storage keys/fingerprints. URLs containing credentials, queries/fragments, literal private addresses or local hostnames are refused.

Local artifact analysis defaults to the SPARK repository root. Additional approved roots can be specified by the host through `SPARK_REA_ALLOWED_ROOTS` (a JSON list of absolute folders). The chosen file must be a regular, unlinked package or native binary within those roots, at most 200 MB. Packages use `open_binary` then `inspect_artifact`; native binaries use `open_binary` then `binary_overview`. All installed schemas are validated before the first step. The MCP worker runs the sequence as one queue item, preventing other calls from changing its active target between steps. Unavailable tools/providers and failed steps produce no completed report claim.

The report retains sanitized evidence, coverage limitations and provenance. It is not recovered original source or proof that every feature works. **Add report to searchable knowledge** uses the existing project document index without external synchronization.

## Build an original app

Two supported build paths are available:

- **Original notes recipe:** folders, search, pinning, editing/deletion, bold/italic formatting and local persistence.
- **Blueprint data apps:** one to six entities, each with up to ten text, number, date, boolean or select fields. The first-party renderer supplies forms, searchable record tables, editing/deletion, numeric totals, entity navigation and local persistence. Each entity is bounded to 1,000 records. Supply/edit the JSON directly, or start with the local inventory blueprint; neither requires inference.

Saving a changed blueprint creates a separate candidate with its parent report recorded. Existing reports, apps and their user data are retained. The candidate must then be built explicitly.

**Generate blueprint using verified free model** is optional. It requires `OPENROUTER_API_KEY`, a goal and explicit consent to share up to 6,000 characters of the sanitized report. Before generation, the implementation checks the official OpenRouter catalog for zero prompt, completion and request pricing on the exact `openrouter/free` route. It makes one bounded inference request, refuses incomplete/invalid output, and never retries or selects a paid fallback. The response is a schema-validated data blueprint, not executable HTML/JavaScript/Python. Generation does not change SPARK's live voice provider.

Source: [OpenRouter free-router documentation](https://openrouter.ai/docs/guides/routing/routers/free-router).

## Test and open

**Test in hidden browser** creates a temporary, non-persistent Chromium profile. The fixed behavioral checks cover representative creation/editing, search, persistence/reload and deletion; the notes recipe additionally checks folders, pinning and formatting. These are renderer checks, not full semantic acceptance of a model's proposed app.

**Open tested app** requires matching artifact hashes and successful browser proof. Notes must exactly match the shipped recipe. Blueprint apps must contain the exact shipped renderer (normalizing Windows line endings) with only validated JSON inserted at its data marker. Extra code, URLs, unknown fields and prototype keys are rejected. The app has no Node access, is sandboxed with context isolation, denies permissions/new windows/navigation, and allows requests only to its own app file. Its persistent profile is separate from the test profile. Preview operations have timeouts.

No general native-code generation, arbitrary website reconstruction, external integration, cloud sync, deployment or copied third-party assets are provided by this build path. Unsupported behavior belongs in the blueprint's explicit limitations.

## Voice

Existing governed voice sessions support:

- `reverse engineer website https://example.com/`
- `reverse engineer app ABSOLUTE_PATH`
- `show REA reports`
- `read latest REA report section 1 part 1`
- `build notes from latest REA report`
- `test latest REA app`
- `open latest REA app`

A saved 24-character report ID may replace `latest`. Latest resolves within the current project at execution time. Voice target analysis uses the same target rules and schemas as the dashboard. Model-driven workspace calls must match the owner's actual utterance; tool output cannot authorize a different operation. Broad blueprint generation remains an explicit dashboard action with a sharing-consent control.

Groq's deterministic workbench parser handles these commands directly. The assistant workspace-tool catalog also exposes them in profiles that permit workspace tools. The restricted Gemini cinematic profile is not broadened by this change. Panel narration uses the existing local Windows speech/microphone path in Groq mode, with bounded parts. Existing microphone behavior is preserved.

## Verification and remaining acceptance

- Combined Python workflow, production-routing-seam and expansion tests: 25 passed, including the final missing-key regression.
- Production Vite build: passed, 2,060 modules.
- Full Node suite before the Windows line-ending regression was added: 161 tests, 156 passed, four denied localhost connections (`EACCES`), one skipped.
- Cross-language staging: Python generated a separate synthetic blueprint candidate; Electron's real artifact/hash/renderer verifier accepted it, and renderer JavaScript syntax compiled. This check does not execute a browser or prove live UI behavior.
- Final focused Node verification: 8 passed, including blueprint validation, launch gates, startup compatibility and Windows CRLF/LF interoperability.
- No live model request was made. The current shell does not have an OpenRouter key or REA CDP endpoint configured.
- Real Chromium/Electron, microphone and provider acceptance remain unverified. The earlier browser URL policy rejected local-file previews; no alternate browser path or security-policy bypass was attempted in this continuation. The standalone Electron test previously exited before its smoke script ran. Live tests are still required outside this execution restriction.

Reports/apps use the existing workspace data root under `rea-workflows/<project>/<report ID>`. No restart/activation, commit, push, merge, dependency installation, paid call or browser-debugging permission change was performed. Concurrent owner work was preserved.

