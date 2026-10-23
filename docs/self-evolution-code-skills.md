# Spark self-evolution and REA-backed code skills

The additional full-Python runtime and live voice/chat gateway are documented in [Trusted Python tools](trusted-python-tools-2026-10-21.md). This document describes the separate restricted data-skill runtime.

## What is available

Upgrade Studio now contains **Invent a code skill**. It composes existing repository analysis and REA discovery with a new persistent code-skill registry. The existing source-repair pipeline still stages selected backend replacements, runs regressions in a temporary source copy, and requires activation approval. This addition does not enable background autonomy or expand its protected source scope.

Workflow:

1. Enter a capability goal with expected behavior and edge cases.
2. Optionally choose **Study repository for this goal**, or enter a saved repository analysis ID. Repository text is untrusted evidence. The generator receives bounded design summaries, not copied third-party implementation.
3. For packaged apps, binaries or runtime questions, discover a REA tool and inspect its advertised schema. Choose exact arguments, confirm the operation, and retain the result. Ordinary source repositories use repository analysis instead of REA.
4. Generate an original code candidate, or paste/edit a specification. Generation never activates it.
5. Inspect the source and examples; add independent expected results through **Revise**. Test examples using real bounded worker execution.
6. Activate the tested revision. Run it with JSON inputs. Saved active skills are immediately available through the registry without restarting.
7. To roll back, test and activate an older saved revision. A failed candidate does not replace the active revision.

## Supported code

Code is one `def run(inputs)` function. It can use local assignments, if/else, returns, arithmetic, JSON data structures, indexing, slicing, comparisons, conditional expressions, and bounded list/generator comprehensions. Available pure helpers are len, sum, min, max, round, abs, sorted, all, any, str, int, float, split, join, lower and upper.

This is a restricted Python data-processing subset interpreted from its AST. It does not use Python eval/exec, import generated modules, install dependencies, or provide filesystem/network/device access. External tasks use Spark's existing approved integrations and Upgrade Studio. It is not an unrestricted Python plugin engine or an OS security sandbox.

Workers run in a fresh isolated-mode Python process with a reduced environment, a four-second timeout, 10,000 evaluation steps, 32 KB JSON values, 1,000 comprehension results, and an 8 KB source limit. Credentials are not passed to workers. Skills have a project boundary, source digest, examples, lifecycle state and optional repository/REA provenance. Passing generated examples proves those examples only.

REA calls retain the existing authorized-session boundary. Some REA tools can modify targets: tool discovery does not grant permission to execute them. Retained evidence is bounded and redacted when it resembles credentials; omission counts and limitations are explicit. A partial REA analysis is not full artifact verification.

## Verified on 2026-10-21

- Spark's own REA client connected and discovered 207 tools.
- REA analyzed a selected compiled SparkScreens JavaScript chunk from the built dist artifact without executing that artifact. The bounded summary was retained with redaction/coverage limitations.
- The configured Groq generator invented **upgrade_test_summary**, revision `3b7ea7689d552864ae8be7f6`, in the local default project with REA evidence `1571cf6cef26cfccf2950bb4`.
- Its generated examples passed real workers. Additional checks independently verified an empty list and a mixed three-result list before activation.
- The activated skill returned `{"total":1,"passed":1,"failed":[]}` for one passing result.
- Focused Python verification: 60 passed, 1 skipped, 15 subtests passed. JavaScript suite: 118 passed, 1 skipped. Production build passed.
- The UI build and static render checks pass. The new controls have not been manually exercised in the running Electron window; reopen Spark to load the backend/UI changes.

## Reference and reuse boundary

Brahma AI Evo documents runtime skill creation and testing in its README. Its source-available personal-use license prohibits redistribution and commercial incorporation. Spark's implementation here is original; no Brahma implementation was copied or vendored.

- Reference: https://github.com/titechprabhasolutions/Brahma-Ai-Evo
- License: https://github.com/titechprabhasolutions/Brahma-Ai-Evo/blob/main/LICENSE

No commit, push, merge or deployment was performed for these local changes.
