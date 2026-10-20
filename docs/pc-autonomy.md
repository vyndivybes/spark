# PC autonomy

**Settings → PC autonomy** lets Spark's active AI session list and read files,
write UTF-8 text, create folders, copy/move files, launch programs, and execute
PowerShell commands. Absolute paths address the PC directly; relative file
paths use your home folder. Commands accept a working directory.

Access runs as your signed-in Windows account. It does not grant administrator
rights or bypass Windows permissions. Spark acts on conversation requests while
running. This is not a scheduler that works indefinitely after Spark is closed.

The setting persists in `backend/settings.json`. It defaults off for new
installations. This user's explicit request authorizes enabling it here.
Enable it, then reconnect voice to advertise the tools to Gemini Live. Groq
uses the same PC tools through local function calling. Disabling the switch
blocks subsequent tool actions immediately, including in an existing session.
An already-running command may finish or reach its timeout.

Only the authenticated, connected session owner can use PC tools. The cockpit
passes its existing workspace token; unrelated browser origins cannot grant
PC access. Typed turns and memory uploads also require session ownership.
Legacy Tool Confirmations continue to govern other tools. The new `pc_action`
tool uses the explicit PC autonomy setting and does not prompt on each action.

Existing files overwritten by `write` or a copy/move destination are backed up
under `%LOCALAPPDATA%/SPARK/workspace/pc-access/backups/<id>/original`.
The accompanying metadata identifies the original path. Restore by copying
that backup to its original path. `actions.jsonl` records action type, outcome,
paths and backup identifiers, without file contents, commands or arguments.
Terminal commands can modify or delete files directly; those changes are not
automatically backed up. Backups remain until you remove them.

Read results and command output go to your selected AI provider to continue
the task. Directory listings return 200 entries at a time; text reads return
24,000 bytes with a continuation offset. Commands default to 30 seconds and
support up to 120 seconds, returning exit status and bounded output. Timed-out
commands have their process tree terminated. Program launches return a PID,
which proves launch only. Groq allows up to eight PC actions per turn.

Verification:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_spark_pc_access.py tests/test_spark_cinematic_tools.py tests/test_spark_live_profile.py tests/test_spark_groq_cloud.py tests/test_spark_groq_vision_desktop.py -q
npm run build
```

The tests use actual temporary files, a real PowerShell command, a nonzero exit,
timeout cleanup, a launched Python process, overwrite backups, immediate
revocation, installed Gemini schema validation, and a simulated Groq tool
response that executes the real file service. Mock provider responses do not
prove live cloud behavior.

Provider contracts follow the official [Gemini Live tool guide](https://ai.google.dev/gemini-api/docs/live-api/tools)
and [Groq local tool calling guide](https://console.groq.com/docs/tool-use/local-tool-calling).
