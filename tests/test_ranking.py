import tempfile
import unittest
from collections import Counter
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from aams.contracts import EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind
from aams.ranking import LexicalRanking, bm25_scores, tokens
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.representations import DeterministicFixtureProvider
from aams.retrieval_routing import RetrievalMode
from aams.storage import AccessContext, SQLiteMemoryStore
from aams.vector_index import RepresentationIndex


def stamp(day: int) -> str:
    return f"2026-02-{day:02d}T00:00:00Z"


def seed(store: SQLiteMemoryStore, identifier: str, scope: str, day: int, text: str) -> None:
    access = AccessContext("collector", scope, True)
    payload = text.encode()
    evidence = Evidence(
        identifier,
        scope,
        "station-" + identifier,
        "fixture:" + identifier,
        access.principal,
        stamp(day),
        stamp(day),
        EvidenceStatus.RECORDED,
        payload,
        "sha256:" + sha256(payload).hexdigest(),
    )
    formation = MemoryFormation(
        "f-" + identifier,
        scope,
        MemoryKind.EXPERIENCE,
        (identifier,),
        access.principal,
        stamp(day),
        EpistemicState.OBSERVED,
    )
    store.ingest(access, identifier, formation, (evidence,))


VISIBLE = (
    ("e1", "pump pressure dropped at the harbor station"),
    ("e2", "the harbor crane was inspected and the harbor gate repaired"),
    ("e3", "filler " * 120 + "turbine vibration exceeded its limit"),
)


class Bm25ScoreTest(unittest.TestCase):
    def test_empty_corpus_and_unmatched_documents_score_zero(self):
        self.assertEqual(bm25_scores(frozenset({"a"}), []), ())
        docs = [Counter(["b"]), Counter(["a", "b"])]
        scores = bm25_scores(frozenset({"a"}), docs)
        self.assertEqual(scores[0], 0.0)
        self.assertGreater(scores[1], 0.0)

    def test_rare_terms_outweigh_common_terms(self):
        docs = [Counter(["common", "rare"]), Counter(["common", "other"]), Counter(["common"])]
        rare, common, _ = bm25_scores(frozenset({"common", "rare"}), docs)
        self.assertGreater(rare, common)
        self.assertGreater(common, 0.0)

    def test_term_frequency_saturates_and_length_normalizes(self):
        short = Counter(["a", "x"])
        repeated = Counter(["a"] * 4 + ["x"] * 4)
        padded = Counter(["a"] + ["x"] * 30)
        scores = bm25_scores(frozenset({"a"}), [short, repeated, padded, Counter(["y"])])
        self.assertGreater(scores[0], scores[2])
        self.assertLess(scores[1], 4 * scores[0])

    def test_tokenization_matches_overlap_ranker(self):
        self.assertEqual(tokens("Harbor_crane, HARBOR!"), ["harbor", "crane", "harbor"])


