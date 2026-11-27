"""Disposable #127 contract model. No application mutation or new storage API."""

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_learning import TIME, review, seed

from aams.learning import CandidateState, LearningCandidate
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.representations import DeterministicFixtureProvider
from aams.storage import AccessContext, SQLiteMemoryStore
from aams.vector_index import RepresentationIndex

ORIGIN = "opaque-origin-01"
TOKEN = "erasedpayload"


def encode(value):
    return json.dumps(value, sort_keys=True).encode()


def snapshot(source, destination):
    with (
        closing(sqlite3.connect(source)) as live,
        closing(sqlite3.connect(destination)) as copy,
    ):
        live.backup(copy)


class FenceUnavailable(RuntimeError):
    pass


class FixtureAuthority:
    """A trusted head and a separate journal, deliberately outside the backup domain."""

    def __init__(self, directory):
        self.directory = directory
        self.directory.mkdir()
        self.heads = {}
        for scope in ("A", "B"):
            self.publish(scope, [])

    def journal_path(self, scope):
        return self.directory / f"{scope}.json"

    def publish(self, scope, entries):
        raw = encode({"scope": scope, "epoch": len(entries), "entries": entries})
        path = self.journal_path(scope)
        pending = path.with_suffix(".pending")
        pending.write_bytes(raw)
        pending.replace(path)
        # Trusted test state stands in for a durable, independently obtained head.
        self.heads[scope] = sha256(raw).hexdigest()

    def read_fence(self, scope):
        try:
            raw = self.journal_path(scope).read_bytes()
        except OSError as exc:
            raise FenceUnavailable("Scope unavailable") from exc
        digest = sha256(raw).hexdigest()
        if self.heads.get(scope) != digest:
            raise FenceUnavailable("Scope unavailable")
        return json.loads(raw)["entries"], digest

    def erase(self, principal, scope, origin, request):
        if (principal, scope) != ("operator-a", "A"):
            raise PermissionError("Erasure denied")
        entries, _ = self.read_fence(scope)
        for index, entry in enumerate(entries, 1):
            if entry["request"] == request:
                if entry["origin"] != origin:
                    raise ValueError("Request conflict")
                return index
        self.publish(scope, [*entries, {"origin": origin, "request": request}])
        return len(entries) + 1


class FixtureView:
    """Build a new serving projection from the scoped, fenced fixture subset."""

    def __init__(self, directory, quarantined_file, authority, scope):
        entries, self.head = authority.read_fence(scope)
        erased = {entry["origin"] for entry in entries}
        self.authority = authority
        self.scope = scope
        self.access = AccessContext("reader", scope)
        self.provider = DeterministicFixtureProvider()
        quarantined = SQLiteMemoryStore(quarantined_file)
        quarantined.verify_integrity()
        rows, truncated = quarantined.sample_learning_evidence(
            self.access, since=TIME, through=TIME, limit=32
        )
        if truncated:
            raise ValueError("Incomplete fixture")
        # The fixture's source_actor is a stand-in for a trusted origin key.
        survivors = {r.evidence_id: r for r in rows if r.source_actor not in erased}
        directory.mkdir()
        self.store = SQLiteMemoryStore(directory / "clean.sqlite")
        seed(
            self.store,
            {
                "evidence": [
                    (
                        r.evidence_id,
                        scope,
                        r.producer,
                        r.source_actor,
                        r.source_locator,
                        r.payload.decode(),
                    )
                    for r in survivors.values()
                ]
            },
        )
        self.lessons = {}
        for name in ("single", "multi", "survivors-only"):
            candidate = quarantined.get_candidate(self.access, name)
            if candidate is not None:
                proposal = candidate.proposal
                refs = set(proposal.support_ids) | set(proposal.refute_ids)
                if refs <= survivors.keys() and candidate.state is CandidateState.APPROVED:
                    self.lessons[name] = proposal.claim

        # One vetted historical sidecar is simulated explicitly. Native approval
        # requires two independent supports and cannot produce this legacy entry.
        if scope == "A" and "primary" in survivors:
            self.lessons["legacy-single"] = f"{TOKEN} single-source summary"

        self.memory = CognitiveMemory(self.store)
        self.index = RepresentationIndex(self.store)
        self.index.rebuild(AccessContext("builder", scope, True), self.provider)
        self.check()

    def check(self):
        _, head = self.authority.read_fence(self.scope)
        if head != self.head:
            raise FenceUnavailable("Scope unavailable")

    def evidence(self, identifier):
        self.check()
        return self.store.get_evidence(self.access, identifier)

    def lesson(self, identifier):
        self.check()
        return self.lessons.get(identifier)

    def recall(self, query):
        self.check()
        return self.memory.recall(self.access, CognitiveNeed(query=query))

    def vector_ids(self):
        self.check()
        return {
            row.source_id for row in self.index.snapshot(self.access, self.provider.spec).vectors
        }


class ErasureRestoreContractTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.live = self.root / "live.sqlite"
        self.backup = self.root / "old.sqlite"
        self.authority = FixtureAuthority(self.root / "outside-backup")
        store = SQLiteMemoryStore(self.live)
        seed(
            store,
            {
                "evidence": [
                    ("primary", "A", "sensor-a", ORIGIN, "fixture:primary", TOKEN),
                    ("copy", "A", "sensor-copy", ORIGIN, "fixture:copy", TOKEN + " copy"),
                    ("other", "A", "sensor-b", "support-origin-02", "fixture:other", "retainalpha"),
                    ("third", "A", "sensor-c", "support-origin-03", "fixture:third", "retainbeta"),
                    ("primary", "B", "sensor-private", ORIGIN, "fixture:private", "foreignpayload"),
                ]
            },
        )
        self.create_lesson(store, "single", ("primary",), f"{TOKEN} staged draft", approved=False)
        self.create_lesson(
            store, "multi", ("primary", "other", "third"), f"{TOKEN} reviewed lesson"
        )
        index = RepresentationIndex(store)
        index.rebuild(AccessContext("builder", "A", True), DeterministicFixtureProvider())
        snapshot(self.live, self.backup)

    def create_lesson(self, store, name, supports, claim, *, approved=True):
        author = AccessContext("author", "A", True)
        candidate = LearningCandidate(name, "A", author.principal, claim, TIME, supports)
        store.create_candidate(author, name, candidate)
        result = review(store, candidate, AccessContext("reviewer", "A", True, True))
        self.assertEqual(result, approved)

    def view(self, name, source, scope="A"):
        return FixtureView(self.root / name, source, self.authority, scope)

    def assert_erased(self, view):
        for identifier in ("primary", "copy"):
            self.assertIsNone(view.evidence(identifier))
        for identifier in ("legacy-single", "multi"):
            self.assertIsNone(view.lesson(identifier))
        self.assertEqual(view.recall(TOKEN)["items"], [])
        self.assertEqual(view.vector_ids(), {"other", "third"})
        self.assertEqual(view.evidence("other").payload, b"retainalpha")

    def test_snapshot_cannot_resurrect_sources_or_old_lessons(self):
        original = self.view("original", self.live)
        self.assertEqual(original.evidence("primary").payload, TOKEN.encode())
        self.assertIsNotNone(original.evidence("copy"))
        self.assertIn(TOKEN, original.lesson("legacy-single"))
        self.assertIsNone(original.lesson("single"))
        self.assertIn(TOKEN, original.lesson("multi"))
        self.assertTrue(original.recall(TOKEN)["items"])
        self.assertEqual(original.vector_ids(), {"primary", "copy", "other", "third"})
        # Scope permissions precede all journal mutation.
        for principal, scope in (("reader", "A"), ("operator-a", "B")):
            with self.assertRaises(PermissionError):
                self.authority.erase(principal, scope, ORIGIN, "replica-purge")
        self.assertEqual(self.authority.read_fence("A")[0], [])
        self.assertEqual(self.authority.read_fence("B")[0], [])
        receipt = self.authority.erase("operator-a", "A", ORIGIN, "replica-purge")
        first = self.authority.journal_path("A").read_bytes()
        self.assertEqual(self.authority.erase("operator-a", "A", ORIGIN, "replica-purge"), receipt)
        self.assertEqual(self.authority.journal_path("A").read_bytes(), first)
        with self.assertRaisesRegex(ValueError, "Request conflict"):
            self.authority.erase("operator-a", "A", "different-origin", "replica-purge")
        self.assertNotIn(TOKEN.encode(), first)
        with self.assertRaises(FenceUnavailable):
            original.recall(TOKEN)

        self.assert_erased(self.view("after", self.live))
        restored = self.root / "restored.sqlite"
        snapshot(self.backup, restored)
        raw = SQLiteMemoryStore(restored)
        self.assertEqual(
            raw.get_evidence(AccessContext("reader", "A"), "primary").payload, TOKEN.encode()
        )
        self.assertEqual(
            raw.get_candidate(AccessContext("reader", "A"), "multi").state, CandidateState.APPROVED
        )
        self.assertIn(
            "primary",
            {
                v.source_id
                for v in RepresentationIndex(raw)
                .snapshot(AccessContext("reader", "A"), DeterministicFixtureProvider().spec)
                .vectors
            },
        )
        self.assert_erased(self.view("after-restore", restored))

        foreign = self.view("foreign", restored, "B")
        self.assertEqual(foreign.evidence("primary").payload, b"foreignpayload")
        self.assertTrue(foreign.recall("foreignpayload")["items"])
        self.assertEqual(foreign.vector_ids(), {"primary"})

        self.create_lesson(raw, "survivors-only", ("other", "third"), "independent revised lesson")
        refreshed = self.view("re-reviewed", restored)
        self.assert_erased(refreshed)
        self.assertEqual(refreshed.lesson("survivors-only"), "independent revised lesson")

    def test_missing_stale_or_changed_fence_fails_closed(self):
        path = self.authority.journal_path("A")
        obsolete = path.read_bytes()
        self.authority.erase("operator-a", "A", ORIGIN, "request-1")
        current = path.read_bytes()
        path.unlink()
        with self.assertRaises(FenceUnavailable):
            self.view("missing", self.backup)
        path.write_bytes(obsolete)
        with self.assertRaises(FenceUnavailable):
            self.view("stale", self.backup)
        path.write_bytes(current + b" ")
        with self.assertRaises(FenceUnavailable):
            self.view("changed", self.backup)
        self.assertEqual(self.view("available-b", self.backup, "B").vector_ids(), {"primary"})

    def test_view_binds_to_the_head_of_the_entries_it_filtered(self):
        read_fence = self.authority.read_fence
        advanced = False

        def advance_after_first_read(scope):
            nonlocal advanced
            verified = read_fence(scope)
            if not advanced:
                advanced = True
                self.authority.erase("operator-a", "A", ORIGIN, "race-at-read")
            return verified

        with patch.object(self.authority, "read_fence", side_effect=advance_after_first_read):
            with self.assertRaises(FenceUnavailable):
                self.view("raced-read", self.backup)
        self.assert_erased(self.view("retry-read", self.backup))

    def test_view_rejects_a_fence_that_advances_during_index_rebuild(self):
        rebuild = RepresentationIndex.rebuild

        def advance_during_rebuild(index, access, provider):
            self.authority.erase("operator-a", "A", ORIGIN, "race-at-rebuild")
            return rebuild(index, access, provider)

        with patch.object(
            RepresentationIndex, "rebuild", autospec=True, side_effect=advance_during_rebuild
        ):
            with self.assertRaises(FenceUnavailable):
                self.view("raced-rebuild", self.backup)
        self.assert_erased(self.view("retry-rebuild", self.backup))
