# Brahma capability composition — REA 5P stage 1

This proposal catalogs feature inspirations from the four TiTech Prabha Solutions repositories.
It **does not** import, execute, redistribute, or automatically apply their source code.
Use `backend/spark_brahma_composer.py` to emit deterministic review candidates. It is not a live REA MCP call.

## Existing SPARK foundations
- `spark_rea.py`: bounded persistent REA MCP client
- `spark_repo_import.py`: public-repository evidence import; no upstream code execution
- ARKUS: FTS5 and declarative skills (no unrestricted generated code)
- WEB_AGENT_VIEW: ephemeral local Playwright browser
- HOLO: existing gesture/visualizations
- PC autonomy: session-governed computer actions

## License gates (verified against LICENSE files, Nov 23 2026)
- Brahma Sol: README says personal-use source-available, LICENSE contains GPLv3. Resolve conflict before copying.
- Brahma AI Evo: strict personal-only non-distribution license; **do not mirror/copy to this public SPARK repository**.
- Brahma Echo: source-available; modifications for own use permitted but rebranding/republication restricted. Inspiration only until reviewed.
- Modular Chrome OS: MIT; attribution required for substantial copied portions.
- Source patterns discussed here are conceptual and not copied.

## Proposed stages
1. **Plan**: gather read-only REA and static inventory evidence; map source capabilities against existing SPARK.
2. **Prepare**: independent baseline verification, dependency and license review, no-cost budget check, isolated branch.
3. **Proceed**: independently implement reflex router, memory provenance, Android pairing and browser-context permissions; no direct upstream self-patching.
4. **Perform**: unit, integration, security and performance tests on actual Windows/Android devices. Evidence requires real results.
5. **Persist**: retain signed build evidence, provenance, manual review and rollback plan. Do not merge on unverified green claims.

## Run composition unit tests
```sh
python -m unittest discover -s tests -p 'test_spark_brahma_composer.py' -v
```

### Release posture
Proposal-only. No user permissions changed; no runtime integration; no billing configuration; no deployment.

## Implemented stage: authenticated deterministic reflexes

The following workspace actions are wired into `backend/server.py` and share the
existing owner-session and workspace-token authentication checks:

- `brahma_composition` with empty payload: returns the static, licensing-gated
  eight-candidate evidence manifest. This is read-only and available without
  a live voice session to an authenticated desktop workspace.
- `brahma_reflex` with `{"command":"reflex help"}`: lists exact recognized commands.
- `brahma_reflex` with `{"command":"open calculator"}` or
  `{"command":"open notepad"}`: dispatches a fixed executable through the
  **existing** `PcAccess.execute` audit path, but only when the current
  authenticated owner has PC autonomy enabled.

These commands are API-facing; the UI and voice intent router do not yet expose
a dedicated button or spoken-command shortcut. Unknown, injected, multiline,
and non-ASCII inputs fail closed. The launcher only confirms process startup;
it does not claim a usable window is visible.

Tests:
```sh
python -m unittest discover -s tests -p 'test_spark_reflex.py' -v
python -m unittest discover -s tests -p 'test_spark_brahma_composer.py' -v
```

No third-party Brahma source was copied. This does not implement phone pairing,
memory improvement, neural voice, or live REA source analysis yet.

## Phase 2 implementation inventory (still draft)

### Project-scoped explicit memory
- `backend/spark_personal_memory.py`: local SQLite entries with source, confidence,
  creation, expiry and deletion; no implicit chat/clipboard ingestion.
- Authenticated workspace actions: `brahma_memory_list` (empty payload),
  `brahma_memory_remember` (payload `{"body":"..."}`, source forced to
  user_explicit), and `brahma_memory_forget` (`{"id":"<32 hex chars>"}`).
- Data is stored locally outside Git; **not encrypted at rest**. Do not store secrets.
- REA tool discovery: `brahma_rea_discovery` lists configured REA MCP tool names
  through the existing REA client; it does not call those tools or analyze source.

### Android groundwork
- `backend/spark_android_pairing.py`: one-time 120-second pairing invitation,
  owner approval, replay rejection and revocation (process-local only).
  Not exposed over network, with no encrypted transport and no commands granted.
- `android-companion/`: Android Keystore-backed P-256 identity application.
  It is not connected to SPARK and has **no verified APK**. Public keys do not
  prove device possession until challenge/response is implemented.

### Browser context
- Existing local browser now accepts an explicit `inspect` command and emits
  `web_browser_context` to the owning browser session with a bounded title,
  URL and body text; this does not transmit content to a model.
  The local BrowserWindow now provides an explicit **Inspect text** button.
  Its result appears only in that browser view, and is not sent to an AI model.

### Test commands
```sh
python -m unittest discover -s tests -p 'test_spark_personal_memory.py' -v
python -m unittest discover -s tests -p 'test_spark_android_pairing.py' -v
python -m unittest discover -s tests -p 'test_spark_browser_context.py' -v
python -m unittest discover -s tests -p 'test_spark*.py'
```

Voice/avatar changes, live pair transport, full Android control and autonomous
code promotion remain unimplemented. Existing HOLO, voice, Skill Forge and
self-healing must be independently benchmarked before adding replacements.

### Desktop UI
- Workspace -> REA / Brahma upgrades now exposes the candidate report, REA tool
  names, explicit memory creation/list/deletion and fixed Calculator/Notepad reflexes.
- All buttons use the existing `workspace_action` + per-launch workspace token;
  the backend enforces permissions. Browser `Inspect text` is opt-in.
- This UI is not a phone pairing or agent automation interface.

## Voice-first Skill Forge (new candidate workflow)

The original ARKUS declarative Skill Forge remains available under an
**Advanced manual Skill Forge controls** disclosure in Workspace → Skill Forge.

Supported natural-language commands for the existing sandboxed **code skills**:
- "Spark, create skill to convert millimetres to metres accurately"
- "Spark, upgrade skill area_calc to calculate area in square metres"
- "Spark, list skills"
- "Spark, activate tested skill area_calc"

The parser is deterministic and local. Groq speech, Gemini Live utterances and
active-session typed commands route through the same existing owner-authenticated
`voice_workspace_action` boundary. The generator uses the already configured
provider and existing CodeSkills restrictions; it never directly executes an
untrusted source script or imports third-party code. Candidate generation must
return two or more test cases, and the existing test lifecycle runs before a
revision can be activated. It is NOT generalized self-learning, and unsupported
skills must fail with a clear message rather than claiming success.

**Explicit two-turn activation:** A requested upgrade creates and tests a new
candidate but does not activate it. A separate "activate tested skill NAME"
utterance activates only when exactly one tested candidate exists for that name.
If the model changes the requested skill name, activation is withheld. The
original active revision remains available until a qualified replacement is
activated. Failed or unverified inference is not a success result.

**Limits:** Existing built-in skills outside `list_code_skills` cannot be
upgraded through this shortcut. External skill installations, unrestricted
Python/PowerShell, arbitrary application permissions and paid inference fallbacks
are not enabled. Voice/device acceptance still requires a real Windows
microphone and active speech session; model generation can fail on free-tier
limits.

Tests: `python -m unittest discover -s tests -p 'test_spark_skill_voice.py' -v`.
