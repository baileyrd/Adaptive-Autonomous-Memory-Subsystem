"""Focused tests using toy receipts, independent of held-out histories."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_quorum_lineage import directed_context, public_response

TASK = {"topic": "toy", "checks": ["seal"]}


def row(rid, state="clear", time="2"):
    return dict(
        evidence_id=rid,
        source_actor=rid,
        source_locator=rid,
        observed_at=time,
        preview=json.dumps(dict(topic="toy", check="seal", state=state)),
        digest=state,
    )


class QuorumLineageTests(unittest.TestCase):
    def test_same_slot_or_old_original_does_not_complete_quorum(self):
        rows = [row("a"), row("b")]
        self.assertEqual(
            public_response(TASK, rows, {"a": "1", "b": "1"})["decision"]["action"], "abstain"
        )
        distinct = {"a": "1", "b": "2"}
        self.assertEqual(public_response(TASK, rows, distinct)["decision"]["action"], "proceed")
        self.assertEqual(
            public_response(TASK, [row("a", time="1"), row("b")], distinct)["decision"]["action"],
            "abstain",
        )

    def test_block_and_conflict_do_not_allow_release(self):
        receipts = {"a": "1", "b": "2"}
        rows = [row("a"), row("b"), row("c", "blocked")]
        self.assertEqual(public_response(TASK, rows, receipts)["decision"]["action"], "abstain")
        rows[-1] = row("c", "blocked", time="3")
        self.assertEqual(public_response(TASK, rows, receipts)["decision"]["action"], "stop")

    @patch("evaluate_quorum_lineage.components", return_value={"authorized": True})
    def test_cycle_and_visible_unknown_parent_do_not_resolve(self, _):
        rows = [row(rid) for rid in ("original", "copy", "mixed", "unknown", "cycle")]
        links = [
            dict(child=child, parent=parent)
            for child, parent in (
                ("copy", "original"),
                ("mixed", "original"),
                ("mixed", "unknown"),
                ("cycle", "cycle"),
                ("cycle", "original"),
            )
        ]
        context = directed_context(None, TASK, rows, links, {"original": "1"})
        self.assertEqual(
            [r["evidence_id"] for r in context], ["original", "mixed", "unknown", "cycle"]
        )
