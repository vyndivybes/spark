# Connected workspace upgrade

The 20 October 2026 upgrade adds three connected workflows.

## Publish a project into VAYU

In **Home / Knowledge**, import the permitted documents and publish selected
ones to HOLO. Choose **Publish / refresh VAYU snapshot**. Open the VAYU workspace
and select **Spark project data**. Choose a project, inspect its published notes
in the graph, or use the task table for recorded reminders and agent workloads.
The publication contains bounded excerpts of already published notes and task
metadata. It does not expose the full private knowledge database. Graph lines
mean project membership, not inferred business or semantic relationships.

Publication is manual and labelled with its timestamp. Refresh it after changes.
Projects remain separate. Source removal and unpublishing revoke the export;
refresh an already loaded view to clear its old snapshot. **Remove VAYU snapshot**
revokes the entire selected project export. The original ten business-schema
projection pages still use their reference schema, separate from this data view.

## Turn Jarvis advice into a reviewed PC task

Ask a question in **VAOS Jarvis**, then use **Prepare report task** beneath its
answer. The default draft writes the advisory into a new Markdown file under
`Documents/SPARK/Advisories`. No model request or PC execution happens while
preparing the draft. You can review/edit up to six PC actions, including file
operations, program launches or commands, and use **Stage edited plan**.
Review every displayed step, then choose **Approve and run these steps**.

Approval is bound to the exact saved goal, advice and action plan by its hash.
Changing the draft requires staging and reviewing a new plan. PC autonomy must
be enabled in the authenticated active session. Its existing file backups and
command timeouts apply. Turning autonomy off blocks subsequent steps; an
already-running command may finish or time out. Jarvis advice is data, never
execution permission. This is a local reviewed task workflow, not autonomous
business authority or a remote Jarvis dispatch API.

The task ID, state, plan and results persist in
`%LOCALAPPDATA%/SPARK/workspace/pc-tasks/tasks.sqlite3`. Refresh task history to
inspect prior outcomes. Repeating a run for a completed/failed/interrupted task
returns its saved state without running it again. A task found running after
restart becomes interrupted; it is never automatically replayed. Prepare a new
reviewed task after checking which effects already occurred.

## Cockpit navigation

The toolbar uses a fixed 64-pixel row. Navigation scrolls horizontally when
needed, while window controls remain reachable. Use Tab or the horizontal
scrollbar to reach additional destinations. The Experience Deck stays anchored
below the toolbar and keeps its close control visible while its cards scroll.

## Verification

```powershell
.venv/Scripts/python.exe -m pytest tests/test_workspace_upgrade.py tests/test_vayu_launcher.py tests/test_spark_workbench.py -q
$env:SPARK_TEST_VAYU_UI='1'
$env:SPARK_TEST_JARVIS_UI='1'
$env:SPARK_TEST_DECK_UI='1'
.venv/Scripts/python.exe -m pytest tests/test_vayu_project_ui.py tests/test_jarvis_ui.py tests/test_experience_deck_ui.py -q
npm run build
```

Storage tests use real files and databases, including approval/hash rejection,
project isolation, source revocation, repeated-run idempotency, interrupted
recovery and mid-plan revocation. Chromium checks use a real published project
HTTP service and a fixture for the Jarvis task approval controls. They do not
certify physical hand tracking or remote VAOS business records.
