import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from aams.contracts import (
    BeliefProposal,
    EpistemicState,
    Evidence,
    EvidenceStatus,
    MemoryFormation,
    MemoryKind,
)
from aams.storage import AccessContext, SQLiteMemoryStore, VersionConflict, WriteConflict, _SCHEMA

TIME = "2026-01-01T00:00:00Z"
EARLIER = "2025-01-01T00:00:00Z"


class BeliefTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "memory.db"
        # Exercise upgrading the issue #3 schema with real rows before writing revisions.
        with sqlite3.connect(self.path) as db:
            for statement in _SCHEMA:
                db.execute(statement)
            db.execute("PRAGMA user_version=1")
            for key in ("e1", "e2"):
                payload = key.encode()
                db.execute(
                    "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        key,
                        "scope",
                        "sensor",
                        key,
                        "ingester",
                        TIME,
                        TIME,
                        "recorded",
                        payload,
                        "sha256:" + sha256(payload).hexdigest(),
                    ),
                )
        self.store = SQLiteMemoryStore(self.path)
        self.access = AccessContext("writer", "scope", True)
        self.proposal = BeliefProposal(
            "It rained", EpistemicState.INFERRED, "Forecast", TIME, support_ids=("e1",)
        )

    def test_reconstruct_known_and_effective_history(self):
        original = self.store.get_evidence(self.access, "e1")
        first = self.store.revise(self.access, "weather", None, self.proposal)
        correction = replace(
            self.proposal,
            state=EpistemicState.CONTESTED,
            valid_from=EARLIER,
            refute_ids=("e2",),
            rationale="Conflicting measurement",
        )
        second = self.store.revise(self.access, "weather", first.revision_id, correction)
        store = SQLiteMemoryStore(self.path)
        self.assertEqual(store.belief_history(self.access, "weather"), (first, second))
        self.assertEqual(store.get_belief(self.access, "weather"), second)
        self.assertEqual(
            store.get_belief(
                self.access, "weather", recorded_as_of=first.recorded_at, effective_at=TIME
            ),
            first,
        )
        self.assertIsNone(
            store.get_belief(
                self.access, "weather", recorded_as_of=first.recorded_at, effective_at=EARLIER
            )
        )
        self.assertEqual(store.get_belief(self.access, "weather", effective_at=EARLIER), second)
        self.assertEqual(second.parent_id, first.revision_id)
        self.assertEqual(store.get_evidence(self.access, "e1"), original)
        self.assertEqual(store.get_evidence(self.access, "e2").payload, b"e2")
        with sqlite3.connect(self.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE belief_revision SET rationale='rewritten'")

    def test_concurrent_revision_conflict(self):
        first = self.store.revise(self.access, "weather", None, self.proposal)

        def revise():
            try:
                return self.store.revise(self.access, "weather", first.revision_id, self.proposal)
            except VersionConflict as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: revise(), range(2)))
        self.assertEqual(results.count("VERSION_CONFLICT"), 1)
        self.assertEqual(len(self.store.belief_history(self.access, "weather")), 2)

    def test_unauthorized_links_and_rollback(self):
        first = self.store.revise(self.access, "weather", None, self.proposal)
        other = AccessContext("other", "private", True)
        foreign = Evidence(
            "foreign",
            other.scope,
            "sensor",
            "private:1",
            "other",
            TIME,
            TIME,
            EvidenceStatus.RECORDED,
            b"private",
            "sha256:" + sha256(b"private").hexdigest(),
        )
        formation = MemoryFormation(
            "fm",
            other.scope,
            MemoryKind.EXPERIENCE,
            ("foreign",),
            "other",
            TIME,
            EpistemicState.OBSERVED,
        )
        self.store.ingest(other, "request", formation, (foreign,))
        self.assertIsNone(self.store.get_belief(other, "weather"))
        self.assertEqual(self.store.belief_history(other, "weather"), ())
        with self.assertRaises(PermissionError):
            self.store.revise(replace(self.access, writable=False), "weather", None, self.proposal)
        messages = []
        for link in ("foreign", "unknown"):
            with self.assertRaises(WriteConflict) as failure:
                self.store.revise(
                    self.access,
                    "weather",
                    first.revision_id,
                    replace(self.proposal, refute_ids=(link,)),
                )
            messages.append(str(failure.exception))
        self.assertEqual(messages[0], messages[1])
        self.assertEqual(self.store.belief_history(self.access, "weather"), (first,))

    def test_rejects_observation_promotion_and_invalid_validity(self):
        with self.assertRaises(ValueError):
            replace(self.proposal, state=EpistemicState.OBSERVED)
        with self.assertRaises(ValueError):
            replace(self.proposal, valid_until=EARLIER)
        with self.assertRaises(ValueError):
            replace(self.proposal, valid_until="2026-01-01")
