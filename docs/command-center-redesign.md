# Command center redesign

The default Spark screen is now a futuristic command workspace. The graphite and cyan interface replaces the stacked home panel with a persistent navigation rail, screen search, overview, session activity, diagnostic readings, and direct entry into existing tools.

The rail opens missions, document knowledge, memory, capabilities, Skill Forge, upgrade studio, repository intelligence, PC management, health, connections, approvals, history, Workbench, recovery/REA, models, and schedules. Existing workspace actions still use the authenticated socket and existing backend approval rules. VAYU publishing remains available in document knowledge. Experience Library, settings, the voice cockpit, and desktop window controls remain available.

The dashboard uses actual connection state, AI session state, session messages, and the existing host diagnostics. It shows missing readings as a dash. A backend socket connection does not imply an AI session is ready. Diagnostic polling uses the existing local read-only service while the dashboard is visible.

The voice cockpit now uses a conversation column, a separate visualizer, a bottom control dock, and the same surface palette. Modular positioning is retained. Microphone, camera consent, face authentication, confirmations, provider selection, and execution policies are unchanged.

## Verification on 21 October 2026

- Production Vite build passes. The existing large-bundle and outdated Browserslist advisories remain.
- Full JavaScript suite: 103 passed, one optional test skipped.
- Dashboard regression coverage distinguishes backend offline, backend online with AI idle, and AI ready. It verifies diagnostic values and real session messages.
- Chromium preview checks desktop, tablet, and phone layouts, screen navigation, screen search, mobile navigation, cockpit callback, and help. The preview uses the actual production components with an explicitly disconnected socket fixture. No model calls are made.
- Actual Electron launch verified dashboard rendering, navigation to PC Manager, return to overview, voice-cockpit round trip, and opening settings, with no page exceptions.
- The Electron acceptance run displayed an offline core and a pre-existing hand-tracking asset fetch error. It does not qualify connected AI, voice/audio, cameras, devices, or external integrations.

Screenshots are under `docs/evidence/command-center-*.png`. Changes are local source changes; this redesign does not publish, push, or merge a release.

## Consolidation and spatial revision

Following screenshot feedback, the cockpit toolbar now has one workspace-tools launcher and one dashboard return button. Its dock keeps four visible controls: power, microphone, camera, and an expandable device tray. Settings, hand tracking, lights, printers, CAD, and browser remain in that tray. Escape and outside click dismiss it.

The dashboard sidebar now groups tools into Workspace, Build, Evolution, Systems, and Governance. The overview no longer repeats the navigation as shortcut cards or adds a second conversation button. Assistant names in the conversation display as Spark rather than mixing ADA and Spark.

The flat visualizer is replaced by a shared Three.js scene with a lit faceted core, wireframe shell, tilted orbital rings, and particles. Rotation responds to pointer position, and the cockpit core responds to existing audio intensity. The cockpit uses a translucent conversation surface and a perspective floor. Rendering is capped at 30 frames per second, pauses while the document is hidden, respects reduced-motion preferences, caps pixel density, disposes GPU resources, and provides a CSS fallback when WebGL is unavailable. The covered cockpit scene is deactivated while the dashboard is open.

Fresh verification: production build passed; 103 JavaScript tests passed, one optional test skipped. Electron checks confirmed both 3D canvases, grouped navigation, four primary dock controls, six expandable device tools, Escape dismissal, workspace launcher, and dashboard/cockpit navigation, without page exceptions. Evidence: `spatial-dashboard.png`, `spatial-cockpit.png`, and `spatial-device-tray.png`. No microphone, camera, device, or provider acceptance is implied by these UI checks.
