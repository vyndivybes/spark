# VAOS Jarvis connection

Open **Experience Deck → VAOS Jarvis → Open VAOS / sign in**. Sign in to your
founder account in the isolated VAOS window, return to Spark, refresh the
connection, and ask a question. The portal session persists in a dedicated
Electron partition. **Disconnect VAOS** removes that partition's saved session
and closes the portal window. Other browser sessions are unchanged.

During voice, say **“Ask Jarvis, what is the current workforce status?”**.
Gemini has the `ask_vaos_jarvis` function; Groq routes the explicit Ask/Consult
Jarvis phrase locally. The Workbench Services list also exposes `vaos-jarvis`
through the same fixed advisory adapter. The adapter uses Electron's session,
not an independently deployed MCP endpoint. A configured bridge or a stored
cookie does not establish that the current founder session is valid. Every
question is checked by VAOS.

The default portal is `https://vaos.vayushastr.workers.dev`, identified in the
repository's deployment documentation. The host operator can set
`SPARK_VAOS_URL` to another HTTPS origin before starting Spark.
The source contract was verified against
[`vyndivybes/vaos` at `06bdb059d01b6ea85b985f133db55041ad1f2bbd`](https://github.com/vyndivybes/vaos/tree/06bdb059d01b6ea85b985f133db55041ad1f2bbd).
No VAOS source was copied into Spark and no remote deployment was changed.

Requests use `GET /api/adaptive-intelligence?q=...`, with a question of 5–300
characters. VAOS requires its founder session and commissioned read-only
intelligence. It can return 401 for expired authentication, 403 for denied
identity, 409 for an uncommissioned service, or source-data holds. Spark
preserves advisory answers and holds; it does not treat them as execution
authority. VAOS business writes and agent dispatch are not part of this API.
Local PC autonomy does not change VAOS business authority.

The remote window has Node disabled, context isolation and sandboxing enabled.
Its cookies stay in Electron's isolated session. Python talks to an ephemeral,
loopback-only bridge authenticated with the existing per-launch workspace
token. The bridge exposes only a fixed advisory question route. It never
returns cookies, passwords, credentials or arbitrary remote API access.
Questions go to VAOS; voice tool results also go to the active AI provider.

Tests:

```powershell
node --test tests/jarvis-bridge.test.cjs
.venv/Scripts/python.exe -m pytest tests/test_spark_jarvis.py tests/test_spark_pc_access.py tests/test_spark_workbench.py -q
$env:SPARK_TEST_JARVIS_UI='1'
.venv/Scripts/python.exe -m pytest tests/test_jarvis_ui.py -q
npm run build
```

The installed Electron cookie check is `tests/fixtures/jarvis-electron-check.cjs`.
It uses a synthetic local cookie and a real Chromium session fetch. Unit and
UI fixtures prove transport, isolation, errors, routing, rendered answers and
mobile fit. A successful live business answer still requires founder sign-in
and available source evidence on VAOS.
