VAYU PRODUCTIVITY WORKSPACE
18 October 2026

START
Extract this ZIP into a NEW folder. Double-click Start.cmd and keep its window
open. Use the browser tab it opens. Python 3.10 or later is required; no extra
Python packages or administrator privileges are needed. A free loopback port
is chosen automatically, avoiding the previous blocked-port issue.

YOUR DAILY WORKFLOW
1. Founder Desk opens first. Add one real outcome with an owner, next action,
   due date and priority. High-priority unfinished items fill the top-three view.
2. Business sections organise projects, contacts, operations, engineering/ VEDM,
   digital workforce and intelligence. Knowledge references are historical or
   reference architecture, with source/confidence labels. Inspect evidence or
   add a local follow-up; a follow-up never changes the source record.
3. Switch to Personal for career, learning, family, cycling and documents.
   Both spaces start empty. No personal information is inferred or imported.
4. Review open/blocked items daily and completed work weekly. Decision items
   are your planning notes, not an official approval or signing authority.
5. Expand Backups & workspace information to export JSON regularly. Import
   adds new IDs only, retaining existing records. Export each space separately.

SAVING
When started through Start.cmd, your action registers are stored in separate
workspace-data/personal.json and business.json files alongside the app. They
survive browser refreshes, server restarts and different loopback ports. Keep
this whole folder when moving computers. Concurrent edits from another tab
are rejected; reload to see that tab's saved version before editing again.
If you open just the HTML or use a generic static server, the app falls back
to browser storage and displays that limitation. Export before changing the
browser, browser profile, or server port in this fallback mode.
Personal and Business are separate local registers, not separate authenticated
accounts. Anyone with access to your Windows folder/account can read the data.

KNOWLEDGE AND ARCHITECTURE
Explore Knowledge preserves the original three-panel business knowledge view:
239 entities, 292 relationships and 64 source references, search and entity/
source inspector. The distracting enclosing rings remain removed. Architecture
& record stores in the knowledge sidebar opens the detailed supporting schema.
This is snapshot knowledge and reference architecture, not a statement that
all described employees, modules or tables are deployed and connected.
Generative LLM answers and continuous mail/Drive/ledger sync are not activated.
Ask Wiki uses local evidence retrieval. Local actions do not write official
ledgers, assign live digital employees, or send any external messages.

HAND CONTROL
In Explore Knowledge, expand Hand control and Enable hand control. Webcam
permission is opt-in. Local MediaPipe 0.10.21 JS, WASM and model are included.
Point/pinch selects; pinch-drag rotates; two open hands control zoom. Swipe
cycles system filters. Return to Founder Desk stops the camera. Physical
webcam acceptance must be checked on your own Windows device.
MediaPipe Tasks Vision 0.10.21: Apache-2.0 per package metadata. Hand landmark
model: Google's public float16 hand_landmarker model.

VERIFICATION
Browser checks: create/edit/complete, high priorities, Personal/Business
isolation, reload persistence, backup export/import, evidence navigation,
responsive desktop/mobile layout and no JavaScript page errors. Original
knowledge layout, source links, system filtering, intelligence and hand adapter
passed at 1920x1080, 1366x768 and 390x844. Server tests checked restart/port
persistence, conflict rejection, origin protection and private-file access.

ANALYTICS & INTELLIGENCE UPDATE - 19 October 2026
Open Analytics & intelligence in Business, or Analytics in Personal. The
Features tab lists 44 implemented capabilities and source-dependent gaps.

Views: Overview, Trends, Workload, Kanban, Data quality, Explore, Scenarios,
Records, Definitions and Features. Use the data-source control for your
current action register, the business knowledge snapshot, or a CSV upload.
Filters, source records and exports use the same selected population.

Action editing now includes estimated hours, actual hours and dependency
item IDs. Completion timestamps are recorded for new completions. Earlier
Done records without a timestamp stay unknown; historical completion dates
are never inferred from update times. No employee productivity, capacity or
SLA is inferred from a list of employee names in the knowledge graph.

