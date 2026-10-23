# Spark internet access

Spark's Gemini voice and Groq assistant paths expose `web_search` and
`read_web_page`. Search uses Bing's public RSS results and needs no additional
API key. Spark fetches public pages directly and returns text with source URLs.
The existing source cards display the links returned by successful requests.

Try saying "Search the web for the latest Python release" or
"Read https://www.python.org/doc/ and explain what is available."
Restart Spark after installing these changes so its backend loads the tools.
Gemini's minimal diagnostic `voice` profile keeps its original tool-free setup;
the normal `cinematic` profile includes internet tools.

Both providers also expose `inspect_public_github_repo`. It accepts a public
GitHub repository URL or `owner/repository`, then reads GitHub's public API for
metadata, root files and README text without a CLI login. This is an overview;
Spark must read relevant source files before describing implementation details.
Missing README/root listings are reported separately from successful metadata.

`get_connection_status` reports whether the current Spark process has Gmail,
Google Drive, Google Calendar and GitHub adapters in `SPARK_MCP_SERVERS`. It
returns no credentials or account content and performs no OAuth probe.
`configured_unverified` means configuration exists, not that login works.
`not_configured` means the adapter is absent from this launch. A connection in
Codex or another app does not automatically authorize Spark. Account content
reads remain available through the separately configured Workbench adapters,
not through this voice status tool.

`get_dashboard_help` gives both voice providers grounded help for Spark's own
workspace screens. The Capabilities entry explains every visible control under
Build > Capabilities, including the empty calculation-skill state. The Missions
entry resolves both "Missions" and "Autonomous Missions." Spark calls this tool
before answering questions about its own pages.

Repository adoption requests use both tools together. Spark first inspects the
public repository and its license, then explains the Build > Repositories flow:
analyze against a specific goal, review cited opportunities, import license and
dependency evidence, stage one candidate, test and inspect it, and approve its
activation separately. Local-first architecture is not a reason to refuse a
compatible adaptation.

Both tools only read public HTTP and HTTPS resources. They reject local network
addresses, credential-bearing URLs, non-web ports, binary downloads, oversized
responses and private DNS answers. Redirect destinations undergo the same checks.
Requests have a timeout, page text is bounded, and failures return an explicit
unverified result. Search quality and website availability depend on the remote
service. Login-only pages and pages requiring JavaScript are not supported by
this text reader. Retrieved content is treated as evidence, never instructions.

This capability does not enable Google's separate paid Search grounding option.
Normal usage of the already configured AI provider still applies.

Verification: `python -m pytest tests/test_spark_web.py tests/test_spark_assistant_tools.py -q`.
