"""Regression tests for scoped canonical IDs and schema-6 upgrades."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from hashlib import sha256
from pathlib import Path

from aams.contracts import EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind
from aams.retrieval_telemetry import _SCHEMA as _TELEMETRY_SCHEMA
from aams.storage import (
    _BELIEF_SCHEMA,
    _CANDIDATE_SCHEMA,
    _OUTCOME_SCHEMA,
    _SCHEMA,
    AccessContext,
    SQLiteMemoryStore,
)
from aams.vector_index import _SCHEMA as _REPRESENTATION_SCHEMA

TIME = "2026-01-01T00:00:00Z"
PAYLOAD = b"shared identifier"
SCHEMA_6 = (
    *_SCHEMA,
    *_BELIEF_SCHEMA,
    *_CANDIDATE_SCHEMA,
    *_OUTCOME_SCHEMA,
    *_REPRESENTATION_SCHEMA,
    *_TELEMETRY_SCHEMA,
)


def records(scope: str) -> tuple[MemoryFormation, Evidence]:
    evidence = Evidence(
        "ev-shared",
        scope,
        "sensor",
        "test:1",
        "agent",
        TIME,
        TIME,
        EvidenceStatus.RECORDED,
        PAYLOAD,
        "sha256:" + sha256(PAYLOAD).hexdigest(),
    )
    formation = MemoryFormation(
        "fm-shared",
        scope,
        MemoryKind.EXPERIENCE,
        ("ev-shared",),
        "agent",
        TIME,
        EpistemicState.OBSERVED,
    )
    return formation, evidence


class ScopedIdentityTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "memory.db"

    def ingest(self, store: SQLiteMemoryStore, scope: str) -> AccessContext:
        access = AccessContext("agent", scope, True)
        formation, evidence = records(scope)
        store.ingest(access, "request", formation, (evidence,))
        return access

    def test_identifier_in_one_scope_is_not_observable_from_another(self):
        store = SQLiteMemoryStore(self.path)
        first = self.ingest(store, "scope-a")
        second = self.ingest(store, "scope-b")
        for access in (first, second):
            formation = store.get_formation(access, "fm-shared")
            self.assertEqual(formation.scope, access.scope)
            self.assertEqual(store.get_evidence(access, "ev-shared").scope, access.scope)
        store.verify_integrity()

    def test_schema_6_store_upgrades_in_place(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            for statement in SCHEMA_6:
                db.execute(statement)
            db.execute("PRAGMA user_version=6")
        store_6 = SQLiteMemoryStore.__new__(SQLiteMemoryStore)
        store_6.path = self.path
        access = self.ingest(store_6, "scope-a")
        store = SQLiteMemoryStore(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 7)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable evidence"):
                db.execute("UPDATE evidence SET payload=x'00'")
        formation, evidence = records("scope-a")
        self.assertEqual(store.get_formation(access, "fm-shared"), formation)
        self.assertEqual(store.get_evidence(access, "ev-shared"), evidence)
        self.assertEqual(store.ingest(access, "request", formation, (evidence,)), formation)
        self.ingest(store, "scope-b")
        store.verify_integrity()


if __name__ == "__main__":
    unittest.main()
