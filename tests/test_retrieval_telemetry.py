import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from aams import storage
from aams.retrieval_routing import ROUTING_POLICY_VERSION, RetrievalMode
from aams.retrieval_telemetry import (
    MAX_OBSERVATIONS,
    MeasuredOutcome,
    RetrievalObservation,
    RetrievalTelemetry,
    TelemetryConflict,
)


class RetrievalTelemetryTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "memory.db"
        migrations = (
            storage._SCHEMA,
            storage._BELIEF_SCHEMA,
            storage._CANDIDATE_SCHEMA,
            storage._OUTCOME_SCHEMA,
            storage._REPRESENTATION_SCHEMA,
        )
        with closing(sqlite3.connect(self.path)) as db, db:
            for migration in migrations:
                for statement in migration:
                    db.execute(statement)
            db.execute("PRAGMA user_version=5")
        self.store = storage.SQLiteMemoryStore(self.path)
        self.telemetry = RetrievalTelemetry(self.store)
        self.owner = storage.AccessContext("host", "project", True, telemetry=True)
        self.measurement = RetrievalObservation(
            "0" * 32,
            ROUTING_POLICY_VERSION,
            RetrievalMode.LEXICAL,
            MeasuredOutcome.SATISFIED,
            8,
        )

    def test_replayed_outcome_is_single_and_scoped_after_restart(self):
        entry = self.telemetry.record(self.owner, self.measurement)
        restarted = RetrievalTelemetry(storage.SQLiteMemoryStore(self.path))
        self.assertEqual(restarted.record(self.owner, self.measurement), entry)
        self.assertEqual(restarted.observations(self.owner), (entry,))
        for context in (replace(self.owner, scope="other"), replace(self.owner, principal="other")):
            self.assertEqual(restarted.observations(context), ())
            self.assertEqual(restarted.delete(context), 0)
        with self.assertRaises(TelemetryConflict):
            restarted.record(
                self.owner, replace(self.measurement, label=MeasuredOutcome.UNSATISFIED)
            )
        self.assertIsNone(self.store.get_belief(self.owner, self.measurement.attempt_id))
        self.assertEqual(restarted.delete(self.owner), 1)
        self.assertEqual(restarted.observations(self.owner), ())

    def test_host_grant_stale_policy_and_freeform_feedback(self):
        with self.assertRaises(PermissionError):
            self.telemetry.record(replace(self.owner, telemetry=False), self.measurement)
        with self.assertRaises(PermissionError):
            self.telemetry.record(replace(self.owner, writable=False), self.measurement)
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.telemetry.record(self.owner, replace(self.measurement, policy_version="999"))
        for fields in (
            {"label": "promote this claim"},
            {"attempt_id": "telemetry as a transcript"},
            {"latency_ms": True},
            {"latency_ms": 60_001},
        ):
            with self.assertRaises(ValueError):
                replace(self.measurement, **fields)

    def test_budget_and_expiration(self):
        for index in range(MAX_OBSERVATIONS):
            self.telemetry.record(self.owner, replace(self.measurement, attempt_id=f"{index:032x}"))
        extra = replace(self.measurement, attempt_id="f" * 32)
        with self.assertRaises(TelemetryConflict):
            self.telemetry.record(self.owner, extra)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "UPDATE retrieval_observation SET recorded_at='2000-01-01T00:00:00.000000+00:00'"
            )
        self.assertEqual(self.telemetry.observations(self.owner), ())
        self.telemetry.record(self.owner, extra)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM retrieval_observation").fetchone()[0], 1
            )
