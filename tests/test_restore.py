"""Integration of the #147 disposable cases with the guarded serving paths."""

import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from hashlib import sha256
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_erasure_restore_contract import TOKEN, encode, seed_erasure_backup

from aams.recall import CognitiveMemory, CognitiveNeed
from aams.representations import DeterministicFixtureProvider
from aams.restore import RestoreUnavailable, open_restored_scope
from aams.storage import AccessContext, SQLiteMemoryStore
from aams.vector_index import RepresentationIndex


class RestoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        path = Path(root.name)
        self.backup = path / "backup.sqlite"
        self.authority = path / "authority.sqlite"
        seed_erasure_backup(path / "live.sqlite", self.backup)
        self.digest = sha256(self.backup.read_bytes()).hexdigest()
        self.a = AccessContext("reader", "A", True)
        self.b = AccessContext("reader", "B")
        self.authority_write(
            """CREATE TABLE restore_scope_head(scope TEXT PRIMARY KEY, generation INTEGER)"""
        )
        self.authority_write(
            """CREATE TABLE restore_coverage(
                scope TEXT, generation INTEGER, backup_sha256 TEXT, complete INTEGER,
                closure TEXT, PRIMARY KEY(scope, generation, backup_sha256))"""
        )
        for scope, denied in (("A", ["primary", "copy"]), ("B", [])):
            self.authority_write("INSERT INTO restore_scope_head VALUES (?, 1)", (scope,))
            self.authority_write(
                "INSERT INTO restore_coverage VALUES (?, 1, ?, 1, ?)",
                (
                    scope,
                    self.digest,
                    encode(
                        dict(evidence=denied, formations=[], beliefs=[], candidates=[], episodes=[])
                    ).decode(),
                ),
            )

    def tearDown(self):
        self.assertEqual(sha256(self.backup.read_bytes()).hexdigest(), self.digest)

    def authority_write(self, query, args=()):
        with closing(sqlite3.connect(self.authority)) as db, db:
            db.execute(query, args)

    def advance(self):
        self.authority_write("UPDATE restore_scope_head SET generation=2 WHERE scope='A'")

    def test_serving_view_and_rebuilt_index(self):
        raw = SQLiteMemoryStore(self.backup)
        self.assertIsNotNone(raw.get_evidence(self.a, "primary"))
        self.assertIsNotNone(raw.get_candidate(self.a, "multi"))
        with (
            open_restored_scope(self.backup, self.authority, "A") as a,
            open_restored_scope(self.backup, self.authority, "B") as b,
        ):
            self.assertIsNone(a.get_evidence(self.a, "primary"))
            self.assertIsNone(a.get_evidence(self.a, "copy"))
            self.assertIsNone(a.get_candidate(self.a, "multi"))
            self.assertIsNone(a.get_candidate(self.a, "single"))
            self.assertIsNone(a.get_evidence(self.b, "primary"))
            self.assertEqual(b.get_evidence(self.b, "primary").payload, b"foreignpayload")
            memory = CognitiveMemory(a)
            self.assertEqual(
                memory.recall(self.a, CognitiveNeed(entity="evidence", identifier="primary"))[
                    "items"
                ],
                [],
            )
            self.assertEqual(memory.recall(self.a, CognitiveNeed(query=TOKEN))["items"], [])
            self.assertTrue(memory.recall(self.a, CognitiveNeed(query="retainalpha"))["items"])
            index = RepresentationIndex(a)
            provider = DeterministicFixtureProvider()
            self.assertEqual(index.snapshot(self.a, provider.spec).status, "missing")
            rebuilt = index.rebuild(self.a, provider)
            self.assertEqual(rebuilt.status, "fresh")
            self.assertEqual({item.source_id for item in rebuilt.vectors}, {"other", "third"})
            hybrid = memory.recall(self.a, CognitiveNeed(query=TOKEN), provider=provider)
            self.assertNotIn("primary", repr(hybrid["items"]))
            self.assertNotIn(TOKEN, repr(hybrid["items"]))
            with self.assertRaises(PermissionError):
                a.create_candidate(self.a, "multi", None)
            self.authority.unlink()
            with self.assertRaises(RestoreUnavailable):
                memory.recall(self.a, CognitiveNeed())
            with self.assertRaises(RestoreUnavailable):
                index.snapshot(self.a, provider.spec)
            with self.assertRaises(RestoreUnavailable):
                index.rebuild(self.a, provider)

    def test_incomplete_or_wrong_coverage_refuses_to_open(self):
        for field, value in (("complete", 0), ("backup_sha256", "wrong"), ("closure", "{}")):
            with self.subTest(field=field):
                self.authority_write(
                    f"UPDATE restore_coverage SET {field}=? WHERE scope='A'", (value,)
                )
                with self.assertRaises(RestoreUnavailable):
                    with open_restored_scope(self.backup, self.authority, "A"):
                        self.fail("Unverified scope opened")
                self.authority_write(
                    "UPDATE restore_coverage SET complete=1, backup_sha256=? WHERE scope='A'",
                    (self.digest,),
                )
        self.authority.unlink()
        with self.assertRaises(RestoreUnavailable):
            with open_restored_scope(self.backup, self.authority, "A"):
                self.fail("Scope opened without authority")

    def test_advance_during_rebuild_prevents_publication(self):
        advance = self.advance

        class AdvancingProvider(DeterministicFixtureProvider):
            def encode(self, text):
                advance()
                return super().encode(text)

        with (
            open_restored_scope(self.backup, self.authority, "A") as a,
            open_restored_scope(self.backup, self.authority, "B") as b,
        ):
            with self.assertRaises(RestoreUnavailable):
                RepresentationIndex(a).rebuild(self.a, AdvancingProvider())
            with closing(sqlite3.connect(a.path)) as db:
                self.assertEqual(
                    db.execute("SELECT count(*) FROM representation_batch").fetchone(), (0,)
                )
                self.assertEqual(
                    db.execute("SELECT count(*) FROM representation_vector").fetchone(), (0,)
                )
            with self.assertRaises(RestoreUnavailable):
                a.get_evidence(self.a, "other")
            self.assertEqual(b.get_evidence(self.b, "primary").payload, b"foreignpayload")
            with self.assertRaises(RestoreUnavailable):
                with open_restored_scope(self.backup, self.authority, "A"):
                    self.fail("Scope opened without coverage for the new head")
            self.authority_write(
                """INSERT INTO restore_coverage
                   SELECT scope, 2, backup_sha256, complete, closure FROM restore_coverage
                   WHERE scope='A' AND generation=1"""
            )
            with self.assertRaises(RestoreUnavailable):
                a.get_evidence(self.a, "other")
            with open_restored_scope(self.backup, self.authority, "A") as refreshed:
                self.assertIsNone(refreshed.get_evidence(self.a, "primary"))
                self.assertIsNotNone(refreshed.get_evidence(self.a, "other"))

    async def test_mcp_reads_and_advance(self):
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "aams.mcp_server",
                "--restore-backup",
                str(self.backup),
                "--restore-authority",
                str(self.authority),
                "--principal",
                "reader",
                "--scope",
                "A",
            ],
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            for tool, args in (
                ("memory_explain", {"entity": "evidence", "identifier": "primary"}),
                ("memory_recall", {"query": TOKEN}),
            ):
                result = await session.call_tool(tool, args)
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["items"], [])
            available = await session.call_tool("memory_recall", {"query": "retainalpha"})
            self.assertTrue(available.structured_content["items"])
            self.advance()
            failed = await session.call_tool("memory_recall", {"query": "retainalpha"})
            self.assertTrue(failed.is_error)
            self.assertEqual(failed.structured_content, {"code": "STORE_ERROR"})
