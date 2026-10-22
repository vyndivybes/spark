"""Capability 05 — Bounded multi-hop deep research with verified citations.

Runs a diagnose→retrieve→follow→synthesize loop over *configured* sources
only (local snapshots, memory, approved connectors — the owner's fixed list;
no arbitrary URL fetching and no cross-source privilege escalation).
Every claim in the answer cites a retrieved document; when the corpus does
not verify a question's key facts, the answer stops with an explicit
insufficiency statement instead of inventing content. Hops are bounded
(2-8) and the full query trace is returned.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

MIN_HOPS = 2
MAX_HOPS = 8
STOPWORDS = re.compile(
    r"\b(a|an|the|and|or|of|to|in|on|for|is|are|was|were|with|by|from|"
    r"what|which|who|whom|how|why|when|where|do|does|did|my|our)\b", re.I)


class ResearchError(ValueError):
    """Invalid research request, budget or source configuration."""


@dataclass
class SourceDoc:
    source: str          # source identity, e.g. "gmail" or "obsidian-vault"
    title: str
    body: str
    url: str = ""
    retrieved_at: float = 0.0

    @property
    def fingerprint(self):
        return hashlib.sha256(
            (self.source + "|" + self.title + "|" + self.body[:2000]).encode("utf-8")
        ).hexdigest()


def terms(question):
    """Meaningful keywords for hop planning and overlap scoring."""
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", question)]
    keep = []
    for word in words:
        if STOPWORDS.sub("", word) and word.lower() not in (t.lower() for t in keep):
            keep.append(word)
    return keep


def overlaps(text, keywords):
    text_lower = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in text_lower)


def contradictions(first, second):
    """Cheap, honest disagreement detector: same numbers, different key facts."""
    sentences = split_sentences(first.body)
    for sentence in split_sentences(second.body):
        for mine in sentences:
            numbers_mine = re.findall(r"\d+(?:\.\d+)?%?", mine)
            numbers_other = re.findall(r"\d+(?:\.\d+)?%?", sentence)
            if not numbers_mine or not numbers_other:
                continue
            keys_mine = {w.lower() for w in terms(mine)}
            keys_other = {w.lower() for w in terms(sentence)}
            if keys_mine & keys_other:
                if numbers_mine != numbers_other:
                    return {"claim_a": mine.strip()[:200], "claim_b": sentence.strip()[:200]}
    return None


def split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


class ResearchSource:
    """One allow-listed source the owner registered."""

    def __init__(self, name, handler):
        if not re.fullmatch(r"[a-z0-9_-]{2,40}", str(name)):
            raise ResearchError("Source names must be short lowercase tokens.")
        if not callable(handler):
            raise ResearchError("Each source needs a callable query handler.")
        self.name = name
        self.handler = handler


class ResearchEngine:
    """Verifiable multi-hop research over registered sources with a budget."""

    def __init__(self, sources, *, max_hops=4):
        if not isinstance(sources, (list, tuple)) or not sources:
            raise ResearchError("Register at least one approved research source.")
        if any(not isinstance(s, ResearchSource) for s in sources):
            raise ResearchError("Sources must be ResearchSource instances.")
        self.sources = list(sources)
        if type(max_hops) is not int or not MIN_HOPS <= max_hops <= MAX_HOPS:
            raise ResearchError("Set a hop budget between 2 and 8.")
        self._budget = max_hops

    def research(self, question, *, max_hops=None):
        budget = max_hops or self.max_hops_for()
        if type(budget) is not int or not MIN_HOPS <= budget <= MAX_HOPS:
            raise ResearchError("Set a hop budget between 2 and 8.")
        if not isinstance(question, str) or not 5 <= len(question.strip()) <= 500:
            raise ResearchError("Ask a research question of 5-500 characters.")
        keywords = terms(question)
        corpus = {}        # fingerprint -> SourceDoc
        trace = []
        queue = [{"query": question.strip(), "keywords": keywords}]
        hop = 0
        while queue and hop < budget:
            hop += 1
            step = queue.pop(0)
            found = self._query_sources(step["query"], hop)
            corpus.update(found)
            trace.append({"hop": hop, "query": step["query"],
                          "sources": sorted({doc.source for doc in found.values()}),
                          "documents": len(found)})
            for keyword in step["keywords"][:6]:
                follow = f"{question.strip()} ({keyword})"
                if follow != step["query"] and self._novel_follow(follow, trace):
                    queue.append({"query": follow, "keywords": terms(follow)})
        if not corpus:
            return self._no_evidence(question, budget, trace)
        ranked = self._rank(corpus, keywords)
        contradictions_found = self._first_contradiction(ranked)
        answer = self._synthesize(question, ranked, contradictions_found)
        self.max_hop_used = hop
        return {"question": question.strip(), "hops": hop, "budget": budget,
                "documents": len(ranked),
                "citations": [{"id": index + 1, "source": doc.source,
                               "title": doc.title, "url": doc.url,
                               "fingerprint": doc.fingerprint}
                              for index, doc in enumerate(ranked)],
                "trace": trace, "answer": answer,
                "contradictions": [contradictions_found] if contradictions_found else [],
                "verified": answer.get("verified", False)}

    def max_hops_for(self):
        return self._budget

    def _query_sources(self, query, hop):
        found = {}
        keywords = terms(query)
        for source in self.sources[:6]:
            try:
                documents = source.handler(query)
            except Exception:
                documents = []  # A failing source cannot crash the run or fake data.
            for document in documents or []:
                if not isinstance(document, SourceDoc):
                    continue
                if document.fingerprint in found or document.title == "":
                    continue
                found[document.fingerprint] = document
        return found

    def _novel_follow(self, follow, trace):
        return follow not in {step["query"] for step in trace}

    def _rank(self, corpus, keywords):
        docs = sorted(corpus.values(),
                      key=lambda doc: (-overlaps(doc.title + " " + doc.body, keywords),
                                       -(doc.retrieved_at or 0)))
        return docs[:40]

    def _first_contradiction(self, ranked):
        for index, primary in enumerate(ranked[:8]):
            for secondary in ranked[index + 1:index + 8]:
                conflict = contradictions(primary, secondary)
                if conflict:
                    conflict.update({"doc_a": primary.fingerprint,
                                     "doc_b": secondary.fingerprint})
                    return conflict
        return None

    def _synthesize(self, question, ranked, conflict):
        """Answer built only from retrieved sentences with citation indices."""
        keywords = terms(question)
        picks = []
        used = set()
        for index, doc in enumerate(ranked):
            scored = sorted(
                split_sentences(doc.body),
                key=lambda sentence: -overlaps(sentence, keywords))
            for sentence in scored[:2]:
                if overlaps(sentence, keywords) and len(sentence) > 30:
                    picks.append({"text": sentence, "citation": index + 1})
                    used.add(True)
            if len(picks) >= 6:
                break
        missing = [keyword for keyword in keywords
                   if all(keyword.lower() not in doc.body.lower() for doc in ranked[:10])]
        verified = bool(picks) and not missing and not conflict
        lines = [f"Research: {question.strip()}",
                 "Cited findings (from retrieved sources only):"]
        for pick in picks[:5]:
            lines.append(f"- {pick['text']} [source {pick['citation']}]")
        if missing:
            lines.append("Unverified terms in this corpus: " + ", ".join(missing))
        lines.append("Verified only where retrieved sources agree; "
                     "no knowledge beyond the retrieved documents is asserted.")
        if conflict:
            lines.append("Contradicting evidence detected — treat as unresolved.")
        return {"text": "\n".join(lines), "verified": verified,
                "unverified_terms": missing}

    def _no_evidence(self, question, budget, trace):
        return {"question": question, "hops": len(trace), "budget": budget,
                "documents": 0, "citations": [], "trace": trace,
                "answer": {"text": "No evidence retrieved from the approved "
                                    "sources; stopping rather than inventing.",
                           "verified": False, "unverified_terms": terms(question)},
                "contradictions": [], "verified": False}
