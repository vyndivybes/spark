# SPARK brain galaxy display

The cockpit now opens with the Neural Atlas graph as its main display. The
239 nodes and 292 links come from the same canonical inventory embedded in
`vendor/vayu-workspace/VAYU-Knowledge-Sphere-Live.html` that the existing
`spark_neural_atlas.py` bridge uses. The display reads IDs, titles, types and
edges, without exporting note bodies. It labels this data as a snapshot,
refreshes the local source every 30 seconds and does not invent graph links
when data is unavailable. Decorative stars are separate from graph nodes.

The scene projects three-dimensional graph positions into Canvas, with a slow
global rotation, rotating type modules, revolving orbital trails, depth-based
parallax and an extruded CSS SPARK wordmark. Labels avoid one another and the
central title; hovering a node shows its name and connection count.

Voice colours correspond to measured FFT bands: amber at 80–300 Hz, green at
300–1500 Hz, cyan at 1.5–5 kHz and violet at 5–10 kHz. Pulses propagate along
the real links using graph-hop delays. Module expansion follows band energy
and contracts as that energy decays. No new voice pulses start while muted.
Idle galaxy motion continues independently of voice input. Reduced-motion
preferences disable rotation, traveling pulses and pointer tilt.

Browser audio uses an AnalyserNode attached to the existing approved AEC
microphone stream. It does not acquire a second microphone or connect raw
input to speakers. Native visualization releases its input stream on mute,
disconnect or cleanup and cancels stale asynchronous capture attempts.

## Verification

- Production build passed. Main JavaScript is about 313 KB, with CAD and
  MediaPipe still deferred. Vite reports its existing deferred CAD size warning
  and stale Browserslist data warning.
- All 118 JavaScript tests passed, including graph topology, frequency-band
  mapping, existing AEC behavior and nonblocking backend startup coverage.
- The installed Electron production renderer loaded the actual Atlas snapshot,
  animated, opened the deferred Knowledge workspace and reported zero renderer
  exceptions. Startup requested no CAD, MediaPipe model or WASM resources.
- An isolated Electron fixture passed actual Chromium FFTs for silent generated
  tones at 187.5, 937.5, 3000 and 7500 Hz. Each tone's expected band dominated.
  The mute result was `[0,0,0,0]`. Pointer movement changed the wordmark angle.
- Final screenshot: `docs/evidence/brain-galaxy-cockpit.png`.
- Synthetic-tone preview: `docs/evidence/brain-galaxy-synthetic-frequencies.png`.
  This preview is test audio, not a recording or a physical microphone test.

The final isolated render readiness measurement was 5.9 seconds under current
host load; an earlier run was 1.6 seconds. These measurements exclude the
PowerShell launcher and AI connection and are not a cold-start guarantee.
The existing user session was not restarted. Physical microphone response,
provider connection and user acceptance of the visual effect remain unverified.
