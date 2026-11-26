"""Toy checks of witness priority under the common final budget."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_quorum_lineage import public_response
from shipment_witness_selector import select_witnesses

TASK = dict(topic="toy", checks=["seal"])


def row(rid, time, state="clear"):
    return dict(
        evidence_id=rid,
        source_actor=rid,
        source_locator=rid,
        digest=state,
        observed_at=time,
        preview=json.dumps(dict(topic="toy", check="seal", state=state)),
    )


def select(rows, receipts, byte_limit=8192):
    return select_witnesses(
        rows, task=TASK, receipts=receipts, max_citations=8, max_bytes=byte_limit
    )


class ShipmentWitnessTests(unittest.TestCase):
    def test_latest_conflict_keeps_unreceipted_block_in_native_order(self):
        rows = [row(str(i), "2") for i in range(9)] + [row("block", "2", "blocked")]
        context = select(rows, {"0": "north", "1": "south"})
        self.assertEqual(context, rows[:7] + rows[-1:])
        self.assertEqual(public_response(TASK, context, {})["decision"]["action"], "abstain")

    def test_latest_distinct_slots_and_no_credit_for_stale_receipt(self):
        rows = [row("old", "1", "blocked")] + [row(str(i), "2") for i in range(10)]
        self.assertIn(rows[-1], select(rows, {"0": "north", "1": "north", "9": "south"}))
        receipts = {"old": "north", "9": "south"}
        context = select(rows, receipts)
        self.assertEqual(public_response(TASK, context, receipts)["decision"]["action"], "abstain")
        size = len(json.dumps(rows[-1:], sort_keys=True).encode())
        self.assertEqual(select(rows, receipts, size), rows[-1:])
