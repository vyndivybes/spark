---
name: open-code-review-delegate
description: Run scoped Alibaba Open Code Review delegation in SPARK without a separate paid model API.
---

# SPARK Open Code Review — delegated mode only

Upstream: https://github.com/alibaba/open-code-review (Apache-2.0).
The reviewed ocr CLI must be installed separately on an authorized development machine. Delegation needs **no separate API key** for OCR but relies on an already available, authorized host agent/model; native OCR provider mode is not enabled.

1. Inspect the baseline and source changes before reviewing; protect local PC data, browser sessions, private memory, secret settings and user files from LLM egress.
2. Use ocr delegate preview --format json --from main to enumerate changed files and ocr delegate rule --format json --from main <paths...> to resolve review rules. The host agent must then inspect those diffs; the delegation CLI does not perform an LLM review itself.
3. Test Windows-specific command invocation, Electron session isolation, backend authorization and voice/skill forge safety separately from the frontend.
4. If OCR CLI or a permitted host model is unavailable, mark **HOLD**. Run existing deterministic security scans, PR review, npm test and Python tests; do not claim the OCR engine ran.
5. Never silently select a paid fallback model. Keep any approved auto-evolution change on an isolated branch with evidence and rollback.
6. Require founder approval before purchase issuance or external communications; reviewing a plan grants no new permissions.
