# Spark 2.0 release plan

Draft scope recorded on 27 October 2026. This document starts the upgrade;
it does not declare the current installation to be version 2.0 or release-ready.
The package and lockfile currently identify the application as 1.0.0.

## Proposed outcome

A reliable personal intelligence workstation with a holographic dashboard,
Spark's own voice, useful connected information, evidence-backed website and
repository analysis, and recoverable local upgrades.

Prioritize completing existing capabilities. Confirm any major additions with
the owner before adding services, dependencies, or new product areas.

## Baseline and release gates

| Area | Existing evidence | Required for 2.0 |
| --- | --- | --- |
| Startup voice | On 26 October, a real opening produced one automatic Gemini narration, 80 non-silent audio buffers, and zero microphone requests. Returning Home did not replay it. | Fresh launch, locked/unlocked behavior, disconnect, cancellation, selected speaker, provider failure, and replay all behave correctly. Reopening the app plays exactly once. |
| Weather and Morning Digest | Coimbatore weather and the 26 October digest were read through Spark's configured voice. Digest acknowledgement is preserved. | Today's dates and observation times are visible and spoken accurately. Missing or stale information is identified. No overlap with an existing conversation. |
| Website intelligence | Igloo page description and relevant search links are retrievable. An isolated JavaScript fixture rendered successfully. Igloo's actual visual interface remains unverified. | Reads clearly distinguish metadata, body text, rendered observations, and unavailable visuals. Relevant citations are returned. Website information cannot instruct privileged actions. A representative dynamic website must pass a real visual inspection before claiming that capability. |
| Repository intelligence | A schedule reliability adaptation and a reviewed Brahma-inspired task retry correction were applied through staged tests and rollback backups. | Repeatable import, source selection, analysis, review, test, activation, and rollback on a controlled reference repository. No automatic success claims for unsupported repositories or empty proposals. |
| Connected knowledge and services | Previous checks cover selected Google snapshots and some local knowledge reads. Registration alone does not establish account or query functionality. | Verify a real read for each configured service. Show the checked time and specific failure or unavailable state. Never label an installed adapter as a successful integration. |
| Dashboard and navigation | Holographic views, motion pause, narrow layouts and reduced motion passed prior focused checks. | Current build has reachable controls, readable status, keyboard access, no clipping on supported window sizes, and no blocking renderer errors. |
| Recovery and release identity | Maintenance candidates use backups, source hashes and staged/installed verification. Automatic promotion has a separate clean-worktree requirement. | Preserve owner edits and data; verify recovery and rollback. Desktop, backend and installer agree on the release version and candidate identity. |
| Installation | Existing Windows packaging configuration is present. | Build and launch the packaged candidate with the intended Python runtime, required assets, and preserved user data. Verify the installed application rather than inferring success from a renderer build. |

## Execution order

1. Confirm the owner’s release scope and establish a current baseline.
2. Repair the core workflows and their directly related failures.
3. Run affected checks, then candidate-wide verification and real desktop acceptance.
4. Align version information and release notes with the verified candidate.
5. Build and verify the local Windows package and recovery procedure.
6. Declare the release ready only when required gates pass; document remaining
   optional capabilities explicitly.

## Working rules

- Preserve all existing local changes. Do not clean, reset, stash, commit, or
  publish them merely to satisfy an upgrade gate.
- Keep account credentials and personal data out of release artifacts and evidence.
- Use separate candidate data and profiles where practical; do not treat a
  candidate fixture as proof that a live account or installed feature works.
- No new subscriptions, paid capabilities, external messages, or publishing are
  implied by the version upgrade.
- Bump the final release number only alongside the qualified candidate, not as
  a substitute for the requested upgrade.

## Current status

The owner selected **complete and verify existing features first** on
27 October 2026. Scope is accepted; baseline verification is starting.
No final release promotion, package version change, or publication has occurred.
