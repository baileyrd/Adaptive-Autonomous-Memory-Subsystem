"""Model-free verification of the published first run and replay."""

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_seal_room import inspect  # noqa: E402


class PublishedQualificationTests(unittest.TestCase):
    def test_paired_evidence(self):
        reports = []
        for name, checksum in (
            ("first", "d9f8e147270894d596587c203e600d34e803c5ec03154cac3874a73353bf623a"),
            ("replay", "5a4391711f4e02f90eb64d4751d895263439a07b77a454858f3bedb1f0424bbe"),
        ):
            path = ROOT / "docs/audit" / f"seal-room-{name}.jsonl"
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), checksum)
            with path.open() as stream:
                self.assertEqual(
                    json.loads(next(stream))["source"], "6bdd6e9262374b774dd18f917f69e9e71e34f3d4"
                )
            reports.append(inspect(path))
        self.assertEqual(*reports)
        self.assertEqual(
            reports[0]["gate"],
            dict(event="gate", trials=20, correct=4, paired_correct=0, qualified=False),
        )
