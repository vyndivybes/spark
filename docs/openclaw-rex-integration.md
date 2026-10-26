# OpenClaw Rex ↔ SPARK

**Location:** SPARK → Capabilities → Agent Runtimes. No additional dashboard. The bridge is optional and makes no changes to the OpenClaw installation, gateway configuration, or SPARK's Gemini defaults.

## Windows activation

On the PC running SPARK, verify these read-only commands:

~~~powershell
openclaw --version
openclaw gateway status --json
openclaw models status --agent rex --json --check
~~~

The gateway previously reported *connected-no-operator-scope*, which is not execution authorization. Grant Rex's required operator scope using OpenClaw's normal authenticated gateway controls. **Do not** open port 18789 to the network or bypass authentication.

Independently verify the model/provider credentials are restricted to **zero-billed free-tier** inference. Set \`SPARK_OPENCLAW_FREE_MODELS\` in SPARK's host process environment to comma-separated exact model IDs that you have verified free. A model identifier alone does **not** guarantee that a Google Gemini project is unbilled. No model is approved by default. Restart SPARK after setting it.

Choose **Check OpenClaw Rex status**, then **Ask Rex** with a harmless prompt and one approved model ID. A successful turn verifies Rex operator authorization; gateway status alone does not. SPARK invokes \`openclaw agent --agent rex --session-key spark-rex --model MODEL --message-file FILE --timeout N --json\` and omits \`--deliver\` and \`--local\`. An explicit model overrides configured fallback routing. Private prompt files are deleted immediately after each turn; no shell interpolates prompt text.

The authenticated owner session is needed to execute Rex. The read-only status action can use SPARK's existing workspace-token gate. Voice supports **"check Rex status"** only, not voice-originated execution. Errors are bounded and do not expose gateway stderr or provider secrets. Ambiguous timeouts must be investigated in OpenClaw before retrying.

## Verification

Run \`python -m unittest tests.test_spark_openclaw_bridge -v\` from the SPARK root. These unit tests mock OpenClaw and cannot certify the live Windows bridge. Complete acceptance with a harmless \`health check\` on the Windows gateway, then confirm a response appears in SPARK. If operator scope or free-model approval is missing, status remains blocked—do not claim deployment complete.
