# SPARK final commissioning continuation, 2026-10-23 IST

Production readiness remains **HOLD**. Local commissioning is complete to the available configuration and authorization boundaries. Live voice, Google, and several owner sessions remain unaccepted. No provider or hardware success is inferred from UI wiring or fixture tests.

## Subsequent owner-authorized acceptance

The owner then authorized using the existing host credentials, confirmed Gemini billing is disabled, and consented to a brief real microphone/speaker test. The following results supersede the earlier voice/Google/digest HOLD rows below:

- Gemini Live connected using `gemini-3.8-live`, voice profile and browser AEC. Real microphone speech and a response were observed; the owner explicitly confirmed hearing SPARK clearly. The microphone was muted and the session ended afterward. No transcript is included in evidence.
- The RC's Google adapters reused the existing authorized host account, with `--allow-writes` removed and empty `write_tools`. Gmail, Calendar and Drive profile/briefing reads passed. Gmail and Calendar returned empty current windows; Drive returned 25 files. All three runtime snapshots reached `current`, `stale=false`, with recorded successful reads.
- Morning Digest then returned `status=completed`, with all three Google sources current, 25 documents and one triage candidate. No message was sent and no business record was changed.
- A genuine pre-refresh defect was found: registered sources still in `waiting` could produce a completed digest. A regression test first failed for both `waiting` and `unknown`; the classifier now treats both as unavailable. The 24 composition tests, 31 digest tests including wiring, three offline-owner access tests and ten PC boundary tests passed.
- An inherited RC PC-autonomy setting permitted one read-only home-directory listing during the voice session. The audit recorded no writes. The session was stopped. Commissioning now uses `SPARK_SETTINGS_FILE` under the isolated data root, with PC autonomy and configured device discovery disabled. The tracked settings file was restored; active-install settings are not copied over during integration.

The owner subsequently requested a local merge into the active SPARK checkout. That authorizes local source integration and an owned restart; it does not authorize merging GitHub PR #51, deploying, changing billing, or writing live business data. OpenCode model-backed and optional-provider acceptance remains unverified.

Source baseline is `1a36a7b`, offline texture fix `62ebccc`, and startup/recovery fix `687e676`. This report and evidence accompany those changes on `release/openjarvis-reconcile`, draft PR #51. The earlier [capture](5p-final-commissioning-62ebccc.md) remains historical evidence.

## Plan and prepare

Acceptance required an owned isolated desktop, correct cockpit target, real read integrations where configured, bounded local execution, restart/security evidence, relevant regressions and a sanitized branch handover. Original checkout and PIDs 24824/16360 were protected. Only Gemini may be used for a subsequent cloud acceptance run, with verified zero cost. No merge, deployment, billing change, live business write, external message, reset or clean was authorized or performed.

The referenced pasted OpenCode log was retrieved and treated as context. Initial local changes to backend health and startup tests were reviewed, retained, tested and included. The local `opencode.json` remains untracked and excluded from commits.

## Proceed and perform

Port 9223 was owned by the isolated RC, rather than another browser. Its only surviving page was a hidden VEDM business portal. The old harness selected any page when the cockpit was absent, then waited indefinitely on some CDP calls. Logs showed a cockpit shutdown request and backend exit; the portal could keep Electron alive after the cockpit closed. No evidence established an unexpected navigation of the cockpit into VEDM.

The new `scripts/commissioning-target.cjs` requires exactly one page from this checkout's `dist/index.html`, with `sparkBackendPort=8010`. It refuses portals, other checkouts, wrong backend ports and ambiguity. The commissioning CDP transport used this selector and bounded request timeouts.

An immediate stop/relaunch also reproduced Windows singleton lock error 32 and a debugger bind collision. The checked-in `scripts/commissioning-launch.ps1` verifies the recorded executable and isolated profile, protects original PIDs, snapshots descendants, checks creation times before stopping them, waits on process handles, and refuses occupied ports. It uses separate profile/data/notes, an isolated token, explicit empty host MCP catalog, and disables Python bytecode writes. Launch returns promptly; readiness is a separate check. It does not stop foreign port owners.

