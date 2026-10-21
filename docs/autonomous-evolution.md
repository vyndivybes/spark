# SPARK self-evolution (SAEE + REA)

SPARK's **Improve SPARK → Self-Evolution and REA** offers a persisted, revocable founder grant for bounded autonomous upgrades. The grant is stored under the workspace data directory (`saee/autonomy-policy.json`), **not** the Git checkout.

## How to use

1. Update your local SPARK checkout from the verified GitHub branch/merge, without losing local changes, then restart SPARK.
2. In **Improve SPARK**, select **Check autonomy status**.
3. **Enable hourly checks** allows read-only REA catalog discovery and local syntax inspection; no source is uploaded and no code is changed.
4. **Enable autonomous repairs** explicitly allows sharing the selected, bounded SPARK Python source with the already configured AI provider and permits eligible code changes. This invokes local code validation; it is **not** an operating-system sandbox.
5. Optionally enter a goal mentioning a backend module (for example, “Improve spark_task_planner reliability without changing interfaces”) and choose **Queue upgrade**. SPARK will independently analyze its own local checkout, stage a single-file candidate, run existing regression gates, and activate it if they pass. A completed upgrade reports **restart required**.
6. **Run inspection now** invokes one cycle immediately, respecting cooldown and limits. **Emergency stop** disables the grant even while a cycle is running, and prevents further activation after in-flight steps finish. **Cancel queued upgrade** discards an unprocessed goal.

## Autonomous actions

- Read local Python syntax and discover the connected REA MCP tool catalog.
- Without a queued goal, attempt to repair **one eligible Python syntax error** using existing `heal_sources → test_repair_candidate → activate_repair_candidate` gates, if model-source permission is granted.
- With a queued goal and no syntax errors, select **one** eligible existing SPARK backend module by matching the goal to its filename, analyze that module through the existing repository intelligence engine, accept only a **single-file** opportunity, and use the existing staging, regression tests, security scan, rollback journal and post-activation verification.
- Limit checks to once per 60 minutes and automatic successful upgrades to one per UTC day.
- Maintain project-specific SAEE attempt records. Decline changes to authorization, recovery, integration, and security modules.
- Roll back if the post-activation regression gate fails; disable autonomy after rollback.

## Explicit boundaries

- REA MCP **tool calls are not automatically executed**, because a discovered catalog may contain commands that modify arbitrary external targets. Catalog discovery is evidence, not a guarantee of REA readiness.
- No arbitrary shell commands, unreviewed third-party clones, new files, dependency installations, external deployments, billing, or PC-wide modification are authorized by this subsystem.
- The model-generated patch is tested through the existing local regression subprocess. This subprocess has a bounded environment but **is not a hardened OS-level isolation sandbox**. Enable unattended model-source repairs only on a trusted machine and with that risk understood.
- No assurance is made that a passing regression suite proves functionality, reliability or security of a generated patch.
- Source permissions and privacy are separate from the general PC autonomy setting. No personal files, business ledgers or credentials are automatically supplied to the AI model.
- New files, broad redesigns and multi-module upgrades still need a separately governed release workflow. A live backend **restart is not automatic**; code can be on disk while loaded Python modules retain their old versions.

## Testing

Run the repository checks (`npm test`, `npm run build`, `python -m unittest discover -s tests -p 'test_spark*.py'`) and the focused autonomy suite:

```
python -m unittest discover -s tests -p test_spark_auto_evolution.py
```

GitHub CI also runs the intelligence suite on Windows and Linux. A passing CI run verifies code/test behavior, **not** live REA installation or local Windows deployment. The local SPARK interface must be used to enable persisted autonomy.
