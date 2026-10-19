# Repository feature audit

Inspected on 19 October 2026. The malformed input links resolve to the three
repositories below. Existing local audit checkouts were fetched from their
official remotes. Analysis used source trees and Python AST inventories; none
of the upstream applications, hardware drivers or startup scripts were executed.
REA's skill routes complete source repositories to normal source analysis.
Existing REA static summaries were not treated as runtime feature proof.

| Repository | Inspected remote commit | Relationship to Spark |
|---|---|---|
| [ADA V2](https://github.com/nazirlouis/ada_v2) | `d005af742fc5c604074b8b92bd9a223d7fca7447` | MIT-licensed foundation already integrated. |
| [Brahma AI Evo](https://github.com/titechprabhasolutions/Brahma-Ai-Evo) | `c8d9c0f8f1b14b67baf4c258a15be631793a7381` | Functional reference only; no upstream source, assets or prompts copied. |
| [O.L.L.I.E](https://github.com/nazirlouis/O.L.L.I.E) | `abf7f49b2871554af5c5c7e7d33176a774d8e3cc` | Functional reference only; no upstream robot code, models or assets copied. |

These statuses describe implemented code and the verification listed below.
They do not assert full parity with another application or its advertised claims.

## ADA V2 comparison

| Source capability | Source evidence | Spark status |
|---|---|---|
| Native voice and interruption | `backend/ada.py` | Present; Spark also has an explicit Groq path. |
| CAD generation, refinement and STL preview | `backend/cad_agent.py`, `src/` CAD components | Present. |
| Slicing and Moonraker/OctoPrint printing | `backend/printer_agent.py` | Present; physical printer acceptance depends on the user's equipment. |
| Browser agent | `backend/web_agent.py` | Present, with additional scoped browser sessions. |
| Face authentication and hand gestures | `backend/authenticator.py`, React hand tracking | Present. |
| Kasa discovery and control | `backend/kasa_agent.py` | Present. |
| Project context, files and chat | `backend/project_manager.py`, `backend/tools.py` | Present; Spark preserves default-project history and has indexed knowledge. |

No missing ADA feature family was established by this inspection. This does
not certify every upstream hardware or provider path on this Windows device.

## Brahma comparison

| Capability and source evidence | Spark result |
|---|---|
| Word/report authoring: `actions/docx_tools.py` | Added original structured DOCX authoring and optional Groq content generation. |
| Spreadsheets: `actions/office_builder.py` | Added original XLSX creation with multiple sheets, explicit local range formulas, column charts and header styling. Formula-looking input strings remain literal text. |
| Presentations: `actions/office_builder.py` | Added original PPTX creation with title/content slides and speaker notes. Downloadable internet templates and brand matching are not implemented. |
| PDF suite: `actions/pdf_tools.py` | Added PDF creation, import, merge, page extraction and text extraction. General Office-to-PDF conversion and OCR are not implemented. |
| User memory: `memory/memory_manager.py`, `core/memory_cortex.py` | Added explicit project-scoped preference memory, listing and removal. Groq voice can save/recall it locally. Automatic inference of preferences and default cloud prompt injection are not enabled. |
| Reminders/calendar: `actions/reminder.py`, `actions/calendar_scheduler.py` | Added durable timezone-aware local agenda, completion, overdue catch-up and visible reminders while the project is connected. No OS wakeup or cloud calendar sync is claimed. |
| Multi-step tasks: `agent/planner.py`, `agent/executor.py`, `core/omni_planner.py` | Connected durable reviewed routines to actual system-status, skill and allowlisted app executors. Per-step approval, results, timing and audit history are visible. Interrupted side effects are not replayed. Arbitrary computer plans remain unavailable. |
| Execution tracker: `ui.py`, `core/execution_reflection.py` | Added actual execution status and parameter/result inspection. This displays tool evidence, not hidden model reasoning. |
| Spotify and workspace services: `actions/spotify_controller.py`, `actions/google_workspace_mcp.py` | Added a general host-configured stdio MCP hub with discovery, schema validation, persistent sessions and explicit calls. Provider servers, OAuth and user credentials must be configured and tested separately. No Spotify playback or mail/calendar account acceptance was performed. |
| Tuya/Home Assistant: `smart_home/` | Existing Kasa remains. A trusted MCP bridge can now be configured through the service hub; direct Tuya/HA provider adapters are not implemented or tested. |
| Clipboard processing: `actions/clipboard_processor.py`, `core/clipboard_sentry.py` | Added manual clipboard read/copy, JSON formatting, trimming, case conversion and statistics. No clipboard watcher. |
| Screen context: `actions/screen_processor.py` | Added selected screenshot/image analysis through the existing opt-in Groq vision route. No background capture, screen streaming or new default image uploads. |
| Globe/routes/radar: `actions/geospatial_globe.py`, `core/radar_hud.py` | Added independent offline great-circle distance and coordinate plotting. Live flights, street navigation, POIs, weather radar and a textured 3D globe remain unimplemented. |
| Self-healing and skill creation: `actions/auto_heal_engine.py`, `core/skill_forge.py` | Prior Spark work already supplies user-started source repair, staged/live tests, durable rollback and declarative calculation skills. Continuous self-patching and arbitrary executable skill hot-loading remain unavailable. |
| REA integration: `actions/rea_mcp_client.py`, `actions/reverse_engineer.py` | Prior Spark work already supplies direct REA MCP discovery and calls. No automatic binary reconstruction claim. |
| System diagnostics: `actions/system_diagnostics_mcp.py` | Existing Spark CPU/RAM/storage/battery snapshots and safe diagnostic export. Process termination, freezing, power changes and global window manipulation were not added. |
| Study, gaming and flow-state tools: `core/study_guard.py`, `core/game_sentinel.py`, `core/flowstate.py` | Existing focus timer retained. Application surveillance/blocking, automated game installation and workspace restoration remain unimplemented. |
| Network sentry and disk cleaner: `core/net_sentinel.py`, `core/space_cleaner.py` | Traffic inspection, connection termination and bulk file cleanup remain unimplemented. |
| Circuit assembler: `actions/circuit_assembler.py` | Not implemented. No generated wiring or firmware is presented as electrically verified. |
| Phone gateway and call proxy: `brahma_connect/`, `actions/call_assistant.py` | Existing Spark Android Health Connect import retained. Pairing, SMS, location sync, accessibility control and call interception are not implemented. |
| Meeting capture, fitness/food tracking, social messaging, Discord, shopping, image generation | Not implemented. These require additional feature scope, permissions, provider/account setup, and acceptance beyond this desktop bundle. Existing browser tools and public lookups do not establish parity. |

## O.L.L.I.E comparison

| Capability and source evidence | Spark result |
|---|---|
| FK/IK and action sequences: `ollie_ik_solver.py`, `ollie_sequence_manager.py` | Added an original idealized 3-joint arm simulator with configurable link lengths, Cartesian targets, move/delay/gripper steps, playback and unreachable-target rejection. This is not O.L.L.I.E's six-axis robot model. |
| CAN/ODrive control and telemetry: `ollie_controller.py`, `start_can.py` | Not implemented. No physical motors were discovered, engaged or moved. |
| Collision checks and URDF simulation: `ollie_ik_solver.py`, `ollie_urdf/` | Not implemented; no models copied. |
| RealSense depth, ChArUco calibration and segmentation/tracking: `ollie_vision.py`, `ollie_calibration.py`, `ollie_tracker.py` | Not implemented. Requires camera hardware, calibration targets, model/runtime dependencies and independent validation. |
| AI robot actions: `ollie_brain.py`, `ollie_ai_manager.py` | Not connected to physical execution. Spark's reviewed routines and simulator do not imply calibrated autonomous grasping. |

## Implementation and validation

New modules: `spark_productivity.py`, `spark_office.py`, `spark_robotics.py`,
`spark_integrations.py`, `spark_workbench.py`, `spark_workbench_voice.py`.
The UI is **Knowledge / Skills → Workbench**. Existing owner/authentication
checks apply to every new socket action. Office artifacts use opaque IDs in
project-scoped local storage. Service launch commands and credentials can only
come from host configuration, never socket arguments.

Regression coverage exercises actual generated file formats, PDF round trips,
formula rejection, project isolation, durable agenda/routines, denied and failed
steps, interrupted-action handling, pure geometry and a real stdio MCP fixture.
Separate UI acceptance uses a temporary workspace and the actual production
socket handler, without launching microphones or devices. Hardware and
third-party account workflows remain unverified as stated above.

### Verification record

Prior Workbench verification, before the OpenJarvis integration (current results
are in `intelligence-verification.md`):

- Python regression suite: 171 tests run, 170 passed, one skipped.
- JavaScript suite: all 86 tests passed. Production Vite build passed; its
  existing bundle-size advisory remains.
- Live isolated UI: saved a preference, created and downloaded a DOCX, reopened
  the downloaded file with `python-docx`, completed a reviewed system-status
  routine, and rendered the arm simulation with real backend-generated frames.
- Live configured Groq model: generated an original kickoff brief through
  `generate_office`; the resulting DOCX reopened with readable paragraphs.
- Actual Socket.IO transport: an overdue reminder appeared in `due_agenda`,
  completing it removed it from that result, and a downloaded PDF arrived as
  valid binary data.
- The browser automation service timed out during the final notification UI
  check. Visible reminder toast behavior and the final summary-text polish
  therefore still need desktop acceptance. Hardware, external service accounts,
  screenshot vision-provider access and microphone voice acceptance were not
  exercised in this change.

For isolated UI acceptance after `npm run build`, run
`tests/fixtures/workbench_ui_server.py` with Spark's `.venv` Python. It bundles
only the real workbench components, uses a temporary project store, and serves
`/preview` on loopback port 8123, or `SPARK_TEST_PORT`. Its test session never
initializes the production microphone, printer discovery or face camera.
