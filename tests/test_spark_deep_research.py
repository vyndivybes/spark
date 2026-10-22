"""Capability 05 — Deep research offline acceptance.

Sources are injectable fake corpora with realistic documents; no network,
LLM call or credential is involved.
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_workspace import SparkWorkspace
from spark_workbench import Workbench
from spark_deep_research import (MIN_HOPS, MAX_HOPS, ResearchEngine,
                                 ResearchError, ResearchSource, SourceDoc,
                                 contradictions)


def doc(source, title, body, url=""):
    return SourceDoc(source=source, title=title, body=body, url=url,
                     retrieved_at=time.time())


class Corpus:
    """Simple in-memory search standing in for snapshot/memory stores."""

    def __init__(self, docs):
        self.docs = docs

    def __call__(self, query):
        words = [w for w in query.lower().split() if len(w) > 3]
        hits = []
        for item in self.docs:
            text = (item.title + " " + item.body).lower()
            if any(word.rstrip(")(") in text for word in words):
                hits.append(item)
        return hits


class EngineSetupTests(unittest.TestCase):
    def test_budget_bounds_enforced(self):
        with CorpusFixture() as fixture:
            with self.assertRaises(ResearchError):
                fixture.engine(max_hops=1)
            with self.assertRaises(ResearchError):
                fixture.engine(max_hops=9)

    def test_at_least_one_registered_source(self):
        with self.assertRaises(ResearchError):
            ResearchEngine([])
        with self.assertRaises(ResearchError):
            ResearchEngine([object()])

    def test_source_names_validated(self):
        with self.assertRaises(ResearchError):
            ResearchSource("Bad Name!", lambda q: [])

    def test_question_length_validated(self):
        with CorpusFixture() as fixture:
            engine = fixture.engine()
            with self.assertRaises(ResearchError):
                engine.research("hi")
            with self.assertRaises(ResearchError):
                engine.research("q" * 501)


class ResearchFlowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = CorpusFixture()
        self.fixture.__enter__()
        self.addCleanup(self.fixture.__exit__, None, None, None)

    def test_answer_cites_only_retrieved_documents(self):
        engine = self.fixture.engine()
        result = engine.research("What payment contract deadline affects projects?")
        self.assertTrue(result["citations"])
        for citation in result["citations"]:
            self.assertIn(citation["id"], range(1, len(result["citations"]) + 1))
            self.assertIn(citation["source"], ("gmail", "obsidian-vault", "drive"))
        text = result["answer"]["text"]
        self.assertNotIn("hallucinated", text)

    def test_missing_facts_are_explicitly_unverified(self):
        engine = self.fixture.engine()
        result = engine.research("What payment contract deadline governs Quenya renewals?")
        answer = result["answer"]
        self.assertFalse(answer["verified"])
        self.assertIn("Unverified terms", answer["text"])

    def test_no_evidence_stops_instead_of_inventing(self):
        engine = self.fixture.engine()
        result = engine.research("Xylophone quantum resonance in kumquat farming?")
        self.assertEqual(result["documents"], 0)
        self.assertIn("No evidence retrieved", result["answer"]["text"])
        self.assertFalse(result["verified"])

    def test_hop_budget_never_exceeded_and_trace_records_queries(self):
        engine = self.fixture.engine(max_hops=3)
        result = engine.research("What payment contract deadline affects projects?")
        self.assertLessEqual(result["hops"], 3)
        self.assertGreaterEqual(result["hops"], MIN_HOPS)
        for hop, step in enumerate(result["trace"], start=1):
            self.assertEqual(step["hop"], hop)
            self.assertTrue(step["query"])
            self.assertTrue(step["sources"] or step["documents"] == 0)

    def test_duplicate_documents_deduplicated_across_sources(self):
        engine = self.fixture.engine()
        result = engine.research("What payment contract deadline affects projects?")
        fingerprints = [c["fingerprint"] for c in result["citations"]]
        self.assertEqual(len(fingerprints), len(set(fingerprints)))

    def test_contradictions_are_surfaced_not_hidden(self):
        conflicting = [
            doc("gmail", "Sprint summary", "The refund rate was 2% in October 2026."),
            doc("obsidian-vault", "Finance memo",
                "The refund rate was 9% in October 2026. Payment contract deadline "
                "affects projects and refund tracking."),
        ]
        conflict = contradictions(conflicting[0], conflicting[1])
        self.assertIsNotNone(conflict)
        self.assertIn("2%", conflict["claim_a"])
        self.assertIn("9%", conflict["claim_b"])

    def test_failing_source_does_not_crash_or_fake_data(self):
        def broken(query):
            raise OSError("snapshot store offline")

        sources = [ResearchSource("offline-store", broken),
                   ResearchSource("local-corpus", Corpus([doc(
                       "local-corpus", "Sprint summary",
                       "Payment contract deadline affects projects.")]))]
        engine = ResearchEngine(sources)
        result = engine.research("Payment contract deadline affects projects?")
        self.assertGreaterEqual(result["documents"], 1)


class CorpusFixture:
    DOCS = [
        doc("gmail", "Contract renewal email",
            "The renewal payment contract deadline for 2026 is 30 November. "
            "Please confirm supplier invoicing details."),
        doc("obsidian-vault", "Projects tracker",
            "Projects flagged for renewal in 2026 include payment gateway work. "
            "Contract deadline 30 November is tracked in the finance section."),
        doc("drive", "Q3 finance sheet", "Marketing spend was 12,400 USD in Q3."),
        doc("drive", "October refund memo", "Refund rate was 4% in October."),
    ]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def engine(self, max_hops=4):
        sources = [ResearchSource("local-corpus", Corpus(self.DOCS)),
                   ResearchSource("drive-archive", Corpus(self.DOCS[:2]))]
        return ResearchEngine(sources, max_hops=max_hops)


class WorkbenchResearchWiringTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.directory.name)
        self.workbench = Workbench(self.workspace)
        self.addAsyncCleanup(self._close)

    async def _close(self):
        await self.workbench.integrations.close()
        await self.workbench.intelligence.close()
        self.directory.cleanup()

    async def test_research_run_is_registered_and_safe_on_empty_corpus(self):
        from spark_workbench import ACTION_KEYS
        self.assertIn("research_run", ACTION_KEYS)
        result = await self.workbench.execute(
            "research_run", "general", {"question": "What contract deadline affects projects?",
                                        "max_hops": 4})
        self.assertEqual(result["budget"], 4)
        self.assertIn("hops", result)

    async def test_research_budget_out_of_bounds_is_refused(self):
        from spark_productivity import WorkbenchError
        with self.assertRaises(WorkbenchError):
            await self.workbench.execute(
                "research_run", "general", {"question": "What contract deadline affects projects?",
                                            "max_hops": 99})


if __name__ == "__main__":
    unittest.main()
