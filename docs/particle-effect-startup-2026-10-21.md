# Particle effect and startup verification

Reference: https://www.youtube.com/shorts/xKlcRGy8JsQ

Inspected the playing reference through Chrome after the web fetch was throttled.
Observed cyan particles and connecting strands with flowing folds and dark gaps.
Replaced the solid faceted sphere and orbit rings with a procedural Canvas particle
network. This is a recreation of the observed style. Exact visual matching and
user acceptance remain unconfirmed.

## Startup changes

- Electron creates the interface before waiting for backend health. Previously,
  Python startup and the health deadline could hold back the window for 20 seconds.
- Gesture vision imports and model initialization run only when gestures are enabled.
- CAD, diagnostic panels and workspace tools load on demand.
- Production main JavaScript decreased from 1,441,906 bytes to about 305,860 bytes,
  approximately 79 percent smaller. CAD remains a separate large deferred chunk.

## Evidence

- `npm run build` passed. Vite reports a large deferred CAD chunk and stale
  Browserslist data as warnings.
- All 114 JavaScript tests passed.
- `tests/startup-nonblocking.test.cjs` verifies that the cockpit is created even
  when backend health stays offline. Running its startup harness against the
  original committed main process confirmed that no window was created there.
- `tests/fixtures/particle-startup-check.cjs` ran in installed Electron against
  the production build, with external network and hardware access denied.
  Dashboard readiness was 1,522 ms from fixture process initialization in the
  final run. This does not measure the PowerShell launcher or AI readiness.
- Two frame samples differed. Painted pixels stayed between rows 56 and 557
  of the 682-pixel canvas, leaving room for the caption. The test also opened
  the deferred Knowledge workspace, confirmed no startup vision/model/CAD
  requests and recorded zero renderer exceptions.
- Screenshot: `docs/evidence/particle-cockpit.png`.

The production assets were rebuilt locally. The user's existing SPARK session
was not restarted. Voice connection, microphone AEC and full cold-launch time
were not verified by the isolated renderer check.
