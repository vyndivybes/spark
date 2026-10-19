# SPARK → VAOS Jarvis: first read-only integration

The **JARVIS** control on the SPARK cockpit opens a separate, read-only enterprise question panel. It does not share your browser session or give Jarvis access to your PC.

## Configure (Windows)

Set these only in the ignored local `backend/.env` file loaded by the Python backend (not in PowerShell parent environment, React or Electron):
- `SPARK_JARVIS_URL`: exact HTTPS origin of your VAOS Cloudflare Worker
- `SPARK_JARVIS_DEVICE_ID`: same unique ID as VAOS `VAOS_SPARK_DEVICE_ID`
- `SPARK_JARVIS_TOKEN`: same confidential 32+ character token as Cloudflare secret `VAOS_SPARK_BRIDGE_TOKEN`

On VAOS, explicitly enable `VAOS_SPARK_BRIDGE_CONTROL=read-only-v1`. A token and URL must not be committed. Add the variables to `backend/.env` and then start SPARK normally with `start-spark.ps1`. The Electron process must not inherit the VAOS shared secret from its parent environment. Never store token in a web page or include it in diagnostics.

SPARK's desktop session token remains separate from the VAOS device secret. The JARVIS panel requires the authenticated local Electron cockpit but **not** a live audio connection.

## Failure behavior

Requests time out after eight seconds and never follow redirects. Missing credentials, offline service, mismatched identities and failed signed business reads show an unavailable/HOLD status rather than fabricated numbers. The read-only bridge never retries business actions. No files, camera frames, microphone streams, shell commands, or secrets are forwarded.

Electron restarts an unexpectedly exited, locally managed Python backend at most twice (1s, 2s). Manual process troubleshooting is required after the budget is exhausted; normal app exit never triggers recovery. This is distinct from SPARK's existing explicit staged source-repair workflow.

## Verification

Run `python -m unittest discover -s tests -p test_spark_jarvis_bridge.py`, `npm test`, and `npm run build`. Confirm the *real* VAOS read-only endpoint with both sides configured before claiming live pairing or deployment. Full enterprise mission execution and voice handoff are later work.

## Safe Windows acceptance checklist (no paid Cloudflare Builds)

1. Keep VAOS PR #425 and SPARK PR #43 in draft until live pairing is established. The Cloudflare Workers Builds allowance was exhausted on 20 October 2026; GitHub Actions dry-run qualification is separate from that quota. Do not merge or trigger a production release merely to test pairing.
2. Confirm the existing VAOS Worker currently serves `POST /api/spark-bridge`. The production Worker may not have this route yet. A route only present in an unmerged pull request cannot pass a live pairing test.
3. On the Cloudflare account that owns **vaos**, store `VAOS_SPARK_BRIDGE_TOKEN` as an encrypted Worker secret (not in repository variables). Configure `VAOS_SPARK_DEVICE_ID` and enable `VAOS_SPARK_BRIDGE_CONTROL=read-only-v1` only after deployment and governance checks. Keep them disabled beforehand.
4. On Windows, place only `SPARK_JARVIS_URL`, `SPARK_JARVIS_DEVICE_ID` and `SPARK_JARVIS_TOKEN` in ignored `C:\\Users\\ASUS\\spark\\backend\\.env`. `SPARK_JARVIS_URL` is the HTTPS **origin** obtained from the existing Cloudflare Worker Visit link, not an invented URL or the endpoint path. Keep the Worker token out of GitHub Actions, ChatGPT, Electron, and PowerShell parent process variables.
5. From PowerShell, after obtaining the same value on both sides:
   ```powershell
   cd C:\Users\ASUS\spark
   & .\.venv\Scripts\python.exe scripts\spark_jarvis_preflight.py --check
   & .\.venv\Scripts\python.exe scripts\spark_jarvis_preflight.py --probe
   ```
   `--check` is entirely offline. `--probe` sends exactly one harmless greeting over HTTPS, checks the read-only response contract and prints no secrets or enterprise records. Its PASS proves only endpoint reachability and device authentication, **not** that signed VYNDI business sources are functioning.
6. Verify a separately authorized, bounded VYNDI inventory/mission **read** with observed-source evidence before releasing. A HOLD response is an honest failure of source qualification, not proof of zero records.

If the Cloudflare connected app reports 403 on Worker settings or secrets, its permission grants are missing `workers-scripts.read` (or suitable Workers Scripts permissions). ChatGPT identity/account listing alone does not grant Worker access. Reconnect with a suitable scope or carry out these configuration steps directly in the Cloudflare dashboard. Never paste the bridge secret into a chat.

**Rollback / revoke:** remove `VAOS_SPARK_BRIDGE_CONTROL`, rotate the encrypted Worker secret, and remove the local SPARK Jarvis lines from `backend/.env`. Leave the existing production Worker and its other bindings intact.
