import asyncio
import sqlite3
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from aams.contracts import EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind
from aams.storage import AccessContext, SQLiteMemoryStore, StoreIntegrityError

TIME = "2026-01-12T09:00:00Z"
_CRASH_WRITER = """
import sys
from hashlib import sha256
from aams.contracts import (
    BeliefProposal, EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind,
)
from aams.storage import AccessContext, SQLiteMemoryStore

path, phase = sys.argv[1:]
access = AccessContext("writer", "weather", True)
time = "2026-01-12T09:00:00Z"
payload = b"observation"
record = Evidence("e", "weather", "station", "test:1", "writer", time, time,
                  EvidenceStatus.RECORDED, payload, "sha256:" + sha256(payload).hexdigest())
formation = MemoryFormation("f", "weather", MemoryKind.EXPERIENCE, ("e",), "writer",
                            time, EpistemicState.OBSERVED)

def pause():
    print("BARRIER", flush=True)
    sys.stdin.read(1)
    return 0

class FaultStore(SQLiteMemoryStore):
    def _connect(self):
        connection = super()._connect()
        if phase in ("ingest", "revise"):
            table = "ingestion" if phase == "ingest" else "belief_evidence"
            connection.create_function("pause", 0, pause)
            connection.execute(f"CREATE TEMP TRIGGER barrier BEFORE INSERT ON {table} "
                               "BEGIN SELECT pause(); END")
        return connection

store = FaultStore(path)
if phase == "revise":
    previous = store.get_belief(access, "b")
    proposal = BeliefProposal("Revised", EpistemicState.INFERRED, "Correction", time,
                              support_ids=("e",))
    store.revise(access, "b", previous.revision_id, proposal)
else:
    store.ingest(access, "key", formation, (record,))
if phase == "committed":
    pause()
"""


class RecoveryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "memory.db"
        self.store = SQLiteMemoryStore(self.path)
        self.access = AccessContext("writer", "weather", True)

    async def kill_at_barrier(self, phase):
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            _CRASH_WRITER,
            str(self.path),
            phase,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        try:
            self.assertEqual(await asyncio.wait_for(child.stdout.readline(), 10), b"BARRIER\n")
        finally:
            if child.returncode is None:
                child.kill()
            await child.wait()
            child.stdin.close()
        self.assertNotEqual(child.returncode, 0)
        store = SQLiteMemoryStore(self.path)
        store.verify_integrity()
        return store

    async def test_ingestion_crash_before_and_after_commit(self):
        recovered = await self.kill_at_barrier("ingest")
        self.assertIsNone(recovered.get_evidence(self.access, "e"))
        self.assertIsNone(recovered.get_formation(self.access, "f"))
        recovered = await self.kill_at_barrier("committed")
        self.assertEqual(recovered.get_evidence(self.access, "e").payload, b"observation")
        self.assertEqual(recovered.get_formation(self.access, "f").evidence_ids, ("e",))

    async def test_revision_crash_preserves_history(self):
        from aams.contracts import BeliefProposal

        recovered = await self.kill_at_barrier("committed")
        revision = recovered.revise(
            self.access,
            "b",
            None,
            BeliefProposal(
                "Initial", EpistemicState.INFERRED, "Evidence", TIME, support_ids=("e",)
            ),
        )
        recovered = await self.kill_at_barrier("revise")
        self.assertEqual(recovered.belief_history(self.access, "b"), (revision,))

    async def test_backup_restores_and_broken_links_are_detected(self):
        record = Evidence(
            "e",
            "weather",
            "station",
            "test:1",
            "writer",
            TIME,
            TIME,
            EvidenceStatus.RECORDED,
            b"sample",
            "sha256:" + sha256(b"sample").hexdigest(),
        )
        formation = MemoryFormation(
            "f", "weather", MemoryKind.EXPERIENCE, ("e",), "writer", TIME, EpistemicState.OBSERVED
        )
        self.store.ingest(self.access, "key", formation, (record,))
        backup = self.path.with_name("backup.db")
        with sqlite3.connect(self.path) as live, sqlite3.connect(backup) as snapshot:
            live.backup(snapshot)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE formation_evidence SET evidence_id='broken'")
        with self.assertRaises(StoreIntegrityError):
            self.store.verify_integrity()
        restored = SQLiteMemoryStore(backup)
        restored.verify_integrity()
        self.assertEqual(restored.get_evidence(self.access, "e"), record)
        self.assertEqual(restored.get_formation(self.access, "f"), formation)