CSV upload is session-only and separate in each workspace: maximum 2 MB,
20,000 data rows and 50 unique columns. Keep your original file. CSV supports
quoted commas, escaped quotes and multiline fields. Numeric analysis expects
plain numbers; date columns expect YYYY-MM-DD or an ISO timestamp. Use
Explore to choose a grouping, measure, aggregation and bar/line/donut view.
Descriptive statistics, Pearson correlation and IQR flags are descriptive;
they do not establish cause or prove that a record is defective.

The backlog scenario requires your throughput assumption. It assumes no new
work and equally sized actions; it is not a statistical forecast. Knowledge
update dates describe the snapshot, not a history of live business activity.
Definitions explains denominators, missing values, date scope and sources.

Export CSV/JSON downloads the filtered source rows; Print view uses the
currently visible analytics view. Source CSV exports prefix formula-like
values for spreadsheet safety. JSON preserves the unmodified record values.
Refresh register rereads local actions; it does not query upstream systems.

The complete Data plugin is not embedded or replicated. Live accounting,
CRM funnels/cohorts, inventory valuation, digital-employee run analytics,
statistical forecasting, causal analysis and scheduled notifications need
appropriate authoritative datasets and/or service integrations. They are
listed as requiring source data, never represented with invented values.
No new subscription, cloud hosting or paid API has been enabled.

Analytics verification: all 10 views opened in Chromium; independently known
KPI counts/shares, filter All/reset and date scope, scenario assumptions,
knowledge integrity, CSV statistics/correlation, chart marks, filtered JSON
export, mobile bounds and cross-space isolation checked. Quoted/multiline
CSV parsing and formula-safe export checked. Existing action save/edit/
complete and backup import/export, source inspection, graph search/filters,
original responsive layouts and hand-control adapter regressions passed.
The Windows physical webcam and browser print dialog require device use.

ENTERPRISE DATA INTELLIGENCE EXTENSION - 19 October 2026
The Business Analytics & intelligence area now has three EXTRA tabs:
- Capability audit: 30 repo-evidenced analytical use cases, source-file links,
  evidence classifications and acceptance gaps. A further 175 possible use cases
  are shown only as opportunity categories, NOT operational modules.
- Source intake: upload up to 12 CSV/JSON exported datasets (each up to 2 MB,
  20,000 rows, 50 columns). Data is held only for this browser session and is
  not backed up or automatically synced; keep your original files.
- Ledger trace: inspect actual imported rows and navigate exactly matching
  foreign-key references between imported source families. Missing target
  files, absent IDs and orphan references are explicitly distinguished.
The original 10 analytics views, 44 local features, knowledge sphere and
optional webcam controls are unchanged.

No external API has been connected. Imported data remains UNVERIFIED_UPLOAD,
with qualification HOLD. The extension does not post accounting entries or
control actual agents, and cannot infer genuine end-to-end ledger completeness
from an isolated file. For precise instructions, sample column names, source
limits, quality classifications and local tests, see DATA_INTEGRATION_GUIDE.md.


SEPARATE VISUALIZATION PAGES - 19 OCTOBER 2026
Open Visualizations from the Founder Desk header or Visualizations pages from
Explore Knowledge. The entry page is views/index.html. There are TEN distinct neural projection
pages plus TWO workspace pages. Each has a dedicated URL and explanation. Views: Orbit, Circle, Rings, Graph,
Areas, Links, Timeline, Matrix, Holo Stage, 4-Way Pyramid, Command Desk and
Analytics & Ledgers. Each has a dedicated page; Command Desk and Analytics
wrap the existing authenticated/local workspace without replicating its records. Old all-modes studio is retained for compatibility.

The projection engine is shared, but each dedicated route explicitly selects
and locks one projection mode. No mode buttons are needed on those pages.
The original source and local analytics records remain unchanged. Source
refresh and live accounting/API connections have NOT been introduced.
