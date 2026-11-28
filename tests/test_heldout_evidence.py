import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_heldout import audit_packet, compare, groups_for, run
from fusion import InvalidRun


class HeldoutEvidenceTests(unittest.TestCase):
    def test_required_id_tradeoff_can_leave_both_packets_incomplete(self):
        rows = [{"group": "g1"}, {"group": "g2"}, {"group": "g3"}]
        packets = [
            {"task": "one", "required": ["a", "b"], "bm25": ["a"], "dense": ["b"]},
            {"task": "two", "required": ["c"], "bm25": [], "dense": ["c"]},
            {"task": "three", "required": ["d"], "bm25": ["d"], "dense": []},
        ]
        result = compare(rows, packets, "dense", "bm25")
        self.assertEqual((result["wins"], result["losses"], result["unchanged"]), (1, 1, 1))
        self.assertEqual(result["queries_with_recovered_required_ids"], 2)
        self.assertEqual(result["queries_with_lost_required_ids"], 2)
        self.assertEqual(result["changes"][0]["recovered_ids"], ["b"])
        self.assertEqual(result["changes"][0]["lost_ids"], ["a"])
        self.assertEqual(
            result["grouped_95_interval"],
            compare(rows, packets, "dense", "bm25")["grouped_95_interval"],
        )

    def test_scope_time_and_provenance_reject_unusable_citations(self):
        visible = {"a": {"digest": "good", "source_locator": "fixture:source"}}
        for citation in (
            {"evidence_id": "future"},
            {"evidence_id": "private"},
            {"evidence_id": "a", "digest": "bad", "source_locator": "fixture:source"},
            {"evidence_id": "a", "digest": "good", "source_locator": "fixture:private"},
            {"evidence_id": "a", "digest": "good"},
        ):
            with self.subTest(citation=citation), self.assertRaises(InvalidRun):
                audit_packet({"items": [{"citations": [citation]}]}, visible)

    def test_semantic_fixture_runs_through_native_replay(self):
        groups, _ = groups_for("semantic", None)
        report = run(groups, None)
        self.assertEqual(report["queries"], 6)
        self.assertEqual(report["safety"], {"audited_packets": 12, "violations": 0})
        self.assertEqual(report["quality"]["bm25"]["contradictions_missed"], 0)
