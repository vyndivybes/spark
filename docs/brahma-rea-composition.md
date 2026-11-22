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
