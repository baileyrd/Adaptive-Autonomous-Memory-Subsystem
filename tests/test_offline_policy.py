"""No online policy changes or counterfactual claims from telemetry."""

import unittest
from dataclasses import FrozenInstanceError

from aams.offline_policy import (
    EvidenceBasis,
    OfflineOutcome,
    OfflineRiskBudget,
    OutcomeLabel,
    compare_controlled,
)
from aams.retrieval_routing import RetrievalMode

ID_A = "a" * 32
ID_B = "b" * 32
GROUP = "c" * 32


def sample(
    task_id=ID_A,
    mode=RetrievalMode.LEXICAL,
    label=OutcomeLabel.SATISFIED,
    latency=2.0,
    basis=EvidenceBasis.CONTROLLED_REPLAY,
    group_id=GROUP,
):
    return OfflineOutcome(task_id, group_id, mode, label, latency, "1", basis)


class OfflinePolicyTests(unittest.TestCase):
    def test_valid_matched_replay(self):
        baseline = (
            sample(),
            sample(ID_B, label=OutcomeLabel.UNSATISFIED),
        )
        candidate = (
            sample(mode=RetrievalMode.HYBRID, latency=4.0),
            sample(
                ID_B,
                mode=RetrievalMode.HYBRID,
                label=OutcomeLabel.SATISFIED,
                latency=6.0,
            ),
        )
        result = compare_controlled(baseline, candidate, OfflineRiskBudget(5.0, 0.0))
        self.assertEqual(result.sample_count, 2)
        self.assertEqual(result.baseline_satisfied, 1)
        self.assertEqual(result.candidate_satisfied, 2)
        self.assertEqual(result.candidate_mean_latency_ms, 5.0)
        self.assertTrue(result.meets_risk_budget)
        with self.assertRaises(FrozenInstanceError):
            result.candidate_satisfied = 9

    def test_budget_failure_is_explicit(self):
        baseline = (sample(),)
        candidate = (
            sample(
                mode=RetrievalMode.HYBRID,
                label=OutcomeLabel.UNSATISFIED,
                latency=10.0,
            ),
        )
        result = compare_controlled(baseline, candidate, OfflineRiskBudget(5.0, 0.0))
        self.assertFalse(result.meets_risk_budget)
        self.assertEqual(result.candidate_unsatisfied, 1)

    def test_observational_data_is_not_counterfactual_evidence(self):
        original = (sample(basis=EvidenceBasis.OBSERVATIONAL),)
        other = (sample(mode=RetrievalMode.HYBRID),)
        with self.assertRaises(ValueError):
            compare_controlled(original, other, OfflineRiskBudget(10.0, 1.0))

    def test_rejects_unmatched_and_duplicate_runs(self):
        base = (sample(),)
        candidate = (sample(task_id=ID_B, mode=RetrievalMode.HYBRID),)
        with self.assertRaises(ValueError):
            compare_controlled(base, candidate, OfflineRiskBudget(10.0, 1.0))
        duplicate = (sample(), sample())
        with self.assertRaises(ValueError):
            compare_controlled(duplicate, duplicate, OfflineRiskBudget(10.0, 1.0))
        with self.assertRaises(ValueError):
            compare_controlled(base, (), OfflineRiskBudget(10.0, 1.0))

    def test_same_mode_or_group_mismatch_rejected(self):
        base = (sample(),)
        with self.assertRaises(ValueError):
            compare_controlled(base, base, OfflineRiskBudget(10.0, 1.0))
        other = (sample(mode=RetrievalMode.HYBRID, group_id="d" * 32),)
        with self.assertRaises(ValueError):
            compare_controlled(base, other, OfflineRiskBudget(10.0, 1.0))

    def test_outcomes_reject_untrusted_fields(self):
        for changes in (
            {"task_id": "query-contents"},
            {"group_id": ""},
            {"mode": "hybrid"},
            {"label": "satisfied"},
            {"basis": "controlled_replay"},
            {"policy_version": "0"},
            {"latency_ms": 1},
            {"latency_ms": float("nan")},
            {"latency_ms": float("inf")},
            {"latency_ms": -1.0},
            {"latency_ms": 60_001.0},
        ):
            args = {
                "task_id": ID_A,
                "group_id": GROUP,
                "mode": RetrievalMode.LEXICAL,
                "label": OutcomeLabel.SATISFIED,
                "latency_ms": 2.0,
                "policy_version": "1",
                "basis": EvidenceBasis.CONTROLLED_REPLAY,
                **changes,
            }
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                OfflineOutcome(**args)

    def test_budget_validates_its_parameters(self):
        for latency, unsatisfied in (
            (0.0, 0.0),
            (float("nan"), 0.0),
            (float("inf"), 0.0),
            (5.0, -0.1),
            (5.0, 1.1),
            (5.0, float("nan")),
            (5, 0.0),
            (5.0, 0),
        ):
            with self.subTest(latency=latency, unsatisfied=unsatisfied):
                with self.assertRaises(ValueError):
                    OfflineRiskBudget(latency, unsatisfied)

    def test_offline_module_does_not_change_authority(self):
        record = sample()
        self.assertFalse(hasattr(record, "promote"))
        self.assertFalse(hasattr(record, "apply"))
        with self.assertRaises(FrozenInstanceError):
            record.label = OutcomeLabel.UNSATISFIED


if __name__ == "__main__":
    unittest.main()
