"""Proposed checkpoint behavior is evaluated in disposable storage, not a product API."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from checkpoint_recovery_cases import RECIPE, cases, digest, oracle  # noqa: E402
from checkpoint_recovery_contract import canonical_state, decide, restore, restore_path  # noqa: E402
from evaluate_checkpoint_recovery import checked_inputs, evidence_digest, prepare, transcript_state  # noqa: E402
from aams.storage import AccessContext, SQLiteMemoryStore  # noqa: E402


class CheckpointRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.recipe = json.loads(RECIPE.read_text())
        self.episodes = [e for e in cases(self.recipe) if e["split"] == "design"]
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        prepare(self.directory, self.episodes)
        self.store = SQLiteMemoryStore(self.directory / "memory.db")

    def episode(self, family):
        return next(e for e in self.episodes if e["family"] == family)

    def access(self, episode):
        a = episode["authority"]
        return AccessContext(a["principal"], a["scope"])

    def registered(self, episode, checkpoint):
        authority = copy.deepcopy(episode["authority"])
        authority["registry"][checkpoint["checkpoint_id"]]["digest"] = digest(checkpoint)
        return authority

    def test_lifecycle_statuses_and_claims_do_not_become_completed_work(self):
        expected = {
            "ready": "ready",
            "truncated_transcript": "ready",
            "fabricated_progress": "contradictory",
            "changed_constraints": "stale",
            "expired": "expired",
            "superseded": "superseded",
            "revoked_checkpoint": "unavailable",
            "revoked_access": "unavailable",
            "cross_scope_ref": "unavailable",
            "contradictory_state": "contradictory",
            "future_reference": "unavailable",
            "wrong_digest": "unavailable",
        }
        before = evidence_digest(self.directory / "memory.db")
        for episode in self.episodes:
            with self.subTest(family=episode["family"]):
                restored = restore_path(
                    self.directory / (episode["id"] + ".json"),
                    self.store,
                    self.access(episode),
                    episode["authority"],
                )
                self.assertEqual(restored["status"], expected[episode["family"]])
                if restored["status"] != "ready":
                    self.assertIsNone(restored["state"])
                    self.assertEqual(restored["citations"], [])
                else:
                    self.assertEqual(restored["state"]["completed"], episode["world"]["completed"])
                    self.assertEqual(decide(restored, episode["authority"]), oracle(episode))
        self.assertEqual(before, evidence_digest(self.directory / "memory.db"))

    def test_authorization_before_file_existence_and_reference_reads(self):
        episode = self.episode("revoked_access")
        with (
            patch.object(Path, "open", side_effect=AssertionError("file existence disclosed")),
            patch.object(
                self.store,
                "get_evidence",
                side_effect=AssertionError("reference read before grant"),
            ),
        ):
            value = restore_path(
                self.directory / "missing", self.store, self.access(episode), episode["authority"]
            )
            self.assertEqual(value, {"status": "unavailable", "state": None, "citations": []})
        ready = self.episode("ready")
        for access in (
            AccessContext("other", ready["authority"]["scope"]),
            AccessContext(ready["authority"]["principal"], "foreign"),
        ):
            with patch.object(Path, "open", side_effect=AssertionError("foreign read")):
                self.assertEqual(
                    restore_path(
                        self.directory / "missing", self.store, access, ready["authority"]
                    ),
                    value,
                )

    def test_foreign_missing_revoked_and_bad_digest_have_identical_public_responses(self):
        episode = self.episode("cross_scope_ref")
        public = restore(
            episode["checkpoint"], self.store, self.access(episode), episode["authority"]
        )
        candidate = copy.deepcopy(episode["checkpoint"])
        candidate["evidence_refs"][-1]["scope"] = episode["authority"]["scope"]
        candidate["evidence_refs"][-1]["evidence_id"] = "not-present"
        self.assertEqual(
            restore(
                candidate, self.store, self.access(episode), self.registered(episode, candidate)
            ),
            public,
        )
        for family in ("wrong_digest", "revoked_checkpoint"):
            other = self.episode(family)
            self.assertEqual(
                restore(other["checkpoint"], self.store, self.access(other), other["authority"]),
                public,
            )
        self.assertEqual(public, {"status": "unavailable", "state": None, "citations": []})

    def test_registered_fabrication_and_self_asserted_types_fail_closed(self):
        episode = self.episode("ready")
        for field, value in [
            ("generation", True),
            ("task_revision", True),
            ("recorded_at", "2026-01-09T00:00:00Z"),
        ]:
            cp = copy.deepcopy(episode["checkpoint"])
            cp[field] = value
            self.assertNotEqual(
                restore(cp, self.store, self.access(episode), self.registered(episode, cp))[
                    "status"
                ],
                "ready",
            )
        cp = copy.deepcopy(episode["checkpoint"])
        cp["constraints"]["approval"] = 0
        self.assertEqual(
            restore(cp, self.store, self.access(episode), self.registered(episode, cp))["status"],
            "contradictory",
        )
        fabricated = self.episode("fabricated_progress")
        self.assertEqual(
            restore(
                fabricated["checkpoint"],
                self.store,
                self.access(fabricated),
                fabricated["authority"],
            )["status"],
            "contradictory",
        )

    def test_changed_constraints_and_conflicts_are_not_silently_rebased(self):
        changed = self.episode("changed_constraints")
        old = restore(changed["checkpoint"], self.store, self.access(changed), changed["authority"])
        self.assertEqual(old["status"], "stale")
        current = canonical_state(self.store, self.access(changed), changed["authority"])
        self.assertEqual(decide(current, changed["authority"]), "resolve:approval")
        conflict = self.episode("contradictory_state")
        self.assertEqual(
            canonical_state(self.store, self.access(conflict), conflict["authority"])["status"],
            "contradictory",
        )

    def test_transcript_truncation_is_separate_from_completion_oracle(self):
        episode = self.episode("truncated_transcript")
        state, ids = transcript_state(
            self.store, self.access(episode), episode["authority"], self.recipe
        )
        self.assertEqual(state["status"], "insufficient")
        self.assertLessEqual(len(ids), 8)
        altered = copy.deepcopy(episode)
        altered["world"]["completed"] = []
        self.assertNotEqual(oracle(altered), oracle(episode))
        restored = restore(
            episode["checkpoint"], self.store, self.access(episode), episode["authority"]
        )
        self.assertEqual(restored["state"]["completed"], episode["world"]["completed"])

    def test_preregistered_data_and_execution_pins(self):
        recipe, episodes = checked_inputs()
        self.assertEqual(len(episodes), 72)
        self.assertEqual(recipe["context_bytes"], 8192)
        with patch("evaluate_checkpoint_recovery.RECIPE") as path:
            path.read_bytes.return_value = b"{}"
            with self.assertRaisesRegex(ValueError, "checksum"):
                checked_inputs()

    def test_fresh_processes_report_rejections_and_unmeasured_model_honestly(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/evaluate_checkpoint_recovery.py")],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout[:500])
        report = json.loads(completed.stdout)
        expected_tasks = None
        for arm in report["arms"].values():
            tasks = [r["task_id"] for r in arm["rows"]]
            if expected_tasks is not None:
                self.assertEqual(tasks, expected_tasks)
            expected_tasks = tasks
            self.assertEqual(len(tasks), 72)
            self.assertNotEqual(arm["pid"], arm["prepare_pid"])
            self.assertTrue(arm["canonical_unchanged"])
            self.assertTrue(arm["sidecars_unchanged"])
            self.assertEqual(arm["evidence_digest_before"], arm["evidence_digest_after"])
            self.assertEqual(arm["summary"]["heldout"]["families"], 12)
            self.assertEqual(arm["summary"]["heldout"]["invented_progress"], 0)
        self.assertIn("NOT IMPLEMENTED", report["not_measured"]["product_persistence"])
        self.assertIn("NOT RUN", report["not_measured"]["model_replacement"])
        # No required benefit: conservative denial may lose against transcript reconstruction.


if __name__ == "__main__":
    unittest.main()