Slow but live Python startup now reports `still starting` after 20 seconds, with the cockpit available. Real backend exits remain warnings. A missing optional window icon no longer produces the misleading icon error. This does not certify a packaged installer; packaging still generates its icon through the existing build pipeline.

## Actual result matrix

| Area | Result | Evidence and boundary |
| --- | --- | --- |
| Isolated startup / CDP | PASS | Final backend running on loopback 8010; debugger 9223 selects this RC cockpit. Owned restart and three refusal cases exercised. |
| Capability UI | PASS | 16/16 headings and status/read actions completed; 19 expected actions; no failed requests or remote grain requests. Three cold-start connection-refusal log entries were retained by the browser log backlog. |
| Navigation | PASS | 22/22 destinations; zero breadcrumb mismatches, exceptions, log errors or failed requests. |
| Security / persistence | PASS | Final seven checks passed: wrong/missing tokens refused, external OpenCode execution refused, inactive skill and new memory survive restart, SAEE and Python policy disabled. Earlier 52-action security run retained separately. |
| Local noise | PASS | Local CSS texture present; no remote grain reference/request. |
| Graphify isolated copy | PASS, bounded | Real discovery/stats: 2,226 nodes, 4,642 edges, 130 communities. Original and isolated SHA-256 unchanged. Direct RC integration adapter exercised; running desktop intentionally inherits no host registration and reports Graphify unconfigured. |
| VEDM read | PASS, bounded | Published engineering library, seven configurations and ten gates. Read-only reference, not a business ledger, synchronization or release authority. |
| VYNDI OS / VAOS | HOLD | VYNDI OS returned `SIGN_IN_REQUIRED`; VAOS has no signed-in session. No credentials or account state changed. |
| Gmail / Calendar / Drive | HOLD | No authorized RC MCP registrations. Connected Codex apps do not prove SPARK connectivity and were not substituted. |
| Morning Digest | FAIL for live run; HOLD acceptance | Actual `digest_run` completed its handler with `status=failed`; Google sources `not_configured`. An `ok=true` envelope is not a successful digest. |
| Mic / speaker / Gemini voice | HOLD | Three inputs, three outputs, microphone permission granted, audio API available. Gemini key absent, UI says key required. No microphone recording or audible acceptance test performed; owner consent still required. |
| OpenCode | PASS local test executor; HOLD model session | Installed CLI detected. Real scoped `git --version` passed and outside-root execution refused in disposable workspace. No verified free Gemini configuration, so no model-backed CLI run occurred. |
| Python tools | PASS disposable worker; HOLD desktop acceptance | Real reviewed worker tested, activated, returned 42, persisted and deactivated. Disposable policy returned to disabled; desktop policy stayed disabled. This is a process worker, not an OS security sandbox. |
| Agent / SAEE | PASS bounded local checks; HOLD autonomous desktop | CodeAct returned 42 and refused file I/O; SAEE discovery returned a plan without executing. Broad tests cover guarded agent/monitor/routing/evaluation/telemetry behavior. No claim of live autonomous success. |
| Graphiti / Hermes / Obsidian | HOLD | Not configured in this RC; no installations or synthetic providers added. |
| WhatsApp / Slack / GitHub connector / Workbench / PC actions | HOLD | No authenticated live acceptance. GitHub CLI branch/CI access is separate from SPARK's GitHub integration. No external sends or live mutations attempted. |

The old memory marker had a deliberately short 3,600-second TTL and expired before this continuation. Its absence initially failed the persistence harness, as recorded. The original capture contains its creation/expiry timestamps. A new isolated 86,400-second fixture marker was seeded before the final restart and passed lookup afterward; the original inactive skill also survived. No persistence code was changed to conceal the expired fixture.

## Regression evidence

