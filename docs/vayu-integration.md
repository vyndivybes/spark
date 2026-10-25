# VAYU workspace in Spark

Open **Experience Deck → VAYU Workspace → Open workspace**. Spark starts a loopback-only Python
server and opens the visualization studio in a sandboxed Electron window. Closing the window stops its server.
Python is the same interpreter configured for Spark through `SPARK_PYTHON`.
Port 4891 must be available. An occupied port produces a launch error.

VAYU now opens directly into one visualization studio. Graph, 3D Orbit, Rings,
and Matrix have quick switches; the All views selector also includes Circle,
Areas, Links, Timeline, Holo Stage, and 4-Way Pyramid. Switching modes retains
the selected source focus and uses the same document and renderer, without
page frames or a visualization catalogue. Details and Data & import open only
when requested. The source graph uses occupied columns and labels small node
sets; zoom buttons operate on the active renderer.

Tools retains the action register, Analytics & Ledgers, business knowledge,
project snapshots, and opt-in hand controls. Existing action stores are unchanged.
Old `/views/*.html` bookmarks redirect to the studio's selected mode or the
corresponding tool. Local HTML, JavaScript, and CSS responses disable caching so
checkout updates do not leave mixed generations of navigation in Electron.

Personal and Business action registers are separate files at
`<Electron userData>/vayu-workspace/workspace-data/{personal,business}.json`.
On Windows, Electron normally places userData under `%APPDATA%/spark`.
These files survive restarts and checkout updates. VAYU backup export/import
remains available. Manual CSV/JSON analytics uploads remain session-only.

The bundled source comes from the user-supplied
`VAYU_Productivity_Workspace_Separate_Views.zip`, dated 19 October 2026.
Its original source and documentation are retained under `vendor/vayu-workspace`.
`scripts/vayu_launcher.py` adapts its HTTP handler; the bundled UI uses the unified studio entry point.
It serves only UI assets and keeps private files outside the static root.
The included MediaPipe package metadata states Apache-2.0; its assets and
metadata are preserved. This import does not assert an open-source license
for the user-provided VAYU application itself.

The original knowledge schema remains a bundled snapshot. The connected
**Spark project data** view now reads explicitly published Spark notes and task
states. In **Home / Knowledge**, choose **Publish / refresh VAYU snapshot**,
then open VAYU and select **Tools → Spark project snapshots**. The view
provides a project membership graph, source inspector, and filtered task table.
Refresh the publication after changes; it is not a background live feed.
Private documents are excluded, and projects never aggregate automatically.
Removing a source document or unpublishing a HOLO note revokes the corresponding
project export. An already loaded view retains its snapshot until refreshed.
Exports are stored under `%LOCALAPPDATA%/SPARK/workspace/vayu-exports` and can be
removed using **Remove VAYU snapshot**. Hand control remains opt-in.

The Experience Deck now groups the three related experiences under one VAYU
Workspace card. **Open workspace** opens VAYU's actions, analytics and business
schema views. **Neural Atlas · notes graph** opens the original Brain Map on
published Spark Markdown notes. **HOLO Deck · hand interaction** opens the
original HOLO engine on those same published notes, with 3D object interaction.
Both note engines use bundled examples when no published collection exists.
The engines remain available in their own windows, preserving their controls
and data. This consolidates navigation; it does not merge VAYU's schema snapshot
or action registers with the Spark notes collection.

Verification:

```powershell
node --test tests/experience-manager.test.cjs vendor/vayu-workspace/tests/data-intelligence.test.cjs
.venv/Scripts/python.exe -m pytest tests/test_vayu_launcher.py -q
npm run build
```

Optional runtime and Chromium checks:

```powershell
$env:SPARK_TEST_VAYU_LAUNCH='1'
node --test tests/experience-manager.test.cjs
$env:SPARK_TEST_VAYU_UI='1'
.venv/Scripts/python.exe -m pytest tests/test_vayu_ui.py -q
```

The Chromium check creates an action, reloads it, opens the dedicated pages,
checks desktop/mobile catalogue overflow, and captures screenshots in
`docs/evidence/vayu-views-*.png`. The manager check uses the real Python server
with a window test double to verify reuse and process shutdown. A physical
webcam and the full installed Electron window still require device acceptance.
