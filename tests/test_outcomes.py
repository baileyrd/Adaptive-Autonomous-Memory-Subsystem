import tempfile
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from aams.contracts import EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind
from aams.learning import CandidateState, LearningCandidate, OutcomeFeedback
from aams.storage import AccessContext, SQLiteMemoryStore, VersionConflict, WriteConflict

TIME = "2026-01-01T00:00:00Z"


class OutcomeTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "memory.db"
        self.store = SQLiteMemoryStore(self.path)
        self.owner = AccessContext("operator", "work", True)
        self.other = AccessContext("other", "private", True)
        for access, identity in ((self.owner, "e"), (self.other, "hidden")):
            payload = identity.encode()
            evidence = Evidence(
                identity,
                access.scope,
                "meter",
                "fixture:" + identity,
                access.principal,
                TIME,
                TIME,
                EvidenceStatus.RECORDED,
                payload,
                "sha256:" + sha256(payload).hexdigest(),
            )
            formation = MemoryFormation(
                "f-" + identity,
                access.scope,
                MemoryKind.EXPERIENCE,
                (identity,),
                access.principal,
                TIME,
                EpistemicState.OBSERVED,
            )
            self.store.ingest(access, identity, formation, (evidence,))
        candidate = LearningCandidate("c", "work", "operator", "Rain", TIME, ("e",))
        self.store.create_candidate(self.owner, "candidate", candidate)
        self.feedback = OutcomeFeedback(
            "episode", "work", "c", "operator", "Fixed metric", 0.9, 0.2, TIME, ("e",)
        )

    def test_calibration_counterexample_and_history(self):
        low = self.store.append_outcome(self.owner, "first", 0, self.feedback)
        high = self.store.append_outcome(
            self.owner, "second", 1, replace(self.feedback, measured=1)
        )
        self.assertAlmostEqual(low.feedback.predicted - low.feedback.measured, 0.7)
        self.assertEqual(self.store.append_outcome(self.owner, "first", 0, self.feedback), low)
        with self.assertRaises(VersionConflict):
            self.store.append_outcome(self.owner, "stale", 1, self.feedback)
        restarted = SQLiteMemoryStore(self.path)
        restarted.verify_integrity()
        self.assertEqual(restarted.outcome_history(self.owner, "episode"), (low, high))
        self.assertEqual(restarted.get_candidate(self.owner, "c").state, CandidateState.PROPOSED)
        self.assertIsNone(restarted.get_belief(self.owner, "c"))

    def test_scope_and_atomic_links(self):
        for foreign in ("hidden", "missing"):
            with self.assertRaisesRegex(WriteConflict, "Invalid or unavailable"):
                self.store.append_outcome(
                    self.owner, "first", 0, replace(self.feedback, evidence_ids=("e", foreign))
                )
            self.assertEqual(self.store.outcome_history(self.owner, "episode"), ())
        with self.assertRaises(PermissionError):
            self.store.append_outcome(self.other, "first", 0, self.feedback)
        self.store.append_outcome(self.owner, "first", 0, self.feedback)
        self.assertEqual(self.store.outcome_history(self.other, "episode"), ())
        with self.assertRaises(PermissionError):
            another = AccessContext("another", "work", True)
            self.store.append_outcome(
                another, "rewrite", 1, replace(self.feedback, producer="another")
            )

    def test_invalid_scores(self):
        for score in (float("nan"), float("inf"), True, 1.1):
            with self.assertRaises(ValueError):
                replace(self.feedback, measured=score)
