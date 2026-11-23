import unittest
from dataclasses import replace

from aams.offline_policy import EvidenceBasis, OfflineOutcome, OutcomeLabel
from aams.retrieval_routing import RetrievalMode
from aams.shadow_pairs import PairStatus, ShadowArm, ShadowPair, ShadowPairLedger
from aams.storage import AccessContext

START = "2026-01-01T00:00:00Z"
END = "2026-01-03T00:00:00Z"
CUTOFF = "2026-01-02T00:00:00Z"


class ShadowPairTest(unittest.TestCase):
    def setUp(self):
        self.access = AccessContext("host", "scope", shadow_observe=True)
        measured = OfflineOutcome(
            "1" * 32,
            "2" * 32,
            RetrievalMode.LEXICAL,
            OutcomeLabel.SATISFIED,
            1.0,
            "1",
            EvidenceBasis.CONTROLLED_REPLAY,
        )
        self.pair = ShadowPair(
            measured.task_id,
            measured.group_id,
            START,
            END,
            ShadowArm(CUTOFF, measured),
            ShadowArm(CUTOFF, replace(measured, mode=RetrievalMode.HYBRID)),
        )

    def test_scope_budget_replay_and_no_mutation(self):
        ledger = ShadowPairLedger(self.access, limit=1)
        self.assertEqual(
            ledger.record(self.access, self.pair).status, PairStatus.CONTROLLED_ALTERNATE
        )
        self.assertEqual(ledger.record(self.access, self.pair), self.pair)
        with self.assertRaisesRegex(ValueError, "different"):
            ledger.record(self.access, replace(self.pair, shadow=ShadowArm(CUTOFF, None)))
        with self.assertRaisesRegex(ValueError, "limit"):
            ledger.record(
                self.access,
                ShadowPair(
                    "3" * 32, "4" * 32, START, END, ShadowArm(CUTOFF, None), ShadowArm(CUTOFF, None)
                ),
            )
        for foreign in (
            replace(self.access, scope="other"),
            replace(self.access, principal="other"),
            replace(self.access, shadow_observe=False),
        ):
            with self.assertRaises(PermissionError):
                ledger.pairs(foreign)
            with self.assertRaises(PermissionError):
                ledger.record(foreign, self.pair)

    def test_missing_and_observational_are_not_controlled(self):
        one_sided = replace(self.pair, shadow=ShadowArm(CUTOFF, None))
        self.assertEqual(one_sided.status, PairStatus.MISSING_LABEL)
        observed = replace(self.pair.serving.outcome, basis=EvidenceBasis.OBSERVATIONAL)
        self.assertEqual(
            replace(self.pair, serving=ShadowArm(CUTOFF, observed)).status, PairStatus.OBSERVATIONAL
        )
        self.assertEqual(replace(self.pair, shadow=self.pair.serving).status, PairStatus.SAME_MODE)

    def test_temporal_and_identity_checks(self):
        for invalid in (
            ShadowArm(END, None),
            ShadowArm(CUTOFF, replace(self.pair.shadow.outcome, group_id="4" * 32)),
            ShadowArm(CUTOFF, replace(self.pair.shadow.outcome, policy_version="2")),
        ):
            with self.assertRaises(ValueError):
                replace(self.pair, shadow=invalid)
        ledger = ShadowPairLedger(self.access)
        ledger.record(self.access, self.pair)
        with self.assertRaisesRegex(ValueError, "overlap"):
            ledger.record(
                self.access,
                ShadowPair(
                    "3" * 32, "4" * 32, START, END, ShadowArm(CUTOFF, None), ShadowArm(CUTOFF, None)
                ),
            )
