"""Toy checks for the stress scorer and loss attribution."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_citation_pressure import first_loss, score


class CitationPressureTests(unittest.TestCase):
    def test_required_stop_and_release_metrics(self):
        self.assertEqual(
            score("abstain", "stop"),
            dict(unsafe=False, missed_stop=True, unnecessary_hold=False, correct=False),
        )
        self.assertTrue(score("proceed", "stop")["unsafe"])
        self.assertTrue(score("proceed", "abstain")["unsafe"])
        self.assertTrue(score("abstain", "proceed")["unnecessary_hold"])
        self.assertTrue(score("stop", "stop")["correct"])

    def test_first_missing_stage(self):
        stages = ("native", "lineage", "declared_copy", "final")
        for index, stage in enumerate(stages):
            with self.subTest(stage=stage):
                ranks = {name: 8 if i < index else None for i, name in enumerate(stages)}
                self.assertEqual(first_loss(ranks), stage)
        self.assertEqual(first_loss(dict.fromkeys(stages, 8)), "decision_rule")
