"""Test measurement and memory matching on toy configurations only."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_lesson_transfer import simulate, winners
from lesson_transfer_policy import choose


class LessonTransferTests(unittest.TestCase):
    def test_measured_loss_deadline_and_timing_determine_winner(self):
        config = dict(items=4, capacity=3, occupied=1, drain=2, deadline=4)
        direct, paced = (simulate(config, arm) for arm in ("direct", "paced"))
        self.assertEqual(direct["dropped"], 2)
        self.assertEqual(paced["dropped"], 0)
        self.assertEqual(winners({"direct": direct, "paced": paced}), ["paced"])
        too_late = simulate({**config, "deadline": 2}, "paced")
        self.assertFalse(too_late["deadline_met"])
        self.assertEqual(winners({"direct": direct, "paced": too_late}), [])

    def test_same_actor_applies_guard_only_when_current_conditions_hold(self):
        config = dict(items=7, capacity=4, occupied=2, drain=2, deadline=9)
        memory = {
            "recommendations": [
                {"action": "paced", "conditions": [["headroom", "lt", 4]], "sources": ["prior"]}
            ]
        }
        self.assertEqual(choose({"configuration": config}, memory)["cited_sources"], ["prior"])
        decision = choose({"configuration": {**config, "capacity": 6}}, memory)
        self.assertEqual(decision, dict(action="direct", cited_sources=[], matched=False))
