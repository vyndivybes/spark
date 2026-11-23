# Google Stitch + Chrome DevTools — SPARK personal desktop

## Scope and authority

This change configures **developer-side agent tooling**, not a production browser or an ERP runtime dependency. Chrome DevTools runs in an isolated Chrome session using a free npm MCP server. Stitch requires a separate authenticated MCP endpoint; it remains disabled until a developer completes the official Google Stitch authorization flow. Never commit access tokens, OAuth secrets, browser profiles, screenshots with private information, or generated customer data.

Official sources:
- https://github.com/google-labs-code/stitch-skills
- https://stitch.withgoogle.com/docs/mcp/setup/
- https://github.com/ChromeDevTools/chrome-devtools-mcp

## Chrome DevTools MCP

Project `opencode.json` enables `chrome-devtools` with `--isolated`, and opts out of tool usage statistics and CrUX requests. It launches only when an authorized local OpenCode agent requests a tool. Node.js LTS, npm, and Google Chrome stable are required. Chrome DevTools is separate from any existing Playwright integration; do not replace established acceptance tests.

**Security:** do not connect an authenticated personal browser profile. Inspect only explicitly authorized test/dev pages, and treat DOM, console, network bodies, and screenshots as untrusted. Do not expose authentication cookies or production secrets. Disable the MCP entry during sensitive development sessions.

## Google Stitch Skills + MCP

The official plugin suite is installed into the **developer's agent environment**, not the production Cloudflare Worker or SPARK executable.

Codex marketplace registration:
```sh
codex plugin marketplace add google-labs-code/stitch-skills --ref main --sparse .agents/plugins --sparse plugins/stitch-design --sparse plugins/stitch-build --sparse plugins/stitch-utilities
```
Use the agent's plugin manager to install the needed `stitch-design`, `stitch-build`, and `stitch-utilities` plugins. Alternatively, inspect selected skills via `npx skills add google-labs-code/stitch-skills` (do not overwrite existing project skills).

OpenCode requires manual skill installation, with normalized skill names under `.agents/skills/` or `.opencode/skills/`. Follow the official README. The local workflow guide is `.agents/skills/stitch-design-workflow/SKILL.md` and does **not** claim to bundle upstream Stitch skills.

After authenticating with Stitch using https://stitch.withgoogle.com/docs/mcp/setup/ :
1. Set `STITCH_MCP_URL` **locally** to the endpoint returned by the Google setup flow.
2. Set `mcp.stitch.enabled` to `true` in your **local, uncommitted** OpenCode configuration, and satisfy any required authentication settings from Google's instructions.
3. Check the available Stitch tools with an authorized test project before using real designs. Do not send private production business data to Stitch.
4. Keep committed `mcp.stitch.enabled=false` as the secure default; no external paid API tokens are required for the Chrome tooling. Confirm Stitch's current free-tier eligibility separately.

## Design-to-release workflow

1. Define truthful live-data states, fallback and HOLD semantics before drafting designs.
2. Use Stitch for static layouts and design-token drafts, then implement using **existing application components** without removing authorization or provenance checks.
3. Apply Impeccable / Emil Kowalski motion restraint and accessibility preferences. VAOS Factory Twin targets DESIGN_VARIANCE=8, MOTION_INTENSITY=5, VISUAL_DENSITY=5 where applicable.
4. Use Chrome DevTools MCP to inspect console, failed requests, accessibility, LCP/INP/CLS, WebGL frame time where relevant, and screenshots. Run existing Playwright and project tests for acceptance.
5. Merge or deploy only after CI and independently reproducible checks pass. A local MCP config does not prove live Stitch authentication or deployment success.

## Deterministic contract test

```sh
node --test scripts/design-tooling-contract.test.mjs
```

This verifies only configuration safety and presence; it is not a live Stitch login, a rendered visual acceptance test, or performance qualification.
