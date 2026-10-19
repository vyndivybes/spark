# SPARK → VAOS Jarvis: first read-only integration

The **JARVIS** control on the SPARK cockpit opens a separate, read-only enterprise question panel. It does not share your browser session or give Jarvis access to your PC.

## Configure (Windows)

Set these in the local backend process environment (not in React or Electron):
- `SPARK_JARVIS_URL`: exact HTTPS origin of your VAOS Cloudflare Worker
- `SPARK_JARVIS_DEVICE_ID`: same unique ID as VAOS `VAOS_SPARK_DEVICE_ID`
- `SPARK_JARVIS_TOKEN`: same confidential 32+ character token as Cloudflare secret `VAOS_SPARK_BRIDGE_TOKEN`

On VAOS, explicitly enable `VAOS_SPARK_BRIDGE_CONTROL=read-only-v1`. A token and URL must not be committed. Set process environment variables securely before starting SPARK with `start-spark.ps1`. Never store token in a web page or include it in diagnostics.

SPARK's desktop session token remains separate from the VAOS device secret. The JARVIS panel requires the authenticated local Electron cockpit but **not** a live audio connection.

## Failure behavior

Requests time out after eight seconds and never follow redirects. Missing credentials, offline service, mismatched identities and failed signed business reads show an unavailable/HOLD status rather than fabricated numbers. The read-only bridge never retries business actions. No files, camera frames, microphone streams, shell commands, or secrets are forwarded.

Electron restarts an unexpectedly exited, locally managed Python backend at most twice (1s, 2s). Manual process troubleshooting is required after the budget is exhausted; normal app exit never triggers recovery. This is distinct from SPARK's existing explicit staged source-repair workflow.

## Verification

Run `python -m unittest discover -s tests -p test_spark_jarvis_bridge.py`, `npm test`, and `npm run build`. Confirm the *real* VAOS read-only endpoint with both sides configured before claiming live pairing or deployment. Full enterprise mission execution and voice handoff are later work.
