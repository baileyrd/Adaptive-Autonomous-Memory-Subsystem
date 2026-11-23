import tempfile
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch

from aams.contracts import EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind
from aams.offline_candidate import FeatureBin, StagedRoutingCandidate
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.retrieval_routing import RetrievalMode
from aams.shadow import ShadowConfig, ShadowMode
from aams.shadow_observer import ShadowObserver
from aams.storage import AccessContext, SQLiteMemoryStore

TIME = "2026-01-01T00:00:00Z"


class ShadowObserverTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = SQLiteMemoryStore(Path(directory.name) / "test.db")
        self.access = AccessContext("host", "lab", True, shadow_observe=True)
        payload = b"rain likely"
        record = Evidence(
            "e",
            "lab",
            "station",
            "fixture",
            "host",
            TIME,
            TIME,
            EvidenceStatus.RECORDED,
            payload,
            "sha256:" + sha256(payload).hexdigest(),
        )
        formation = MemoryFormation(
            "f",
            "lab",
            MemoryKind.EXPERIENCE,
            ("e",),
            "host",
            TIME,
            EpistemicState.OBSERVED,
        )
        self.store.ingest(self.access, "key", formation, (record,))
        self.artifact = StagedRoutingCandidate("sha256:" + "a" * 64, (FeatureBin(True, 2, 2, 0),))
        self.need = CognitiveNeed(query="rain")

    def wait_result(self, observer):
        deadline = monotonic() + 3
        while monotonic() < deadline:
            observations = observer.observations(self.access)
            if observations:
                return observations[0]
            sleep(0.001)
        self.fail("Shadow worker did not publish")

    def test_authorized_opt_in_and_redacted_inputs_after_serving(self):
        observer = ShadowObserver(
            self.access, ShadowConfig(ShadowMode.OBSERVE_ONLY, 1), self.artifact, timeout_ms=1000
        )
        memory = CognitiveMemory(self.store, shadow=observer)
        for access in (
            replace(self.access, shadow_observe=False),
            replace(self.access, scope="elsewhere"),
            replace(self.access, principal="different"),
        ):
            memory.recall(access, self.need)
            with self.assertRaises(PermissionError):
                observer.observations(access)
        memory.recall(self.access, CognitiveNeed(query="unknown"))
        self.assertEqual(observer.observations(self.access), ())
        expected = CognitiveMemory(self.store).recall(
            self.access, self.need, requested_mode=RetrievalMode.HYBRID
        )
        with patch("aams.shadow_observer._suggest", return_value="hybrid") as evaluate:
            self.assertEqual(
                memory.recall(self.access, self.need, requested_mode=RetrievalMode.HYBRID), expected
            )
            observation = self.wait_result(observer)
            self.assertTrue(observation.success)
            self.assertEqual(evaluate.call_args.args, (frozenset({True}), True, True))
        self.assertNotEqual(observation.intent.scope_id, self.access.scope)
        self.assertNotIn(self.need.query, repr(observation))
        memory.recall(self.access, self.need)
        self.assertEqual(len(observer.observations(self.access)), 1)
        self.assertIsNotNone(self.store.get_evidence(self.access, "e"))

    def test_disabled_and_slow_error_isolation(self):
        disabled = ShadowObserver(self.access, ShadowConfig(), self.artifact)
        CognitiveMemory(self.store, shadow=disabled).recall(self.access, self.need)
        self.assertEqual(disabled.observations(self.access), ())
        observer = ShadowObserver(
            self.access, ShadowConfig(ShadowMode.OBSERVE_ONLY, 3), self.artifact, timeout_ms=5
        )
        memory = CognitiveMemory(self.store, shadow=observer)
        expected = CognitiveMemory(self.store).recall(self.access, self.need)
        started, finish = Event(), Event()

        def blocked(*flags):
            started.set()
            finish.wait(2)
            raise ValueError("observer error")

        with patch("aams.shadow_observer._suggest", side_effect=blocked) as evaluate:
            try:
                self.assertEqual(memory.recall(self.access, self.need), expected)
                self.assertTrue(started.wait(1))
                self.assertEqual(observer.observations(self.access), ())
                self.assertEqual(memory.recall(self.access, self.need), expected)
                self.assertEqual(evaluate.call_count, 1)
                sleep(0.015)
            finally:
                finish.set()
            self.assertFalse(self.wait_result(observer).success)

    def test_late_success_is_discarded_and_observation_can_be_disabled(self):
        observer = ShadowObserver(
            self.access, ShadowConfig(ShadowMode.OBSERVE_ONLY, 1), self.artifact, timeout_ms=5
        )
        memory = CognitiveMemory(self.store, shadow=observer)
        expected = CognitiveMemory(self.store).recall(self.access, self.need)
        before = self.store.path.read_bytes()
        started, finish = Event(), Event()

        def finishes_late(*flags):
            started.set()
            finish.wait(2)
            return "hybrid"

        with patch("aams.shadow_observer._suggest", side_effect=finishes_late):
            try:
                self.assertEqual(memory.recall(self.access, self.need), expected)
                self.assertTrue(started.wait(1))
                sleep(0.015)
            finally:
                finish.set()
            observation = self.wait_result(observer)
            self.assertFalse(observation.success)
            self.assertEqual(observation.proposed_mode, "lexical")
        revoked = replace(self.access, shadow_observe=False)
        self.assertEqual(memory.recall(revoked, self.need), expected)
        self.assertEqual(CognitiveMemory(self.store).recall(self.access, self.need), expected)
        self.assertEqual(self.store.path.read_bytes(), before)
