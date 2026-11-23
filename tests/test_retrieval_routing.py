"""Contract tests for strict, opt-in, deterministic retrieval routing."""

import unittest
from dataclasses import FrozenInstanceError

from aams.retrieval_routing import (
    RetrievalMode,
    RetrievalRoutingDecision,
    RetrievalRoutingRequest,
    RoutingReason,
    choose_retrieval_mode,
)


class RetrievalRoutingTests(unittest.TestCase):
    def test_default_is_lexical_even_when_hybrid_is_ready(self):
        request = RetrievalRoutingRequest(provider_ready=True, index_fresh=True)
        result = choose_retrieval_mode(request)
        self.assertEqual(result.mode, RetrievalMode.LEXICAL)
        self.assertEqual(result.reason, RoutingReason.DEFAULT_LEXICAL)

    def test_exact_lookup_stays_canonical(self):
        for ready in (False, True):
            for fresh in (False, True):
                request = RetrievalRoutingRequest(
                    requested_mode=RetrievalMode.HYBRID,
                    exact_lookup=True,
                    provider_ready=ready,
                    index_fresh=fresh,
                )
                with self.subTest(request=request):
                    result = choose_retrieval_mode(request)
                    self.assertEqual(result.mode, RetrievalMode.LEXICAL)
                    self.assertEqual(result.reason, RoutingReason.EXACT_CANONICAL)

    def test_hybrid_requires_explicit_opt_in_and_fresh_index(self):
        request = RetrievalRoutingRequest(
            requested_mode=RetrievalMode.HYBRID,
            provider_ready=True,
            index_fresh=True,
        )
        result = choose_retrieval_mode(request)
        self.assertEqual(result.mode, RetrievalMode.HYBRID)
        self.assertEqual(result.reason, RoutingReason.HYBRID_ELIGIBLE)

    def test_degraded_routes_never_execute_hybrid(self):
        expected = (
            (False, True, RoutingReason.PROVIDER_UNAVAILABLE),
            (False, False, RoutingReason.PROVIDER_UNAVAILABLE),
            (True, False, RoutingReason.INDEX_NOT_FRESH),
        )
        for ready, fresh, reason in expected:
            request = RetrievalRoutingRequest(
                requested_mode=RetrievalMode.HYBRID,
                provider_ready=ready,
                index_fresh=fresh,
            )
            with self.subTest(request=request):
                result = choose_retrieval_mode(request)
                self.assertEqual(result.mode, RetrievalMode.LEXICAL)
                self.assertEqual(result.reason, reason)

    def test_type_validation_fails_closed(self):
        for change in (
            {"requested_mode": "hybrid"},
            {"requested_mode": None},
            {"exact_lookup": 1},
            {"provider_ready": "true"},
            {"index_fresh": 1},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                RetrievalRoutingRequest(**change)
        with self.assertRaises(ValueError):
            choose_retrieval_mode("hybrid")
        with self.assertRaises(ValueError):
            RetrievalRoutingDecision(RetrievalMode.HYBRID, "hybrid_eligible")
        with self.assertRaises(ValueError):
            RetrievalRoutingDecision(
                RetrievalMode.LEXICAL, RoutingReason.DEFAULT_LEXICAL, policy_version="2"
            )

    def test_immutable_decisions_and_no_authority_method(self):
        decision = choose_retrieval_mode(RetrievalRoutingRequest())
        with self.assertRaises(FrozenInstanceError):
            decision.mode = RetrievalMode.HYBRID
        self.assertFalse(hasattr(decision, "promote"))
        self.assertFalse(hasattr(decision, "revise_belief"))


if __name__ == "__main__":
    unittest.main()
