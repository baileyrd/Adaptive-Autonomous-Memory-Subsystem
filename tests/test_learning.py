"""Guardrails for inert consolidation proposals and lifecycle requests."""

import unittest
from dataclasses import FrozenInstanceError

from aams.learning import CandidateState, CandidateTransitionRequest, LearningCandidate

STAMP = "2026-11-23T11:00:00Z"


def candidate(**overrides):
    values = dict(
        candidate_id="cand-1",
        scope="project:a",
        proposer="agent:a",
        claim="A measured effect is reproducible",
        created_at=STAMP,
        support_ids=("ev-1",),
    )
    values.update(overrides)
    return LearningCandidate(**values)


def transition(from_state, to_state, **overrides):
    values = dict(
        candidate_id="cand-1",
        scope="project:a",
        from_state=from_state,
        to_state=to_state,
        actor="reviewer:a",
        rationale="Evidence reviewed with original source",
        requested_at=STAMP,
    )
    values.update(overrides)
    return CandidateTransitionRequest(**values)


class LearningContractTests(unittest.TestCase):
    def test_candidate_is_proposed_and_immutable(self):
        record = candidate()
        self.assertIs(record.state, CandidateState.PROPOSED)
        self.assertEqual(record.created_at, "2026-11-23T11:00:00.000000+00:00")
        with self.assertRaises(FrozenInstanceError):
            record.claim = "Changed"

    def test_candidates_cannot_begin_authoritative(self):
        for state in (CandidateState.VALIDATED, CandidateState.APPROVED,
                      CandidateState.PROMOTED, CandidateState.REJECTED, "proposed"):
            with self.subTest(state=state), self.assertRaises(ValueError):
                candidate(state=state)

    def test_candidate_requires_distinct_source_ids(self):
        for overrides in (
            {"support_ids": ()},
            {"support_ids": ["ev-1"]},
            {"support_ids": ("ev-1", "ev-1")},
            {"support_ids": ("ev-1",), "refute_ids": ("ev-1",)},
            {"support_ids": ("",)},
            {"support_ids": ("ev-1",), "refute_ids": ["ev-2"]},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                candidate(**overrides)

    def test_rejects_invalid_identity_and_time(self):
        for overrides in (
            {"scope": ""},
            {"proposer": ""},
            {"claim": " "},
            {"created_at": "2026-11-23T11:00:00"},
            {"created_at": "not-a-time"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                candidate(**overrides)

    def test_transition_sequence(self):
        for before, after in (
            (CandidateState.PROPOSED, CandidateState.VALIDATED),
            (CandidateState.PROPOSED, CandidateState.REJECTED),
            (CandidateState.VALIDATED, CandidateState.APPROVED),
            (CandidateState.VALIDATED, CandidateState.REJECTED),
            (CandidateState.APPROVED, CandidateState.PROMOTED),
        ):
            with self.subTest(before=before, after=after):
                request = transition(before, after)
                request.check_target(candidate(), before)

    def test_prohibited_transitions(self):
        for before in CandidateState:
            for after in CandidateState:
                permitted = {
                    (CandidateState.PROPOSED, CandidateState.VALIDATED),
                    (CandidateState.PROPOSED, CandidateState.REJECTED),
                    (CandidateState.VALIDATED, CandidateState.APPROVED),
                    (CandidateState.VALIDATED, CandidateState.REJECTED),
                    (CandidateState.APPROVED, CandidateState.PROMOTED),
                }
                if (before, after) not in permitted:
                    with self.subTest(before=before, after=after), self.assertRaises(ValueError):
                        transition(before, after)

    def test_transition_is_only_a_request(self):
        record = candidate()
        request = transition(CandidateState.PROPOSED, CandidateState.VALIDATED)
        request.check_target(record, CandidateState.PROPOSED)
        self.assertEqual(record.state, CandidateState.PROPOSED)
        with self.assertRaises(FrozenInstanceError):
            request.to_state = CandidateState.APPROVED

    def test_stale_and_cross_scope_requests_rejected(self):
        record = candidate()
        for request, state in (
            (transition(CandidateState.VALIDATED, CandidateState.APPROVED),
             CandidateState.PROPOSED),
            (transition(CandidateState.PROPOSED, CandidateState.VALIDATED,
                        scope="project:b"), CandidateState.PROPOSED),
            (transition(CandidateState.PROPOSED, CandidateState.VALIDATED,
                        candidate_id="cand-other"), CandidateState.PROPOSED),
        ):
            with self.subTest(request=request), self.assertRaises(ValueError):
                request.check_target(record, state)

    def test_invalid_transition_actor_and_time(self):
        for overrides in (
            {"actor": " "},
            {"rationale": ""},
            {"requested_at": "2026-11-23T11:00:00"},
            {"to_state": "validated"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                transition(CandidateState.PROPOSED, CandidateState.VALIDATED, **overrides)


if __name__ == "__main__":
    unittest.main()