class Bm25RecallTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.access = AccessContext("reader", "team", False)

    def store(self, name: str, *, decoys: bool) -> SQLiteMemoryStore:
        store = SQLiteMemoryStore(self.directory / name)
        for identifier, text in VISIBLE:
            seed(store, identifier, "team", 1, text)
        if decoys:
            # Same vocabulary outside the reader's scope and after the cutoff.
            for index in range(4):
                seed(store, f"p{index}", "private", 1, "harbor turbine pump " * 3)
                seed(store, f"f{index}", "team", 9, "harbor turbine pump " * 3)
        return store

    def test_scores_reveal_nothing_about_private_or_future_records(self):
        need = CognitiveNeed(query="harbor pump turbine", recorded_as_of=stamp(2))
        results = []
        for name, decoys in (("plain.db", False), ("decoys.db", True)):
            memory = CognitiveMemory(
                self.store(name, decoys=decoys), lexical_ranking=LexicalRanking.BM25
            )
            results.append(memory.recall(self.access, need))
        self.assertEqual(results[0], results[1])
        self.assertEqual({item["id"] for item in results[0]["items"]}, {"f-e1", "f-e2", "f-e3"})

    def test_bm25_is_default_and_matches_full_payload(self):
        store = self.store("full.db", decoys=False)
        need = CognitiveNeed(query="turbine vibration")
        default = CognitiveMemory(store).recall(self.access, need)
        explicit = CognitiveMemory(store, lexical_ranking=LexicalRanking.BM25).recall(
            self.access, need
        )
        self.assertEqual(default, explicit)
        self.assertEqual([item["id"] for item in default["items"]], ["f-e3"])
        relevance = default["items"][0]["relevance"]
        self.assertEqual(relevance["ranker"], "bm25")
        self.assertEqual(relevance["matched_terms"], ["turbine", "vibration"])
        self.assertTrue(default["items"][0]["citations"][0]["preview_truncated"])

    def test_legacy_overlap_remains_selectable_for_rollback(self):
        store = self.store("legacy.db", decoys=False)
        legacy = CognitiveMemory(store, lexical_ranking=LexicalRanking.OVERLAP)
        self.assertEqual(
            legacy.recall(self.access, CognitiveNeed(query="turbine vibration"))["items"], []
        )
        packet = legacy.recall(self.access, CognitiveNeed(query="harbor pump"))
        self.assertEqual([item["id"] for item in packet["items"]], ["f-e1", "f-e2"])
        self.assertEqual(
            packet["items"][0]["relevance"],
            {"score": 2, "matched_terms": ["harbor", "pump"]},
        )

    def test_bm25_prefers_specific_evidence_over_repeated_common_terms(self):
        store = self.store("rank.db", decoys=False)
        need = CognitiveNeed(query="harbor pump")
        ranked = CognitiveMemory(store, lexical_ranking=LexicalRanking.BM25).recall(
            self.access, need
        )
        self.assertEqual([item["id"] for item in ranked["items"]], ["f-e1", "f-e2"])

    def test_bm25_hybrid_uses_normalized_lexical_component(self):
        store = self.store("hybrid.db", decoys=False)
        provider = DeterministicFixtureProvider()
        RepresentationIndex(store).rebuild(AccessContext("collector", "team", True), provider)
        memory = CognitiveMemory(store, lexical_ranking=LexicalRanking.BM25)
        packet = memory.recall(
            self.access,
            CognitiveNeed(query="harbor pump"),
            provider=provider,
            requested_mode=RetrievalMode.HYBRID,
        )
        self.assertEqual(packet["retrieval"]["mode"], "hybrid")
        for item in packet["items"]:
            self.assertLessEqual(item["relevance"]["score"], 1.0)
            self.assertEqual(item["relevance"]["ranker"], "bm25")

    def test_cached_terms_match_fresh_scoring_and_stay_bounded(self):
        store = self.store("cache.db", decoys=True)
        need = CognitiveNeed(query="harbor turbine", recorded_as_of=stamp(2))
        warm = CognitiveMemory(store, lexical_ranking=LexicalRanking.BM25)
        first = warm.recall(self.access, need)
        self.assertEqual(warm.recall(self.access, need), first)
        fresh = CognitiveMemory(store, lexical_ranking=LexicalRanking.BM25)
        self.assertEqual(fresh.recall(self.access, need), first)
        with patch("aams.recall._TERM_CACHE_ENTRIES", 1):
            bounded = CognitiveMemory(store, lexical_ranking=LexicalRanking.BM25)
            self.assertEqual(bounded.recall(self.access, need), first)
            self.assertEqual(len(bounded._term_cache), 1)

    def test_rejects_unsupported_ranking(self):
        store = self.store("bad.db", decoys=False)
        with self.assertRaises(ValueError):
            CognitiveMemory(store, lexical_ranking="bm25")


if __name__ == "__main__":
    unittest.main()
