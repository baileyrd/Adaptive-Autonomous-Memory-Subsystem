"""Contracts only: derived vectors never provide independent evidence."""

import unittest
from dataclasses import FrozenInstanceError
from hashlib import sha256

from aams.representations import (
    DerivedVector,
    DeterministicFixtureProvider,
    RepresentationProvider,
    RepresentationSpec,
    create_derived_vector,
)

STAMP = "2026-11-23T12:00:00Z"
DIGEST = "sha256:" + sha256(b"source").hexdigest()


class RepresentationContractsTest(unittest.TestCase):
    def test_fixture_provider_is_deterministic_but_not_semantic(self):
        provider = DeterministicFixtureProvider(8)
        self.assertIsInstance(provider, RepresentationProvider)
        self.assertEqual(provider.encode("abc"), provider.encode("abc"))
        self.assertEqual(len(provider.encode("abc")), 8)
        self.assertEqual(provider.encode(""), (0.0,) * 8)
        self.assertEqual(provider.spec.provider_id, "aams-test")
        self.assertEqual(provider.spec.model_version, "1")

    def test_source_bound_vector_and_immutability(self):
        provider = DeterministicFixtureProvider(8)
        vector = create_derived_vector(
            provider,
            source_id="ev-1",
            scope="scope:a",
            source_payload=b"source",
            text="source",
            generated_at=STAMP,
        )
        self.assertEqual(vector.source_digest, DIGEST)
        self.assertEqual(vector.generated_at, "2026-11-23T12:00:00.000000+00:00")
        self.assertEqual(vector.spec, provider.spec)
        self.assertEqual(vector.values, provider.encode("source"))
        with self.assertRaises(FrozenInstanceError):
            vector.scope = "scope:b"

    def test_bad_specification_rejected(self):
        for kwargs in (
            {"provider_id": ""},
            {"model_id": " "},
            {"model_version": ""},
            {"dimensions": 0},
            {"dimensions": -1},
            {"dimensions": True},
            {"dimensions": 65537},
            {"dimensions": 2.5},
        ):
            fields = dict(provider_id="p", model_id="m", model_version="1", dimensions=8)
            fields.update(kwargs)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                RepresentationSpec(**fields)

    def test_invalid_vectors_rejected(self):
        spec = RepresentationSpec("p", "m", "1", 2)
        base = dict(
            source_id="ev-1",
            scope="scope:a",
            source_digest=DIGEST,
            generated_at=STAMP,
            spec=spec,
            values=(1.0, 0.0),
        )
        for changes in (
            {"values": (1.0,)},
            {"values": [1.0, 0.0]},
            {"values": (float("nan"), 0.0)},
            {"values": (float("inf"), 0.0)},
            {"values": (1, 0.0)},
            {"source_id": ""},
            {"scope": ""},
            {"source_digest": "sha256:abc"},
            {"source_digest": "sha256:" + "G" * 64},
            {"generated_at": "2026-11-23T12:00:00"},
            {"spec": None},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                DerivedVector(**(base | changes))

    def test_provider_validation(self):
        provider = DeterministicFixtureProvider(2)
        with self.assertRaises(ValueError):
            provider.encode(b"not-text")
        with self.assertRaises(ValueError):
            create_derived_vector(
                provider,
                source_id="ev-1",
                scope="scope:a",
                source_payload="not-bytes",
                text="test",
                generated_at=STAMP,
            )

    def test_no_authority_or_mutation_operations(self):
        provider = DeterministicFixtureProvider()
        self.assertFalse(hasattr(provider, "promote"))
        self.assertFalse(hasattr(provider, "write_evidence"))
        self.assertFalse(hasattr(provider, "revise"))
        self.assertFalse(hasattr(provider, "delete"))


if __name__ == "__main__":
    unittest.main()
