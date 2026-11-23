"""Basic contract invariants for the bootstrap; not storage acceptance tests."""

import unittest
from dataclasses import FrozenInstanceError

from aams.contracts import EpistemicState, EvidenceReference, MemoryFormation, MemoryKind


class ContractsTest(unittest.TestCase):
    def test_evidence_requires_source_and_digest(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceReference("ev-1", "agent:a", "", "sha256:abc")

    def test_formation_needs_evidence(self) -> None:
        with self.assertRaises(ValueError):
            MemoryFormation(
                "mem-1", "agent:a", MemoryKind.EXPERIENCE, (), "agent:a",
                "2026-11-22T20:00:00Z", EpistemicState.OBSERVED,
            )

    def test_formation_cannot_repeat_evidence(self) -> None:
        with self.assertRaises(ValueError):
            MemoryFormation(
                "mem-1", "agent:a", MemoryKind.EXPERIENCE, ("ev-1", "ev-1"),
                "agent:a", "2026-11-22T20:00:00Z", EpistemicState.OBSERVED,
            )

    def test_formation_is_immutable(self) -> None:
        record = MemoryFormation(
            "mem-1", "agent:a", MemoryKind.EXPERIENCE, ("ev-1",),
            "agent:a", "2026-11-22T20:00:00Z", EpistemicState.OBSERVED,
        )
        with self.assertRaises(FrozenInstanceError):
            record.scope = "agent:b"


if __name__ == "__main__":
    unittest.main()
