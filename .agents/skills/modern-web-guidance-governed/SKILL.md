---
name: modern-web-guidance-governed
description: Apply reviewed Google Chrome modern web guidance to SPARK's Electron and Vite UI, preserving local-first behavior.
---

# Modern Web Guidance — SPARK

Upstream: https://github.com/GoogleChrome/modern-web-guidance (Apache-2.0).
This is an agent-discoverable workflow bridge, not a vendored installation of upstream dependencies.

1. Start by inspecting SPARK's existing React/Vite/Electron UI and browser tests; preserve secure Electron boundaries, offline operation, keyboard support and reduced-motion preferences.
2. In an approved developer shell with a reviewed version-pinned CLI, retrieve relevant Modern Web Guidance rules and run modern-web-guidance legacy-scan . on the repository; review proposed changes before applying.
3. If that CLI is not installed or cannot be qualified, record **HOLD** for a live upstream scan; still use reviewed specifications and existing tests.
4. No unapproved packages, floating-version installs, telemetry, paid API keys or source upload. Do not alter OmniRoute's zero-cost model configuration.
5. Run npm test, npm run build and relevant SPARK browser/Electron tests before merging; local Chromium sessions must remain isolated.
6. The assistant may prepare internal work, but purchase issuance and external communications require founder approval. Guidance never expands tool authority.
