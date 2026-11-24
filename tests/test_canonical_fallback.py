"""Bounded contract checks for the disposable canonical fallback experiment."""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_canonical_fallback import Reader, attempt, audit, frozen_inputs, prepare  # noqa: E402


class FallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.fixtures = {e["family"]: e for e in frozen_inputs() if e["split"] == "design"}
        prepare(self.directory, self.fixtures.values())
        self.store = Reader(self.directory / "memory.db")

    def attempt(self, family: str) -> tuple:
        e = self.fixtures[family]
        return attempt(
            "fallback", self.directory / (e["id"] + ".json"), self.store, e["authority"], e["fresh"]
        )

    def test_reopen_read_only(self) -> None:
        db = self.store._connect()
        self.addCleanup(db.close)
        with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
            db.execute("CREATE TABLE attempted_write (id INTEGER)")

    def test_fresh_denial_stops_new_lookup(self) -> None:
        state, first, second, reads = self.attempt("revoked_between")
        self.assertEqual((first, second, reads), ("expired", True, 0))
        self.assertEqual(state, {"status": "unavailable", "state": None, "citations": []})
        with patch.object(Path, "open", side_effect=AssertionError):
            self.assertFalse(self.attempt("revoked_access")[2])

    def test_trusted_request_binding_and_time_bounds(self) -> None:
        e = self.fixtures["head_after_cutoff"]
        e["fresh"]["as_of"] = e["fresh"]["now"]
        self.assertEqual(self.attempt("head_after_cutoff")[0]["status"], "unavailable")
        e = self.fixtures["expired"]
        e["fresh"]["task_id"] = "another-task"
        self.assertEqual(self.attempt("expired")[3], 0)

    def test_rejected_claim_is_discarded(self) -> None:
        state, _, _, _ = self.attempt("fabricated_progress")
        e = self.fixtures["fabricated_progress"]
        self.assertEqual(state["state"]["completed"], e["world"]["completed"])
        self.assertNotEqual(state["state"]["completed"], e["checkpoint"]["completed"])
        tampered = json.loads(json.dumps(state))
        tampered["citations"][0]["digest"] = "invalid"
        with self.assertRaisesRegex(ValueError, "Invalid returned citation"):
            audit(e, tampered, "canonical", self.store, 1)
