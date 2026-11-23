import unittest
from dataclasses import replace

from aams.offline_candidate import TrainingPair, train_candidate
from aams.offline_policy import EvidenceBasis, OfflineOutcome, OutcomeLabel
from aams.retrieval_routing import ROUTING_POLICY_VERSION, RetrievalMode


class OfflineTrainingTest(unittest.TestCase):
    def pair(self, task, group):
        left = OfflineOutcome(
            f"{task:032x}",
            f"{group:032x}",
            RetrievalMode.LEXICAL,
            OutcomeLabel.UNSATISFIED,
            1.0,
            ROUTING_POLICY_VERSION,
            EvidenceBasis.CONTROLLED_REPLAY,
        )
        return TrainingPair(
            True, True, left, replace(left, mode=RetrievalMode.HYBRID, label=OutcomeLabel.SATISFIED)
        )

    def test_duplicate_groups_do_not_qualify_and_policy_abstains(self):
        one = self.pair(1, 1)
        copy = self.pair(2, 1)
        learned = train_candidate((one, copy))
        self.assertFalse(learned.suggests_hybrid(short_query=True, opt_in=True))
        independent = self.pair(3, 2)
        ready = train_candidate((one, independent))
        self.assertEqual(ready, train_candidate((independent, one)))
        self.assertTrue(ready.suggests_hybrid(short_query=True, opt_in=True))
        self.assertFalse(ready.suggests_hybrid(short_query=False, opt_in=True))
        self.assertFalse(ready.suggests_hybrid(short_query=True, opt_in=False))
        with self.assertRaises(ValueError):
            train_candidate((one, one))

    def test_corrupt_observational_stale_and_counterexample_feedback(self):
        one, other = self.pair(1, 1), self.pair(2, 2)
        for fields in (
            {"basis": EvidenceBasis.OBSERVATIONAL},
            {"policy_version": "999"},
            {"group_id": "f" * 32},
        ):
            with self.assertRaises(ValueError):
                replace(one, hybrid=replace(one.hybrid, **fields))
        loss = replace(
            other,
            lexical=replace(other.lexical, label=OutcomeLabel.SATISFIED),
            hybrid=replace(other.hybrid, label=OutcomeLabel.UNSATISFIED),
        )
        self.assertFalse(
            train_candidate((one, loss)).suggests_hybrid(short_query=True, opt_in=True)
        )
