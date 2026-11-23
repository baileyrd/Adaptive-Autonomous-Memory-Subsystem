import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from aams.contracts import EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind
from aams.learning import CandidateState, CandidateTransitionRequest, LearningCandidate
from aams.storage import (
    AccessContext,
    SQLiteMemoryStore,
    VersionConflict,
    WriteConflict,
    _BELIEF_SCHEMA,
    _SCHEMA,
)

TIME = "2026-01-01T00:00:00Z"


class CandidateStorageTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "memory.db"
        with closing(sqlite3.connect(self.path)) as db, db:
            for statement in (*_SCHEMA, *_BELIEF_SCHEMA):
                db.execute(statement)
            db.execute("PRAGMA user_version=2")
        self.store = SQLiteMemoryStore(self.path)
        self.author = AccessContext("proposer", "weather", True)
        self.reviewer = AccessContext("reviewer", "weather", True, True)
        for identity, actor, payload in (
            ("a", "station-a", b"original"),
            ("copy", "station-b", b"original"),
            ("b", "station-c", b"separate"),
            ("self", "proposer", b"self"),
        ):
            self.ingest(self.author, identity, actor, payload)
        self.proposal = LearningCandidate(
            "c", "weather", "proposer", "Rain", TIME, ("a", "copy", "b", "self")
        )

    def ingest(self, access, identity, actor, payload):
        evidence = Evidence(
            identity,
            access.scope,
            actor,
            f"source:{identity}",
            access.principal,
            TIME,
            TIME,
            EvidenceStatus.RECORDED,
            payload,
            "sha256:" + sha256(payload).hexdigest(),
        )
        form = MemoryFormation(
            "f-" + identity,
            access.scope,
            MemoryKind.EXPERIENCE,
            (identity,),
            access.principal,
            TIME,
            EpistemicState.OBSERVED,
        )
        self.store.ingest(access, identity, form, (evidence,))

    def decision(self, old, new, *, actor="reviewer"):
        return CandidateTransitionRequest(
            "c", "weather", old, new, actor, "Reviewed provenance", TIME
        )

    def test_scope_lineage_rollback_and_replay(self):
        other = AccessContext("other", "private", True)
        self.ingest(other, "hidden", "station", b"hidden")
        for identifier in ("hidden", "missing"):
            with self.assertRaisesRegex(WriteConflict, "Invalid or unavailable"):
                self.store.create_candidate(
                    self.author, "request", replace(self.proposal, support_ids=("a", identifier))
                )
            self.assertIsNone(self.store.get_candidate(self.author, "c"))
        record = self.store.create_candidate(self.author, "request", self.proposal)
        self.assertEqual(self.store.create_candidate(self.author, "request", self.proposal), record)
        with self.assertRaises(WriteConflict):
            self.store.create_candidate(
                self.author, "request", replace(self.proposal, claim="different")
            )
        self.assertIsNone(self.store.get_candidate(other, "c"))
        self.assertIsNone(self.store.validate_candidate(other, "c"))
        result = self.store.validate_candidate(self.author, "c")
        self.assertEqual(result.independent_support, ("a", "b"))
        self.assertEqual(result.duplicate_support, ("copy",))
        self.assertEqual(result.unverified_support, ("self",))

    def test_policy_history_and_restart(self):
        self.store.create_candidate(self.author, "request", self.proposal)
        validate = self.decision(CandidateState.PROPOSED, CandidateState.VALIDATED)
        with self.assertRaises(PermissionError):
            self.store.decide_candidate(self.author, "validate", 0, validate)
        record = self.store.decide_candidate(self.reviewer, "validate", 0, validate)
        self.assertEqual(
            self.store.decide_candidate(self.reviewer, "validate", 0, validate), record
        )
        approve = self.decision(CandidateState.VALIDATED, CandidateState.APPROVED)
        forged = replace(self.author, candidate_review=True)
        with self.assertRaises(PermissionError):
            self.store.decide_candidate(forged, "approve", 1, replace(approve, actor="proposer"))
        approved = self.store.decide_candidate(self.reviewer, "approve", 1, approve)
        with self.assertRaises(PermissionError):
            self.store.decide_candidate(
                self.reviewer,
                "promote",
                2,
                self.decision(CandidateState.APPROVED, CandidateState.PROMOTED),
            )
        restarted = SQLiteMemoryStore(self.path)
        restarted.verify_integrity()
        self.assertEqual(restarted.get_candidate(self.author, "c"), approved)
        self.assertEqual(approved.state, CandidateState.APPROVED)
        self.assertEqual([item.version for item in approved.history], [1, 2])
        self.assertIsNone(restarted.get_belief(self.author, "c"))

    def test_concurrent_decisions_and_contradiction(self):
        self.store.create_candidate(
            self.author,
            "request",
            replace(self.proposal, support_ids=("a", "copy"), refute_ids=("b",)),
        )
        validate = self.decision(CandidateState.PROPOSED, CandidateState.VALIDATED)

        def attempt(key):
            try:
                return self.store.decide_candidate(self.reviewer, key, 0, validate)
            except VersionConflict:
                return None

        with ThreadPoolExecutor(max_workers=2) as threads:
            outcomes = list(threads.map(attempt, ("one", "two")))
        self.assertEqual(outcomes.count(None), 1)
        self.assertEqual(self.store.validate_candidate(self.author, "c").refute_ids, ("b",))
        with self.assertRaises(PermissionError):
            self.store.decide_candidate(
                self.reviewer,
                "approve",
                1,
                self.decision(CandidateState.VALIDATED, CandidateState.APPROVED),
            )
