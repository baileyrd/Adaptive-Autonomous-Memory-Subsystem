"""Distinguish wording-only behavior from correct evidence sensitivity."""

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_gemma_literal import QUESTIONS, evaluate


class GemmaLiteralTests(unittest.TestCase):
    def test_wording_only_has_reversals_without_evidence_flips(self):
        output = evaluate(lambda prompt: "YES" if QUESTIONS["A"] in prompt else "NO")
        summary = output["summary"]
        self.assertEqual(summary, output["baselines"]["wording_yes_no"])
        self.assertEqual(summary["wording_reversals"], 8)
        self.assertEqual(summary["accuracy"], {"A": 4, "B": 4})
        self.assertEqual(summary["evidence_flips"], {"A": 0, "B": 0})

    def test_matched_cases_change_only_one_observation_and_balance_order(self):
        output = evaluate(lambda _: "invalid")
        order_counts = Counter()
        for row in output["records"]:
            blocked, changed = (row["variants"][v] for v in ("blocked", "changed"))
            diff = [
                i
                for i, (a, b) in enumerate(
                    zip(blocked["observations"], changed["observations"], strict=True), 1
                )
                if a != b
            ]
            self.assertEqual([f"R{i}" for i in diff], [row["decisive"]])
            for name, variant in row["variants"].items():
                order_counts[name, variant["order"]] += 1
        self.assertEqual(set(order_counts.values()), {2})
        self.assertEqual(output["summary"]["invalid"], {"A": 8, "B": 8})
        self.assertEqual(output["summary"]["wording_reversals"], 0)
