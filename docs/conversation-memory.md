# Conversation memory

Spark saves conversations in `projects/<project>/chat_history.jsonl` under the
application root. The active project keeps its own history. Restarting Spark
preserves these files. Switching projects keeps their conversations separate.

Spark automatically restores up to forty recent messages within a 24,000
character context budget. This includes both sides of the conversation, so
"continue where we left off" has the discussion available without a topic
search. Gemini restores it silently on fresh connections and reconnects;
Groq reloads it before each turn. Long typed messages are saved in full,
including their endings, and multiline dialogue keeps its original speaker.
The full log stays on disk when older messages leave the provider context.

Explicitly requested details are stored separately without expiry and are loaded
alongside recent dialogue. For example, say "Remember my name is Shyam".
Gemini uses `remember_detail` and confirms only after a successful local write.
Groq handles explicit name/save requests locally. Correcting a saved name
replaces the `user-name` detail. These details remain scoped to the active project.
Earlier assistant statements claiming memory is session-only are outdated.

Spark previously restored only twelve recent messages, reduced to six on Groq.
Groq also emitted transcripts without saving them. Gemini's default cinematic
configuration did not request input/output transcripts, so spoken exchanges
could be absent from the log.

Conversation recall now indexes existing JSONL logs in a local SQLite FTS5 file
beside each log. It indexes new entries incrementally, without expiring older
entries. Names, incidents and discussion topics can be retrieved after restart
and beyond the recent-message window. Results include dates, speakers and
source IDs, with nearby exchanges for context. The original log is retained.

Groq saves user turns before inference and replies before speech playback.
Camera observations and local knowledge search excerpts retain their existing
exclusion from cloud conversation history.
Relevant older excerpts accompany normal chat, PC autonomy and generated-tool
requests. Gemini's cinematic, cinematic_tools, cinematic_search and full
sessions request transcripts and expose the read-only `recall_conversations`
tool. Typed Gemini questions also receive relevant excerpts automatically.
The diagnostic `voice` profile retains its minimal tool-free handshake.

Restart Spark's backend and reconnect voice to load these changes. Ask, for
example, "Who is Ananya?" or "What did we discuss about the studio flood?"
Names and topic words must match saved text. This is local text retrieval;
it does not recognize faces, resolve aliases or guarantee semantic recall.
The selected cloud provider receives relevant excerpts when answering.

Conversations that were never saved, were deleted, or belong to another project
cannot be recalled from this index. No fabricated summaries or guessed facts
are added. Later corrections remain visible alongside earlier statements.

Verification:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_spark_conversation_memory.py tests/test_persistent_conversation.py tests/test_spark_groq_cloud.py tests/test_spark_live_profile.py -q
```
