"""Pure, fail-closed retrieval-mode selection (v0.5 contract only).

This selector does not execute retrieval, inspect protected indexes, or authorize access.
The retrieval service must enforce scope and time checks independently.
"""

from dataclasses import dataclass
from enum import Enum


class RetrievalMode(str, Enum):
    LEXICAL = "lexical"
    HYBRID = "hybrid"


class RoutingReason(str, Enum):
    DEFAULT_LEXICAL = "default_lexical"
    EXACT_CANONICAL = "exact_canonical"
    HYBRID_ELIGIBLE = "hybrid_eligible"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INDEX_NOT_FRESH = "index_not_fresh"


@dataclass(frozen=True, slots=True)
class RetrievalRoutingRequest:
    """Trusted host policy inputs. Neither candidate scores nor facts."""

    requested_mode: RetrievalMode = RetrievalMode.LEXICAL
    exact_lookup: bool = False
    provider_ready: bool = False
    index_fresh: bool = False

    def __post_init__(self) -> None:
        if type(self.requested_mode) is not RetrievalMode:
            raise ValueError("Expected explicit retrieval mode")
        if any(
            type(value) is not bool
            for value in (self.exact_lookup, self.provider_ready, self.index_fresh)
        ):
            raise ValueError("Routing flags must be boolean")


@dataclass(frozen=True, slots=True)
class RetrievalRoutingDecision:
    mode: RetrievalMode
    reason: RoutingReason
    policy_version: str = "1"

    def __post_init__(self) -> None:
        if type(self.mode) is not RetrievalMode or type(self.reason) is not RoutingReason:
            raise ValueError("Routing decision requires supported mode and reason")
        if self.policy_version != "1":
            raise ValueError("Unsupported routing policy version")


def choose_retrieval_mode(request: RetrievalRoutingRequest) -> RetrievalRoutingDecision:
    """Fail closed to lexical; never infer provider quality or trust from readiness."""
    if not isinstance(request, RetrievalRoutingRequest):
        raise ValueError("Expected retrieval routing request")
    if request.exact_lookup:
        return RetrievalRoutingDecision(RetrievalMode.LEXICAL, RoutingReason.EXACT_CANONICAL)
    if request.requested_mode is RetrievalMode.LEXICAL:
        return RetrievalRoutingDecision(RetrievalMode.LEXICAL, RoutingReason.DEFAULT_LEXICAL)
    if not request.provider_ready:
        return RetrievalRoutingDecision(RetrievalMode.LEXICAL, RoutingReason.PROVIDER_UNAVAILABLE)
    if not request.index_fresh:
        return RetrievalRoutingDecision(RetrievalMode.LEXICAL, RoutingReason.INDEX_NOT_FRESH)
    return RetrievalRoutingDecision(RetrievalMode.HYBRID, RoutingReason.HYBRID_ELIGIBLE)
