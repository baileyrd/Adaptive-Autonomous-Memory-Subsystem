"""Trust-boundary and fresh-process checks for the disposable restart control."""

import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_agent_restart import (  # noqa: E402
    Reader,
    actor,
    checkpoint,
    digest,
    eligible,
    manifest,
    prepare,
    restore,
    retrieve,
    validate,
)
from restart_agent_cases import cases, verify_separation  # noqa: E402
from restart_agent_policy import INSTRUCTION, decide  # noqa: E402


class AgentRestartTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.batch = [e for e in cases() if e["split"] == "design"]
        prepare(self.directory, self.batch)
        self.store = Reader(self.directory / "memory.db")

    def fixture(self, family):
        return copy.deepcopy(next(e for e in self.batch if e["family"] == family))

    def test_denial_precedes_sidecar_and_canonical_reads(self):
        task = self.fixture("unauthorized")["request"]
        with (
            patch.object(Path, "open", side_effect=AssertionError("file probe")),
            patch.object(self.store, "scan_recall", side_effect=AssertionError("canonical probe")),
            patch.object(self.store, "get_evidence", side_effect=AssertionError("source probe")),
        ):
            self.assertEqual(
                restore(self.directory, self.store, task, "unused"), ([], "unavailable")
            )
            self.assertEqual(
                retrieve(self.directory, self.store, task, "checkpoint", "unused")[0], []
            )

    def test_checkpoint_uses_only_preinterruption_sources_and_rejects_fabrication(self):
        e = self.fixture("delayed")
        cp = checkpoint(self.store, e["request"], e["expires_at"])
        self.assertEqual(cp["evidence_refs"][0]["evidence_id"], e["id"] + "-initial")
        cp["interpretation"]["completed"] = ["prepare", "verify", "publish"]
        path = self.directory / (e["id"] + ".json")
        path.write_text(json.dumps(cp))
        # Even recognizing the modified proposal does not make its progress authoritative.
        self.assertEqual(
            restore(self.directory, self.store, e["request"], digest(cp)), ([], "unavailable")
        )

    def test_expired_foreign_and_time_bounded_sources(self):
        registry = json.loads((self.directory / "registry.json").read_bytes())
        for family in ("expired", "cross_scope"):
            e = self.fixture(family)
            self.assertEqual(
                restore(self.directory, self.store, e["request"], registry[e["id"]]),
                ([], "unavailable"),
            )
            context, _, _ = retrieve(
                self.directory, self.store, e["request"], "checkpoint", registry[e["id"]]
            )
            self.assertTrue(context)  # Rejection does not revoke independently readable evidence.
            validate(self.store, e["request"], context)
        task = self.fixture("partial")["request"]
        ids = {r["evidence_id"] for r in eligible(self.store, task)}
        self.assertFalse(
            any(x.endswith(("foreign", "future-recorded", "future-effective")) for x in ids)
        )
        task["effective_at"] = "2026-01-02T00:00:00.000000+00:00"
        self.assertEqual(
            {r["evidence_id"] for r in eligible(self.store, task)}, {task["task_id"] + "-initial"}
        )

    def test_actual_policy_process_and_read_only_integrity(self):
        e = self.fixture("prior_failure")
        context = [
            r
            for r in eligible(self.store, e["request"])
            if r["evidence_id"] == e["id"] + "-current"
        ]
        packet = {"instruction": INSTRUCTION, "task": e["request"], "context": context}
        before = manifest(self.directory)
        first, second = actor(packet), actor(packet)
        self.assertNotEqual(first.pop("agent_pid"), second.pop("agent_pid"))
        self.assertEqual(first, second)
        self.assertEqual(first["action"], "repair")
        context[0]["preview"] = json.dumps(
            {**json.loads(context[0]["preview"]), "failed_attempts": []}
        )
        self.assertEqual(decide(packet)["action"], "verify")
        self.assertEqual(before, manifest(self.directory))
        with self.store._connect() as db:
            with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                db.execute("CREATE TABLE should_not_exist (id INTEGER)")

    def test_split_separation_and_no_label_fields_in_inputs(self):
        verify_separation(cases())
        for e in cases():
            self.assertFalse({"expected", "action", "world", "labels"} & set(e))


if __name__ == "__main__":
    unittest.main()
