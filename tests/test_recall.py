import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from aams.contracts import (
    BeliefProposal,
    EpistemicState,
    Evidence,
    EvidenceStatus,
    MemoryFormation,
    MemoryKind,
)
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.storage import AccessContext, SQLiteMemoryStore

TIME = "2025-01-01T00:00:00Z"


class RecallTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "recall.db"
        self.store = SQLiteMemoryStore(self.path)
        self.memory = CognitiveMemory(self.store)
        self.access = AccessContext("host", "public", True)
        self.fixture = json.loads(
            Path(__file__).with_name("fixtures").joinpath("recall.json").read_text()
        )
        for identity, scope, observation in self.fixture["records"]:
            payload = observation.encode()
            digest = "sha256:" + sha256(payload).hexdigest()
            evidence = Evidence(
                "ev-" + identity,
                scope,
                "station",
                digest,
                "host",
                TIME,
                TIME,
                EvidenceStatus.RECORDED,
                payload,
                digest,
            )
            formation = MemoryFormation(
                identity,
                scope,
                MemoryKind.EXPERIENCE,
                (evidence.evidence_id,),
                "host",
                TIME,
                EpistemicState.OBSERVED,
            )
            self.store.ingest(AccessContext("host", scope, True), identity, formation, (evidence,))

    def test_stable_ranked_fixture_precision_and_scope(self):
        need = CognitiveNeed(query=self.fixture["query"], max_items=2)
        first = self.memory.recall(self.access, need)
        second = CognitiveMemory(SQLiteMemoryStore(self.path)).recall(self.access, need)
        self.assertEqual(first, second)
        self.assertTrue(first["truncated"])
        ids = [item["id"] for item in first["items"]]
        precision = len(set(ids) & set(self.fixture["relevant"])) / len(ids)
        self.assertEqual(precision, 1.0)
        self.assertEqual(ids, self.fixture["expected_top"])
        full = self.memory.recall(self.access, CognitiveNeed(query=self.fixture["query"]))
        self.assertNotIn("secret", [item["id"] for item in full["items"]])

    def test_exact_and_bounds(self):
        def explain(identifier, **limits):
            return self.memory.explain(
                self.access, CognitiveNeed(entity="formation", identifier=identifier, **limits)
            )

        self.assertEqual(explain("secret"), explain("unknown"))
        self.assertEqual(explain("a")["items"][0]["citations"][0]["preview"], "Rain storm warning")
        self.assertEqual(explain("a", max_bytes=128), {"items": [], "truncated": True})
        shallow = explain("a", max_depth=0)["items"][0]
        self.assertEqual(shallow["citations"], [])
        self.assertTrue(shallow["citations_truncated"])
        self.assertEqual(self.memory.recall(self.access, CognitiveNeed(query="..."))["items"], [])
        with self.assertRaises(ValueError):
            CognitiveNeed(max_items=0)
        with self.assertRaises(ValueError):
            CognitiveNeed(kinds=("experiential",))

    def test_historical_and_current_contradiction_explanation(self):
        initial = self.store.revise(
            self.access,
            "weather",
            None,
            BeliefProposal(
                "Rain storm ongoing",
                EpistemicState.INFERRED,
                "Forecast",
                TIME,
                support_ids=("ev-a",),
            ),
        )
        corrected = self.store.revise(
            self.access,
            "weather",
            initial.revision_id,
            BeliefProposal(
                "Rain storm possible",
                EpistemicState.CONTESTED,
                "Negative reading",
                "2024-01-01T00:00:00Z",
                support_ids=("ev-a",),
                refute_ids=("ev-noise",),
            ),
        )
        latest = self.memory.explain(
            self.access, CognitiveNeed(entity="belief", identifier="weather")
        )["items"][0]
        original = self.memory.recall(
            self.access,
            CognitiveNeed(
                entity="belief",
                identifier="weather",
                recorded_as_of=initial.recorded_at,
                effective_at=TIME,
            ),
        )["items"][0]
        self.assertEqual(latest["revision_id"], corrected.revision_id)
        self.assertTrue(latest["contradictory_evidence"])
        self.assertEqual([edge["role"] for edge in latest["citations"]], ["support", "refute"])
        self.assertEqual(original["revision_id"], initial.revision_id)
        self.assertFalse(original["contradictory_evidence"])
        ranked_as_of = self.memory.recall(
            self.access, CognitiveNeed(query="rain storm", recorded_as_of=initial.recorded_at)
        )
        belief = next(item for item in ranked_as_of["items"] if item["entity"] == "belief")
        self.assertEqual(belief["revision_id"], initial.revision_id)
        self.assertEqual([edge["role"] for edge in belief["citations"]], ["support"])

    def test_ranked_scan_uses_one_scoped_snapshot(self):
        with patch.object(self.store, "_connect", wraps=self.store._connect) as connections:
            result = self.memory.recall(
                self.access, CognitiveNeed(query="rain storm", kinds=(MemoryKind.EXPERIENCE,))
            )
        self.assertEqual(connections.call_count, 1)
        self.assertEqual([item["id"] for item in result["items"]], ["a", "b", "copy", "noise"])
