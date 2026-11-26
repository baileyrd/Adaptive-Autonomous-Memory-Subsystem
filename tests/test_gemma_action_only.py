"""Check paired inputs and separate action, citation and formatting scores."""

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_gemma_action_only import assess, evaluate


class GemmaActionOnlyTests(unittest.TestCase):
    def test_pairs_share_facts_and_legend_and_balance_arm_order(self):
        output = evaluate(lambda *_: "{}")
        labels, orders = Counter(), Counter()
        for record in output["records"]:
            a, b = (record["responses"][arm]["prompt"] for arm in "AB")
            start, end = "Allowed action labels:\n", "\nResponse shape:"
            block_a, block_b = (prompt.split(start)[1].split(end)[0] for prompt in (a, b))
            self.assertEqual(block_a, block_b)
            labels[next(k for k, v in record["legend"].items() if v == record["expected"])] += 1
            orders[record["expected"], record["order"]] += 1
        self.assertEqual(labels, {"A": 2, "B": 2, "C": 2})
        self.assertEqual(len(orders), 6)
        self.assertTrue(all(n == 1 for n in orders.values()))

    def test_capture_error_and_wrong_action_with_relevant_citation(self):
        latest = {"R1": (3, "blocked", None)}
        mapping = {"A": "stop", "B": "proceed", "C": "abstain"}
        format_error = assess('{"action":', "A", latest, mapping, "stop")
        self.assertEqual(format_error["format_error"], "incomplete_or_malformed_json")
        self.assertFalse(format_error["abstained_on_stop"])
        result = assess('{"action":"C","citations":["R1"]}', "B", latest, mapping, "stop")
        self.assertTrue(result["abstained_on_stop"])
        self.assertTrue(result["required_evidence_covered"])
        self.assertFalse(result["supported_correct"])
