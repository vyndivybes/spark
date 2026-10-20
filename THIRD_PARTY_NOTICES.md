# Third-party notices for SPARK

SPARK integrates the following original, separately maintained projects. Their copyrights and license files remain included in their source repositories; this file supplies additional attribution.

OpenJarvis (https://github.com/open-jarvis/OpenJarvis), inspected at
`2817faa5fe9dbf0612f56be46f77d7c5c38e271c`, is Apache-2.0 licensed. Its strict
action/final envelope, persistent-agent patterns, hybrid ranking and supervised
improvement design informed the independent SPARK intelligence modules. SPARK
does not bundle its unrestricted executors, research runtime or installer. The
upstream license is retained at `docs/licenses/OpenJarvis-APACHE-2.0.txt`.

| Component | Project | License | Integration |
|---|---|---|---|
| ADA V2 | https://github.com/nazirlouis/ada_v2 | MIT | Existing SPARK React/Electron/Python foundation; derived from upstream ADA V2 source. |
| HOLO Gestures | https://github.com/zubair-trabzada/holo-gestures | MIT, copyright 2026 Zubair Trabzada / AI Workshop Studio LLC | Git submodule `vendor/holo-gestures`, fixed at `55626ff00f6b49c649a407ffdb3cad174479c637`. |
| Brain Map | https://github.com/zubair-trabzada/brain-map | MIT, copyright 2026 Zubair Trabzada / AI Workshop | Git submodule `vendor/brain-map`, fixed at `ea25800adaf7b2baf91d255fb108b9dbed1a4786`. |
| MediaPipe Tasks Vision | https://github.com/google-ai-edge/mediapipe | Apache-2.0, Google LLC | Bundled by HOLO upstream and ADA. |
| Three.js | https://github.com/mrdoob/three.js | MIT, three.js authors | Bundled by HOLO upstream and ADA. |

### Excluded source code

VAYU Workspace is also bundled from the user-provided
`VAYU_Productivity_Workspace_Separate_Views.zip` in `vendor/vayu-workspace`.
Its included MediaPipe Tasks Vision 0.10.21 metadata declares Apache-2.0.
The original bundle and metadata are preserved. No open-source license is
asserted for the VAYU application itself. See `docs/vayu-integration.md`.

- [Brahma AI Evo](https://github.com/titechprabhasolutions/Brahma-Ai-Evo): personal-use source-available licence prohibits Git repository mirroring and redistribution; **no source is included**.
- [O.L.L.I.E](https://github.com/nazirlouis/O.L.L.I.E): no redistribution licence verified; **no source is included**.

The use of names here is for source attribution, not an endorsement or trademark licence. All upstream projects remain the property of their respective authors.

The October 2026 Workbench adds original SPARK implementations of generic
office authoring, local agenda/preferences, reviewed routines, MCP service
connections, text utilities, geometry and idealized robot simulation. It does
not include Brahma source, assets or prompts, or O.L.L.I.E source, URDF models
or robot-control drivers. The inspected revisions and remaining differences
are recorded in [the repository feature audit](docs/repository-feature-audit.md).
