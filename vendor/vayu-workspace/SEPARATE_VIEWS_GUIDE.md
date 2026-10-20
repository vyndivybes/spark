# VĀYÚ separate visualization views

Start using `Start.cmd`; use **Visualizations** from the main workspace header, or open `views/index.html` directly under the local server. Each view is now a separate real HTML page. The original neural schema HTML is preserved as the shared rendering engine; no duplicated datasets.

## Pages

- [`views/orbit.html`](views/orbit.html) — **3D Orbit**: A spatial overview of systems, agents, departments and their evidence-linked relationships.
- [`views/circle.html`](views/circle.html) — **Circle**: Compare the structure of systems and related entities around a radial layout.
- [`views/rings.html`](views/rings.html) — **Rings**: Inspect concentric organisational layers and their linked nodes without mixing in other charts.
- [`views/graph.html`](views/graph.html) — **Graph**: Explore the neural dependency graph from system level into the selected node.
- [`views/areas.html`](views/areas.html) — **Areas**: See department and business-domain clusters separately from transactional timelines.
- [`views/links.html`](views/links.html) — **Links**: Inspect the strongest record-to-record and system-to-system relationships.
- [`views/timeline.html`](views/timeline.html) — **Timeline**: Inspect dated evidence and recorded events. Missing dates remain unknown; this is not a live activity feed.
- [`views/matrix.html`](views/matrix.html) — **Matrix**: Compare source and relationship coverage in a structured analytical matrix.
- [`views/holo.html`](views/holo.html) — **Holo Stage**: Use the existing immersive projection stage and inspect individual schema entities.
- [`views/pyramid.html`](views/pyramid.html) — **4-Way Pyramid**: Use the four-face optical reflection projection; a physical reflector is required for holographic presentation.
- [`views/operations.html`](views/operations.html) — **Command Desk**: Manage founder outcomes, owners, due dates and priorities in a dedicated operational workspace. This is not simulated agent activity.
- [`views/analytics.html`](views/analytics.html) — **Analytics & Ledgers**: Work with the existing analytics tabs, capability audit, source imports and record tracing away from the neural visualizations.

## Where is everything else?

- **Founder Desk:** Open the main workspace; operational tasks and priorities are never mixed into the neural timeline.
- **Analytics & intelligence:** Business → Analytics & intelligence contains the 10 data-analytics views plus Capability audit, Source intake, and Ledger trace.
- **Original all-modes studio:** Open `VYNDI_VAOS_Neural_Schema_Gesture_Hologram_v4.html` when you explicitly want the previous combined projection selector.

All ten neural projection pages use the same underlying neural schema snapshot and interactive inspector. The two workspace pages instead open the existing action register and analytics system. A dedicated page's mode is selected by a whitelisted query parameter, and its navigation does not change unrelated pages. Imports and runtime state in separate frames are not shared automatically; keep original source files. Real-time financial metrics, automatic agent execution, and live ledger synchronization remain unconnected.
