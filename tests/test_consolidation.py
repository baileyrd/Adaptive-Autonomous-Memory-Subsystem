import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from aams.consolidation import propose
from aams.contracts import EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind
from aams.storage import AccessContext, SQLiteMemoryStore

TIME = "2026-01-01T00:00:00Z"


class ConsolidationTest(unittest.TestCase):
    def test_fixture_bounds_and_staging(self):
        fixture = json.loads(
            Path(__file__).with_name("fixtures").joinpath("consolidation.json").read_text()
        )
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteMemoryStore(Path(directory) / "memory.db")
            for identity, scope, actor, locator, text in fixture["evidence"]:
                access = AccessContext("collector", scope, True)
                payload = text.encode()
                record = Evidence(
                    identity,
                    scope,
                    actor,
                    locator,
                    access.principal,
                    TIME,
                    TIME,
                    EvidenceStatus.RECORDED,
                    payload,
                    "sha256:" + sha256(payload).hexdigest(),
                )
                formation = MemoryFormation(
                    "f-" + identity,
                    scope,
                    MemoryKind.EXPERIENCE,
                    (identity,),
                    access.principal,
                    TIME,
                    EpistemicState.OBSERVED,
                )
                store.ingest(access, identity, formation, (record,))
            proposer = AccessContext("proposer", "work", True)
            batch = propose(store, proposer, since=TIME, through=TIME)
            self.assertEqual(batch, propose(store, proposer, since=TIME, through=TIME))
            self.assertFalse(batch.truncated)
            actual = {
                item.claim: {"support": list(item.support_ids), "refute": list(item.refute_ids)}
                for item in batch.proposals
            }
            self.assertEqual(actual, fixture["expected"])
            (candidate,) = batch.proposals
            self.assertEqual(candidate.proposer, proposer.principal)
            self.assertIsNone(store.get_candidate(proposer, candidate.candidate_id))
            self.assertTrue(propose(store, proposer, since=TIME, through=TIME, limit=1).truncated)
            earlier = "2025-01-01T00:00:00Z"
            self.assertEqual(propose(store, proposer, since=earlier, through=earlier).proposals, ())
            store.create_candidate(proposer, candidate.candidate_id, candidate)
            result = store.validate_candidate(proposer, candidate.candidate_id)
            self.assertEqual(len(result.independent_support), 2)
            self.assertEqual(result.duplicate_support, ("one",))
            self.assertEqual(result.refute_ids, ("exception",))
            self.assertIsNone(store.get_belief(proposer, candidate.candidate_id))
