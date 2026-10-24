# Connected knowledge in Spark

Restart Spark using `start-spark.ps1 -Desktop` to load the new backend and built UI.
Local preferences already enable Graphiti and Obsidian with the Spark Vault.

Open the workspace Workbench and select **Connected knowledge**.

| Control | What it reads |
| --- | --- |
| Search Graphify code | Local code graph, symbols and source files |
| Search Graphiti history | Extracted facts and entities in the selected project |
| Entity timeline | Recorded facts with validity and invalidation dates |
| Search Obsidian notes | Markdown files in the configured vault |
| Read Obsidian note | A vault-relative path such as `VAOS.md` |
| Graphiti status | Dependencies, credentials and ingested episode counts |
| Extract next Graphiti batch | Up to 12 pending project episodes, bounded to two minutes |

Graphiti extraction and queries use configured Groq and Gemini services.
Extraction sends project text to the providers. Local note search, exports and
Graphify traversal work without sending source text to an inference provider.

The selected project is supplied by Spark. An explicit request for a different
Graphiti project is rejected. The initial knowledge bridge targets `default`.
Select that project to query its imported business references.

## Refreshing connected data

1. In Automatic synchronization, select **Refresh now** to pull available readers.
2. Select **Update connected knowledge** to regenerate the linked notes and stage
   changed records for Graphiti. Automatic pulls also run this local projection.
3. In Connected knowledge, select **Extract next Graphiti batch**. Read
   `episodes_added`, `episodes_failed`, `remaining` and `time_limit_reached`.
   Repeat batches when needed. Failed records remain pending.

The bridge combines the packaged VAYU business inventory, a Graphify architecture
summary, up to 100 original Obsidian notes and retained VAOS Jarvis, Vyndi OS and
VEDM snapshots. Notes include up to 4,000 source characters. Graph episodes are
also bounded to 4,000 characters and mark longer excerpts as truncated.

Generated notes live under `Spark Vault/Spark-Connected/default`.
Open **Spark connected knowledge.md** there in Obsidian and use its links or
Obsidian's graph view. Original notes are preserved. Generated notes are excluded
from bridge ingestion to prevent recursive copies. Source changes create new
pending episodes; unchanged content does not create duplicates. Historical
episodes and old generated notes remain available, so use the index for the
current export and check source dates.

VAOS Jarvis requires its signed-in founder session. Vyndi OS currently exposes
seeded engineering reference data, and VEDM exposes published library metadata.
A failed reader can retain an older cached snapshot; exported notes preserve its
failed state and last successful read. These sources do not constitute a live
business ledger, release approval or a complete account backup.

## Command line

Run from the Spark checkout:

```powershell
.venv/Scripts/python.exe scripts/connect-knowledge.py --project default
.venv-graphiti/Scripts/python.exe scripts/connect-knowledge.py --project default --refresh-graph
.venv-graphiti/Scripts/python.exe scripts/connect-knowledge.py --project default --import-inventory --drain-graph
```

The first command saves the local bridge configuration and exports notes.
The second additionally runs one real extraction batch. Re-running with another
project changes the bridge's automatic target. Existing project history remains.

The third imports the inventory's explicit entities and relationships through
Graphiti's native graph models, using Gemini embeddings. These keep a
`packaged-reference` source label and require no LLM fact extraction. Cached
business responses are imported as dated source records labelled
`cached-business-evidence`, preserving the staged text, reader state and source
limitations. Their graph relationships describe source provenance, not inferred
business approvals. Remaining free-form project notes use Groq's strict JSON
schema extraction. Short provider-specified quota resets are honored once; persistent
quota failures stop the run with the remaining count intact.

Embedding vectors are cached on disk and requests are paced below the free-tier
per-minute limit. The embedded Kuzu database uses a bounded 256 MiB buffer pool;
inventory writes checkpoint in chunks and reuse already stored vectors when
resuming an interrupted import.

Voice examples:

- "Search my Obsidian notes for VAOS"
- "Read my Obsidian note VAOS"
- "What changed in my project?"
- "Ask Jarvis, what is the current workforce status?"

Graphiti facts are model-extracted associations. Check their source episodes and
retain missing-evidence statements and business release holds.
