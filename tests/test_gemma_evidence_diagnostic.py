"""Reference, condition isolation and extraction scoring without inference."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_gemma_evidence_diagnostic import evaluate, extraction_score, reference


class GemmaEvidenceDiagnosticTests(unittest.TestCase):
    def test_score_separates_stale_invented_missing_and_duplicate(self):
        rows = [(1, "clear", "old"), (2, "clear", "a"), (2, "blocked", None)]
        _, facts, expected = reference(rows, (2, 3))
        self.assertEqual(expected, "abstain")
        output = dict(states=["clear", "clear"], slots=["old"], rows=[["R1", "clear", "old"]])
        result = extraction_score(json.dumps(output), facts)
        self.assertEqual(result["missing"]["states"], ["blocked"])
        self.assertEqual(result["invented"]["slots"], ["old"])
        self.assertEqual(result["invented"]["rows"], [["R1", "clear", "old"]])
        self.assertEqual(result["duplicates"]["states"], ["clear"])
        self.assertFalse(result["exact"])
        self.assertTrue(extraction_score(json.dumps(facts), facts)["exact"])
        self.assertTrue(extraction_score("invalid", facts)["malformed"])

    def test_verified_condition_keeps_both_conflict_states_without_answer(self):
        seen = []

        def infer(prompt, grammar):
            seen.append((prompt, grammar))
            return "{}"

        result = evaluate(infer)
        self.assertEqual(len(seen), 18)
        self.assertEqual(len({r["order"] for r in result["records"]}), 6)
        for row in result["records"]:
            c = row["conditions"]["C"]["prompt"]
            payload = c.split("Latest inspection extraction:\n", 1)[1].splitlines()[0]
            facts = json.loads(payload)
            self.assertEqual(set(facts), {"states", "slots", "rows"})
            self.assertEqual(facts, row["verified"])
            if row["expected"] == "abstain":
                self.assertEqual(set(facts["states"]), {"clear", "blocked"})
