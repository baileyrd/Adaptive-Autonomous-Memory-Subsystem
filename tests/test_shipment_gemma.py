"""Keep the fresh Gemma cases and failed qualification stop independently testable."""

import collections
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_shipment_gemma import run
from shipment_gemma_cases import qualification


class ShipmentGemmaTests(unittest.TestCase):
    def test_fresh_balanced_cases_have_visible_decisive_evidence(self):
        cases = qualification()
        self.assertEqual(
            collections.Counter(expected for _, expected, _ in cases),
            {"proceed": 2, "stop": 2, "abstain": 2},
        )
        for case, expected, rows in cases:
            with self.subTest(case=case):
                newest = max(row[0] for row in rows)
                current = [row for row in rows if row[0] == newest]
                states = {state for _, state, _ in current}
                if expected == "proceed":
                    self.assertEqual(states, {"clear"})
                    self.assertGreaterEqual(len({slot for _, _, slot in current if slot}), 2)
                else:
                    self.assertEqual(
                        states, {"blocked"} if expected == "stop" else {"clear", "blocked"}
                    )

    def test_gate_rejects_one_failure_and_rotates_all_labels(self):
        outcomes = iter([True] * 17 + [False])

        def infer(*_):
            return {"scores": {"supported_correct": next(outcomes)}}

        with patch(
            "evaluate_shipment_gemma.actor.comparison_run",
            side_effect=AssertionError("comparison opened after a failed trial"),
        ):
            result = run(infer)
        self.assertFalse(result["qualified"])
        self.assertEqual(result["supported_correct"], 17)
        self.assertIsNone(result["comparison"])
        for case, _, _ in qualification():
            self.assertEqual(
                {r["rotation"] for r in result["qualification"] if r["case"] == case}, {0, 1, 2}
            )
