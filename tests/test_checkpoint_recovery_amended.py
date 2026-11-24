"""Post-review contract regressions, separate from the preregistered quality sample."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from checkpoint_recovery_amended import restore_path  # noqa: E402
from checkpoint_recovery_cases import RECIPE, cases, day, digest  # noqa: E402
from evaluate_checkpoint_recovery import prepare  # noqa: E402
from aams.storage import AccessContext, SQLiteMemoryStore  # noqa: E402


class AmendedContractTests(unittest.TestCase):
    def setUp(self) -> None:
        episodes = cases(json.loads(RECIPE.read_text()))
        self.episodes = {e["family"]: e for e in episodes if e["split"] == "design"}
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        prepare(self.directory, self.episodes.values())
        self.store = SQLiteMemoryStore(self.directory / "memory.db")
        for episode in self.episodes.values():
            host = episode["authority"]
            host["owner"] = host["principal"]
            host["readers"].append("second-reader")
            self.entry(episode)["registered_at"] = day(4)

    def entry(self, episode: dict) -> dict:
        return episode["authority"]["registry"][episode["checkpoint"]["checkpoint_id"]]

    def read(self, episode: dict, principal: str | None = None) -> dict:
        host = episode["authority"]
        access = AccessContext(principal or host["principal"], host["scope"])
        return restore_path(self.directory / (episode["id"] + ".json"), self.store, access, host)

    def assert_denied(self, value: dict) -> None:
        self.assertEqual(value, {"status": "unavailable", "state": None, "citations": []})

    def test_host_registration_time_bounds_every_lifecycle_state(self) -> None:
        for family in ("ready", "expired", "superseded"):
            with self.subTest(family=family):
                episode = self.episodes[family]
                episode["authority"]["as_of"] = day(3)
                with patch.object(self.store, "get_evidence", side_effect=AssertionError):
                    self.assert_denied(self.read(episode))
                episode["authority"]["as_of"] = day(4)
                self.assertEqual(self.read(episode)["status"], family)
                del self.entry(episode)["registered_at"]
                self.assert_denied(self.read(episode))

    def test_malformed_or_future_registration_fails_closed(self) -> None:
        episode = self.episodes["ready"]
        episode["authority"]["as_of"] = day(9)
        for timestamp in (None, "invalid", day(2), day(7)):
            with self.subTest(timestamp=timestamp):
                self.entry(episode)["registered_at"] = timestamp
                self.assert_denied(self.read(episode))

    def test_owner_and_reader_statuses(self) -> None:
        for family, reason in (
            ("ready", "ready"),
            ("expired", "expired"),
            ("superseded", "superseded"),
            ("changed_constraints", "stale"),
            ("contradictory_state", "contradictory"),
        ):
            with self.subTest(family=family):
                episode = self.episodes[family]
                owner = self.read(episode)
                self.assertEqual(owner["status"], reason)
                reader = self.read(episode, "second-reader")
                if family == "ready":
                    self.assertEqual(owner, reader)
                else:
                    self.assert_denied(reader)
        with patch.object(Path, "open", side_effect=AssertionError):
            self.assert_denied(self.read(self.episodes["revoked_access"]))

    def test_invalid_reference_precedes_expiry_and_supersession(self) -> None:
        for family in ("cross_scope_ref", "wrong_digest", "future_reference"):
            episode = self.episodes[family]
            host = episode["authority"]
            for generation in (1, 2):
                with self.subTest(family=family, generation=generation):
                    host["now"] = day(8)
                    host["active_generation"] = generation
                    self.assert_denied(self.read(episode))

    def test_schema_time_and_revocation_precede_lifecycle_details(self) -> None:
        episode = self.episodes["superseded"]
        host = episode["authority"]
        host["effective_at"] = day(2)
        self.assert_denied(self.read(episode))
        host["effective_at"] = day(6)
        entry = self.entry(episode)
        entry["revoked"] = True
        self.assert_denied(self.read(episode))
        entry["revoked"] = False
        episode["checkpoint"]["schema"] = "unknown"
        entry["digest"] = digest(episode["checkpoint"])
        (self.directory / (episode["id"] + ".json")).write_text(json.dumps(episode["checkpoint"]))
        self.assert_denied(self.read(episode))
