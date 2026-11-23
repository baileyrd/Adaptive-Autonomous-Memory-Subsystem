import sqlite3
import tempfile
import unittest
from contextlib import closing
from hashlib import sha256
from pathlib import Path

from aams.contracts import EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind
from aams.representations import DeterministicFixtureProvider
from aams.storage import _BELIEF_SCHEMA, _CANDIDATE_SCHEMA, _OUTCOME_SCHEMA, _SCHEMA
from aams.storage import AccessContext, SQLiteMemoryStore
from aams.vector_index import RepresentationIndex

TIME = "2026-01-01T00:00:00Z"


class RepresentationIndexTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "memory.db"
        with closing(sqlite3.connect(self.path)) as db, db:
            for statement in (*_SCHEMA, *_BELIEF_SCHEMA, *_CANDIDATE_SCHEMA, *_OUTCOME_SCHEMA):
                db.execute(statement)
            db.execute("PRAGMA user_version=4")
        self.store = SQLiteMemoryStore(self.path)
        self.index = RepresentationIndex(self.store)
        self.author = AccessContext("author", "one", True)
        self.other = AccessContext("other", "two", True)
        self.provider = DeterministicFixtureProvider()

    def ingest(self, access, identity):
        payload = identity.encode()
        evidence = Evidence(
            identity,
            access.scope,
            "sensor",
            identity,
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

    def test_migrate_rebuild_restart_staleness_and_scope(self):
        self.ingest(self.author, "one")
        self.ingest(self.other, "secret")
        batch = self.index.rebuild(self.author, self.provider)
        self.assertEqual([vector.source_id for vector in batch.vectors], ["one"])
        self.assertEqual(self.index.rebuild(self.author, self.provider), batch)
        restarted = RepresentationIndex(SQLiteMemoryStore(self.path))
        self.assertEqual(restarted.snapshot(self.author, self.provider.spec), batch)
        self.assertEqual(restarted.snapshot(self.other, self.provider.spec).status, "missing")
        self.assertEqual(
            restarted.snapshot(self.author, DeterministicFixtureProvider(8).spec).status, "missing"
        )
        with self.assertRaises(PermissionError):
            restarted.invalidate(AccessContext("viewer", "one"), self.provider.spec)
        self.ingest(self.author, "new")
        self.assertEqual(restarted.snapshot(self.author, self.provider.spec).status, "stale")
        self.assertEqual(len(restarted.rebuild(self.author, self.provider).vectors), 2)
        restarted.invalidate(self.author, self.provider.spec)
        self.assertEqual(restarted.snapshot(self.author, self.provider.spec).status, "missing")
        self.assertIsNotNone(self.store.get_evidence(self.author, "one"))

    def test_corrupted_batch_is_disposable(self):
        self.ingest(self.author, "one")
        self.index.rebuild(self.author, self.provider)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE representation_vector SET values_blob=?", (b"invalid",))
        self.assertEqual(self.index.snapshot(self.author, self.provider.spec).status, "corrupt")
        self.assertEqual(self.index.rebuild(self.author, self.provider).status, "fresh")

    def test_replacement_rolls_back_on_write_failure(self):
        self.ingest(self.author, "one")
        original = self.index.rebuild(self.author, self.provider)
        self.ingest(self.author, "new")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                """CREATE TRIGGER fail_rebuild BEFORE INSERT ON representation_vector
                   BEGIN SELECT RAISE(ABORT, 'injected write failure'); END"""
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.index.rebuild(self.author, self.provider)
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(
                db.execute("SELECT generated_at FROM representation_batch").fetchone()[0],
                original.generated_at,
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM representation_vector").fetchone()[0], 1
            )
        self.assertEqual(self.index.snapshot(self.author, self.provider.spec).status, "stale")

    def test_killed_replacement_preserves_committed_batch(self):
        import subprocess
        import sys

        self.ingest(self.author, "one")
        original = self.index.rebuild(self.author, self.provider)
        self.ingest(self.author, "new")
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                """
import sys
from aams.representations import DeterministicFixtureProvider
from aams.storage import AccessContext, SQLiteMemoryStore
from aams.vector_index import RepresentationIndex

def stop_at_publish():
    print("uncommitted", flush=True)
    sys.stdin.read(1)
    return 0

class PausedStore(SQLiteMemoryStore):
    def _connect(self):
        db = super()._connect()
        db.create_function("pause_publish", 0, stop_at_publish)
        db.execute("CREATE TEMP TRIGGER pause_publish BEFORE INSERT ON representation_vector "
                   "BEGIN SELECT pause_publish(); END")
        return db

RepresentationIndex(PausedStore(sys.argv[1])).rebuild(
    AccessContext("author", "one", True), DeterministicFixtureProvider()
)
""",
                str(self.path),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            import select

            self.assertTrue(select.select([child.stdout], [], [], 10)[0])
            self.assertEqual(child.stdout.readline().strip(), "uncommitted")
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)
        reopened = SQLiteMemoryStore(self.path)
        reopened.verify_integrity()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT generated_at FROM representation_batch").fetchone()[0],
                original.generated_at,
            )
        self.assertEqual(
            RepresentationIndex(reopened).snapshot(self.author, self.provider.spec).status, "stale"
        )

    def test_hybrid_scope_and_temporal_reauthorization(self):
        from aams.recall import CognitiveMemory, CognitiveNeed

        class AxisProvider(DeterministicFixtureProvider):
            def encode(self, text):
                return (1.0, 0.0) if text in ("one", "secret", "similar") else (-1.0, 0.0)

        provider = AxisProvider(2)
        self.ingest(self.author, "one")
        self.ingest(self.other, "secret")
        self.index.rebuild(self.author, provider)
        self.index.rebuild(self.other, provider)
        memory = CognitiveMemory(self.store)
        need = CognitiveNeed(query="similar")
        self.assertFalse(memory.recall(self.author, need)["items"])
        hybrid = memory.recall(self.author, need, provider=provider)
        self.assertEqual(hybrid["retrieval"], {"mode": "hybrid", "status": "fresh"})
        self.assertEqual([item["id"] for item in hybrid["items"]], ["f-one"])
        self.assertEqual(hybrid["items"][0]["relevance"]["semantic_source"], "one")
        exact = CognitiveNeed(entity="formation", identifier="f-secret")
        self.assertEqual(
            memory.recall(self.author, exact, provider=provider), memory.recall(self.author, exact)
        )
        historical = CognitiveNeed(query="similar", recorded_as_of="2025-01-01T00:00:00Z")
        self.assertEqual(
            memory.recall(self.author, historical, provider=provider)["retrieval"]["status"],
            "no_match",
        )

    def test_hybrid_fallback_on_missing_stale_corrupt_and_provider_failure(self):
        from aams.recall import CognitiveMemory, CognitiveNeed

        class FailsQuery(DeterministicFixtureProvider):
            def encode(self, text):
                raise RuntimeError("Private exception details")

        self.ingest(self.author, "one")
        memory = CognitiveMemory(self.store)
        need = CognitiveNeed(query="one")

        def assert_fallback(provider, status):
            result = memory.recall(self.author, need, provider=provider)
            self.assertEqual(result.pop("retrieval"), {"mode": "lexical", "status": status})
            self.assertEqual(result, memory.recall(self.author, need))

        assert_fallback(self.provider, "missing")
        self.index.rebuild(self.author, self.provider)
        assert_fallback(DeterministicFixtureProvider(8), "missing")
        assert_fallback(FailsQuery(), "provider_unavailable")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE representation_vector SET checksum='invalid'")
        assert_fallback(self.provider, "corrupt")
        self.index.rebuild(self.author, self.provider)
        self.ingest(self.author, "new")
        assert_fallback(self.provider, "stale")

    def test_empty_batch_requires_valid_timestamp(self):
        self.assertEqual(self.index.rebuild(self.author, self.provider).vectors, ())
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE representation_batch SET generated_at='invalid'")
        self.assertEqual(self.index.snapshot(self.author, self.provider.spec).status, "corrupt")
        self.assertEqual(self.index.rebuild(self.author, self.provider).status, "fresh")

    def test_explicit_router_reports_actual_mode_and_skips_lexical_provider(self):
        from aams.recall import CognitiveMemory, CognitiveNeed
        from aams.retrieval_routing import RetrievalMode

        class ProviderMustNotRun:
            @property
            def spec(self):
                raise AssertionError("Lexical and exact routes skip the provider")

        self.ingest(self.author, "one")
        self.index.rebuild(self.author, self.provider)
        memory = CognitiveMemory(self.store)
        need = CognitiveNeed(query="one")
        lexical = memory.recall(
            self.author, need, provider=ProviderMustNotRun(), requested_mode=RetrievalMode.LEXICAL
        )
        self.assertEqual(
            lexical.pop("retrieval"),
            {"mode": "lexical", "status": "default_lexical", "policy": "1"},
        )
        self.assertEqual(lexical, memory.recall(self.author, need))
        hybrid = memory.recall(
            self.author, need, provider=self.provider, requested_mode=RetrievalMode.HYBRID
        )
        self.assertEqual(hybrid["retrieval"]["mode"], "hybrid")
        self.ingest(self.author, "new")
        stale = memory.recall(
            self.author, need, provider=self.provider, requested_mode=RetrievalMode.HYBRID
        )
        self.assertEqual(stale["retrieval"]["status"], "stale")
        self.assertEqual(stale["retrieval"]["mode"], "lexical")
        exact = memory.recall(
            self.author,
            CognitiveNeed(entity="formation", identifier="f-one"),
            provider=ProviderMustNotRun(),
            requested_mode=RetrievalMode.HYBRID,
        )
        self.assertEqual(exact["retrieval"]["status"], "exact_canonical")
        self.assertIsNone(self.store.get_belief(self.author, "one"))
        self.assertIsNone(self.store.get_candidate(self.author, "one"))

    def test_positive_telemetry_and_rollback_leave_canonical_history_unchanged(self):
        from dataclasses import replace

        from aams.contracts import BeliefProposal
        from aams.learning import LearningCandidate
        from aams.recall import CognitiveMemory, CognitiveNeed
        from aams.retrieval_routing import ROUTING_POLICY_VERSION, RetrievalMode
        from aams.retrieval_telemetry import (
            MeasuredOutcome,
            RetrievalObservation,
            RetrievalTelemetry,
        )

        self.ingest(self.author, "one")
        evidence = self.store.get_evidence(self.author, "one")
        self.store.revise(
            self.author,
            "belief",
            None,
            BeliefProposal(
                "One reported result",
                EpistemicState.INFERRED,
                "Fixture",
                TIME,
                support_ids=("one",),
            ),
        )
        history = self.store.belief_history(self.author, "belief")
        candidate = self.store.create_candidate(
            self.author,
            "candidate",
            LearningCandidate(
                "candidate",
                self.author.scope,
                self.author.principal,
                "One possible conclusion",
                TIME,
                ("one",),
            ),
        )
        memory = CognitiveMemory(self.store)
        need = CognitiveNeed(query="one")
        baseline = memory.recall(self.author, need)
        self.index.rebuild(self.author, self.provider)
        route = memory.recall(
            self.author, need, provider=self.provider, requested_mode=RetrievalMode.HYBRID
        )["retrieval"]
        self.assertEqual(route["mode"], "hybrid")
        telemetry = RetrievalTelemetry(self.store)
        grant = replace(self.author, telemetry=True)
        telemetry.record(
            grant,
            RetrievalObservation(
                "e" * 32, ROUTING_POLICY_VERSION, RetrievalMode.HYBRID, MeasuredOutcome.SATISFIED, 1
            ),
        )
        self.assertEqual(memory.recall(self.author, need), baseline)
        self.index.invalidate(self.author, self.provider.spec)
        result = memory.recall(
            self.author, need, provider=self.provider, requested_mode=RetrievalMode.HYBRID
        )
        self.assertEqual(result.pop("retrieval")["mode"], "lexical")
        self.assertEqual(result, baseline)
        self.assertEqual(self.store.get_evidence(self.author, "one"), evidence)
        self.assertEqual(self.store.belief_history(self.author, "belief"), history)
        self.assertEqual(self.store.get_candidate(self.author, "candidate"), candidate)
