"""Canonical consistency checks on temporary recovery fixtures."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
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
from aams.storage import AccessContext, SQLiteMemoryStore, StoreIntegrityError

TIME = "2026-01-12T09:00:00Z"


class AuditIntegrityTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "restored.db"
        self.store = SQLiteMemoryStore(self.path)
        self.access = AccessContext("collector", "weather", True)
        payload = b"gauge reading"
        evidence = Evidence(
            "e",
            "weather",
            "station",
            "fixture:gauge",
            "collector",
            TIME,
            TIME,
            EvidenceStatus.RECORDED,
            payload,
            "sha256:" + sha256(payload).hexdigest(),
        )
        formation = MemoryFormation(
            "f",
            "weather",
            MemoryKind.EXPERIENCE,
            ("e",),
            "collector",
            TIME,
            EpistemicState.OBSERVED,
        )
        self.store.ingest(self.access, "ingest", formation, (evidence,))

    def test_integrity_rejects_incomplete_formation(self):
        # Simulate a recovered database missing a row while all foreign keys remain valid.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM formation_evidence WHERE formation_id='f'")
        with self.assertRaises(StoreIntegrityError):
            self.store.get_formation(self.access, "f")
        with self.assertRaises(StoreIntegrityError):
            self.store.verify_integrity()

    def test_integrity_rejects_incomplete_revision(self):
        proposal = BeliefProposal(
            "It rained",
            EpistemicState.INFERRED,
            "Gauge",
            TIME,
            support_ids=("e",),
        )
        self.store.revise(self.access, "weather", None, proposal)
        # Model a partial recovery by importing a new revision row without its provenance.
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                """INSERT INTO belief_revision
                   SELECT scope, belief_id, 'restored', revision_id, 2, actor, recorded_at,
                          proposition, state, rationale, valid_from, valid_until, confidence_basis
                   FROM belief_revision WHERE sequence=1"""
            )
        with self.assertRaises(StoreIntegrityError):
            self.store.get_belief(self.access, "weather")
        with self.assertRaises(StoreIntegrityError):
            self.store.verify_integrity()
