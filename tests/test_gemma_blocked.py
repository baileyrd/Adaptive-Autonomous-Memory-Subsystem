"""Verify paired inputs, counterbalance and separation of failure categories."""

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_gemma_blocked import GRAMMARS, evaluate, predicate_score


class GemmaBlockedTests(unittest.TestCase):
    def test_balanced_fixture_and_answer_never_enters_action_prompt(self):
        def run(answer):
            def infer(_, grammar):
                return (
                    '{"answer":"' + answer + '"}' if grammar == GRAMMARS["P"] else '{"action":"A"}'
                )

            return evaluate(infer)["records"]

        first, second = run("A"), run("B")
        counter = Counter()
        for row, other in zip(first, second):
            p, a = (row["trials"][name]["prompt"] for name in "PA")
            prefix = "Latest inspection extraction:\n"
            self.assertEqual(p.split(prefix)[1].splitlines()[0], a.split(prefix)[1].splitlines()[0])
            self.assertEqual(a, other["trials"]["A"]["prompt"])
            label = next(
                k for k, v in row["mappings"]["P"].items() if v == row["expected_predicate"]
            )
            counter[row["expected_predicate"], row["order"], label] += 1
        self.assertEqual(len(counter), 8)
        self.assertEqual(set(counter.values()), {1})

    def test_predicate_rotates_and_invalid_is_not_no(self):
        mapping = {"A": "NO", "B": "YES"}
        self.assertTrue(predicate_score('{"answer":"B"}', mapping, "YES")["correct"])
        rejected = predicate_score('{"answer":', mapping, "YES")
        self.assertTrue(rejected["malformed"])
        self.assertIsNone(rejected["answer"])