| Check | Actual result |
| --- | --- |
| `node --test --test-concurrency=1` | 142 tests, 141 passed, one skipped, zero failures |
| Focused health/startup/target/noise tests | 7/7 passed |
| Installed SPARK Python 3.11 runtime, `-B -m unittest discover -s tests -p 'test_spark*.py'` | 827 tests, six skipped, zero failures/errors |
| `test_web_agent_safety.py` | 3/3 passed |
| `npm run build` | PASS, 59.08 seconds |
| PowerShell launcher | Parser PASS; actual owned restart PASS; original-PID/data-path/occupied-port refusals PASS |
| Diff whitespace | PASS |

The first broad run used the system interpreter: 828 tests, one failure, four errors and ten skips. Missing pytest, croniter and MCP dependencies caused the failures. The installed SPARK runtime has those dependencies and passed the full run. Both attempts remain recorded; no dependency or assertion was weakened, and nothing was installed into the original environment. Test discovery/import behavior accounts for the different test count.

Remaining non-blocking warnings include FastAPI lifecycle deprecation, old Browserslist data, Vite's CJS API and large CAD chunks, plus resource warnings from existing fixtures. Cold startup can produce transient Socket.IO refusals before binding. Final navigation after connection was clean. These warnings were not suppressed to obtain a pass.

Final resource snapshot had approximately 0.63 GiB free RAM and 14.98 GiB free disk. RAM remains an acceptance risk for voice plus browser and agent workloads. No stress workload was added.

## Persist, GitHub and rollback

Push only the reviewed branch commits to existing draft [PR #51](https://github.com/vyndivybes/spark/pull/51), preserving draft status. The baseline GitHub run `39830447107` passed for `1a36a7b`; it does not validate the continuation. Check the final PR head and Actions results after the push. Final GitHub outcome is delivered with the handover, separately from this pre-push report.

Rollback requires no original checkout restoration because no original source changes were made. Stop only a verified isolated root and descendants, wait for their process handles to exit, and leave original PIDs alone. Preserve isolated data/evidence for review. If reverting source becomes necessary, use normal reviewed revert commits for `687e676` and/or `62ebccc`; do not reset, clean, overwrite or force-push. No rollback was executed against production.

The recovery launcher can be invoked from this checkout with `-IsolationRoot <commission-temp> -PythonPath <installed-python> -Restart`. It never imports host MCP registrations. It does not promise backend readiness at process creation. Verify loopback `/status` and the exact cockpit target afterward. Never remove singleton files or kill a foreign listener to force startup.

## Concrete owner-only acceptance

1. Provide a Gemini credential through the isolated host configuration and independently verify that the selected model and quota are free. Keep paid fallback disabled. Then explicitly consent to one mic/speaker test, speak a harmless phrase, hear the response and verify reconnection. No credential belongs in reports or Git.
2. Authorize read-only Google endpoints in SPARK, including the required `google_daily_briefing` tool for each source. Read one bounded item from Gmail, Calendar and Drive, run Morning Digest, and require `status=completed` with fresh source evidence. Do not send or modify anything.
3. Sign in to VAOS and VYNDI OS within their isolated windows. Repeat governed reads. Preserve VEDM's published-reference and release-HOLD limitations.
4. Once free Gemini routing is established, authorize one OpenCode model run in a disposable repository with a fixed prompt and review its patch and tests. Perform any desktop agent/Python/SAEE acceptance under the real owner gate with a bounded fixture and rollback, then restore disabled policies.
5. Configure optional Graphiti/Hermes/Obsidian and any remaining messaging/connectors only if required. Until then retain explicit HOLD. Recheck RAM under the intended workload before promotion. No production approval, merge or deployment follows automatically from this report.

## Evidence

Current sanitized evidence is in [`evidence/rc-final-20261023/`](evidence/rc-final-20261023/README.md). Tokens, private home paths, email addresses and session identifiers were removed. Two representative current screenshots and the earlier reviewed screenshot set are retained. Raw provider payloads, credentials, full host logs, original graphs and disposable workspaces are excluded.
