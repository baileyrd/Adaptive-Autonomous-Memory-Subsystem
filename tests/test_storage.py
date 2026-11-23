import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path

from aams.contracts import EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind
from aams.storage import AccessContext, SQLiteMemoryStore, StoreIntegrityError, WriteConflict

TIME = "2026-11-23T04:00:00+01:00"
PAYLOAD = b"raw observation\x00\xff"
DIGEST = "sha256:" + sha256(PAYLOAD).hexdigest()


class StorageTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "memory.db"
        self.store = SQLiteMemoryStore(self.path)
        self.owner = AccessContext("agent-a", "scope-a", True)
        self.evidence = Evidence(
            "ev-1",
            "scope-a",
            "sensor",
            "test:1",
            "agent-a",
            TIME,
            TIME,
            EvidenceStatus.RECORDED,
            PAYLOAD,
            DIGEST,
        )
        self.formation = MemoryFormation(
            "fm-1",
            "scope-a",
            MemoryKind.EXPERIENCE,
            ("ev-1",),
            "agent-a",
            TIME,
            EpistemicState.OBSERVED,
        )

    def ingest(self):
        return self.store.ingest(self.owner, "request", self.formation, (self.evidence,))

    def test_round_trip_and_process_restart(self):
        self.assertEqual(self.ingest(), self.formation)
        self.assertEqual(self.store.get_formation(self.owner, "fm-1"), self.formation)
        self.assertEqual(self.store.get_evidence(self.owner, "ev-1"), self.evidence)
        self.assertEqual(self.evidence.observed_at, "2026-11-23T03:00:00.000000+00:00")
        with self.assertRaises(FrozenInstanceError):
            self.evidence.payload = b"changed"
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                """import sys
from aams.storage import AccessContext, SQLiteMemoryStore
store = SQLiteMemoryStore(sys.argv[1])
access = AccessContext("agent-a", "scope-a")
store.verify_integrity()
print(store.get_evidence(access, "ev-1").digest)
print(store.get_formation(access, "fm-1").formation_id)
""",
                os.fspath(self.path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.splitlines(), [DIGEST, "fm-1"])

    def test_idempotency_and_duplicate_identity(self):
        self.assertEqual(self.ingest(), self.ingest())
        with self.assertRaises(WriteConflict):
            self.store.ingest(self.owner, "request", replace(self.formation, producer="other"), ())
        with self.assertRaises(WriteConflict):
            self.store.ingest(self.owner, "other-request", self.formation, (self.evidence,))

    def test_partial_write_rolls_back(self):
        broken = replace(self.formation, evidence_ids=("ev-1", "missing"))
        with self.assertRaises(WriteConflict):
            self.store.ingest(self.owner, "request", broken, (self.evidence,))
        self.assertIsNone(self.store.get_evidence(self.owner, "ev-1"))
        self.assertIsNone(self.store.get_formation(self.owner, "fm-1"))
        self.assertEqual(self.ingest(), self.formation)

    def test_scope_and_write_grant(self):
        self.ingest()
        other = AccessContext("agent-b", "scope-b", True)
        self.assertIsNone(self.store.get_evidence(other, "ev-1"))
        self.assertIsNone(self.store.get_evidence(other, "unknown"))
        self.assertIsNone(self.store.get_formation(other, "fm-1"))
        with self.assertRaises(PermissionError):
            self.store.ingest(other, "request", self.formation, ())
        with self.assertRaises(PermissionError):
            self.store.ingest(replace(self.owner, writable=False), "request", self.formation, ())
        cross_scope = replace(self.formation, formation_id="fm-2", scope="scope-b")
        with self.assertRaises(WriteConflict):
            self.store.ingest(other, "request", cross_scope, ())
        with self.assertRaises(PermissionError):
            self.store.ingest(other, "request", cross_scope, (self.evidence,))

    def test_invalid_canonical_values(self):
        for record, changes in (
            (self.evidence, {"digest": "sha256:invalid"}),
            (self.evidence, {"observed_at": "2026-11-23T04:00:00"}),
            (self.evidence, {"recorded_at": "2026-13-23T04:00:00Z"}),
            (self.formation, {"kind": "experiential"}),
            (self.formation, {"epistemic_state": "observed"}),
            (self.formation, {"evidence_ids": ("ev-1", "ev-1")}),
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(record, **changes)

    def test_corruption_is_reported(self):
        self.ingest()
        with sqlite3.connect(self.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE evidence SET payload=?", (b"changed",))
            db.execute("DROP TRIGGER evidence_no_update")
            db.execute("UPDATE evidence SET payload=?", (b"changed",))
        with self.assertRaises(StoreIntegrityError):
            self.store.get_evidence(self.owner, "ev-1")
        with self.assertRaises(StoreIntegrityError):
            self.store.verify_integrity()

    def test_unsupported_schema_is_preserved(self):
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA user_version=2")
        with self.assertRaises(StoreIntegrityError):
            SQLiteMemoryStore(self.path)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
