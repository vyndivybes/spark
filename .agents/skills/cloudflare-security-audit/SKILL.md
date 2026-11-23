---
name: cloudflare-security-audit
description: Conduct independent, evidence-based security audits of SPARK's integrations and bridge surfaces under an OS-enforced sandbox.
---

# SPARK external-integration security audit

Upstream: https://github.com/cloudflare/security-audit-skill (MIT).
Use this audited workflow for Cloudflare-connected SPARK bridges and desktop/browser trust boundaries. It is a skill reference, not an installed complete upstream harness.

1. Inventory Electron IPC, browser sessions, websocket binding, local file access, OmniRoute fallbacks, VAOS/VYNDI bridges, credential brokers, AI prompt-injection, and build supply chain.
2. Run reviewed upstream audit tooling only in an OS-enforced **sandbox** without external networking, with sanitized environment, bounded resources and scratch-only writes. Never run destructive probes against SPARK's normal Windows profile.
3. Prepare architecture/coverage records and use the upstream schema validators before reporting findings.
4. Every candidate needs an **independent verifier** who attempts to disprove it; preserve confirmed, needs_validation and rejected verdicts with exact evidence.
5. If sandboxing, verification, installation or the audit evidence is incomplete, keep the audit **HOLD** and relevant leads needs_validation instead of reporting a security PASS.
6. Do not escalate personal PC privileges or bypass founder approval for purchase issuance and external communication.
