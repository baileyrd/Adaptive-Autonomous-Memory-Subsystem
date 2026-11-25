"""Model-free regression checks for the Q4 evidence experiment."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_q4_resume import PINS, adjudicate, digest, fixtures, packet  # noqa: E402
from restart_agent_cases import cases as previous_cases  # noqa: E402


class Q4ResumeTests(unittest.TestCase):
    def test_source_identity_and_freeze(self):
        batch, labels = fixtures()
        self.assertEqual([digest(batch), digest(labels)], PINS)
        seen = {
            r[k]
            for c in previous_cases()
            for r in c["records"]
            for k in ("id", "source_actor", "source_locator", "scope")
        }
        for c in batch:
            own = {
                r[k]
                for r in c["records"]
                for k in ("id", "source_actor", "source_locator", "scope")
            }
            self.assertFalse(seen & own)
            seen |= own
            self.assertEqual(set(packet(c["request"], [])), {"goal", "access", "observations"})

    def test_conflict_needs_both_sides_and_denial_needs_no_citation(self):
        batch, labels = fixtures()
        for c in batch:
            label = labels[c["id"]]
            if c["family"] == "conflict":
                ids = label["required"]
                self.assertEqual(len(ids), 2)
                self.assertFalse(
                    adjudicate(c, label, "abstain", ids[:1], ids, "structured")["success"]
                )
                self.assertTrue(adjudicate(c, label, "abstain", ids, ids, "checkpoint")["success"])
            if c["family"] == "revoked":
                self.assertTrue(adjudicate(c, label, "abstain", [], [], "no_memory")["denial"])
                self.assertTrue(adjudicate(c, label, "publish", [], [], "checkpoint")["unsafe"])

    def test_invented_progress_and_repeated_failure(self):
        batch, labels = fixtures()
        key = next(c for c in batch if labels[c["id"]]["action"] == "repair")
        label = labels[key["id"]]
        self.assertTrue(adjudicate(key, label, "publish", [], [], "no_memory")["invented_progress"])
        self.assertTrue(adjudicate(key, label, "verify", [], [], "no_memory")["repeated_failure"])
