---
name: stitch-design-workflow
description: Review and implement SPARK personal desktop designs through Google Stitch when its authenticated MCP is available, then qualify with Chrome DevTools.
---

# Governed Stitch-to-Chrome workflow

Read `docs/development/stitch-chrome-devtools.md` before using external design services.

1. Preserve product source-of-truth, security boundaries, auth gates, and the existing frontend stack.
2. Check the `stitch` MCP server is authenticated and available. If not, mark Stitch generation **HOLD** rather than fabricate design artifacts. Use the official `google-labs-code/stitch-skills` plugin skills when installed.
3. Prepare a design brief with responsive layouts, accessible focus states, motion reduction, loading/empty/error/HOLD and actual-vs-simulated data distinction.
4. Generate alternatives via Stitch only with approved inputs; inspect all generated code and assets. No automatic deployment of generated layouts.
5. Implement on a short-lived branch; verify the frontend's DOM/console/network and performance using the separate isolated Chrome DevTools MCP, and run project Playwright and unit suites.
6. Founder approval is still required for purchase issuance and external communications; visual changes never bypass those gates.
