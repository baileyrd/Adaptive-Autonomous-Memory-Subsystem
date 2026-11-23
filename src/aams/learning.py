"""Proposed learning abstractions: contracts only, never authoritative memory.

This module defines inert, inspectable candidate values and transition *requests*.
Only a future policy-enforcing persistence service may approve or apply them.
"""

from dataclasses import dataclass
from enum import Enum

from .contracts import require_text, utc_timestamp


class CandidateState(str, Enum):
    """The distinct stages of a proposed consolidation."""

    PROPOSED = "proposed"
    VALIDATED = "validated"
    APPROVED = "approved"
    PROMOTED = "promoted"
    REJECTED = "rejected"


_ALLOWED = {
    CandidateState.PROPOSED: frozenset({CandidateState.VALIDATED, CandidateState.REJECTED}),
    CandidateState.VALIDATED: frozenset({CandidateState.APPROVED, CandidateState.REJECTED}),
    CandidateState.APPROVED: frozenset({CandidateState.PROMOTED}),
    CandidateState.PROMOTED: frozenset(),
    CandidateState.REJECTED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class LearningCandidate:
    """An untrusted proposal. Evidence IDs are references, not proof of independence."""

    candidate_id: str
    scope: str
    proposer: str
    claim: str
    created_at: str
    support_ids: tuple[str, ...]
    refute_ids: tuple[str, ...] = ()
    state: CandidateState = CandidateState.PROPOSED

    def __post_init__(self) -> None:
        require_text(self.candidate_id, self.scope, self.proposer, self.claim)
        object.__setattr__(self, "created_at", utc_timestamp(self.created_at))
        if self.state is not CandidateState.PROPOSED:
            raise ValueError("New candidates must start as proposed")
        if type(self.support_ids) is not tuple or type(self.refute_ids) is not tuple:
            raise ValueError("Evidence references must be immutable tuples")
        if not self.support_ids:
            raise ValueError("A candidate requires at least one supporting evidence ID")
        links = self.support_ids + self.refute_ids
        require_text(*links)
        if len(set(links)) != len(links):
            raise ValueError("Candidate evidence IDs must be unique across support/refute")


@dataclass(frozen=True, slots=True)
class CandidateTransitionRequest:
    """A proposed transition, NOT an authorization or committed disposition."""

    candidate_id: str
    scope: str
    from_state: CandidateState
    to_state: CandidateState
    actor: str
    rationale: str
    requested_at: str

    def __post_init__(self) -> None:
        require_text(self.candidate_id, self.scope, self.actor, self.rationale)
        object.__setattr__(self, "requested_at", utc_timestamp(self.requested_at))
        if type(self.from_state) is not CandidateState or type(self.to_state) is not CandidateState:
            raise ValueError("Candidate transitions require valid states")
        if self.to_state not in _ALLOWED[self.from_state]:
            raise ValueError("Illegal candidate transition")

    def check_target(self, candidate: LearningCandidate, current_state: CandidateState) -> None:
        """Check identity and expected state; not permission, evidence or persistence."""
        if (
            not isinstance(candidate, LearningCandidate)
            or type(current_state) is not CandidateState
        ):
            raise ValueError("Expected a valid candidate and current state")
        if self.candidate_id != candidate.candidate_id or self.scope != candidate.scope:
            raise ValueError("Candidate transition identity or scope mismatch")
        if self.from_state is not current_state:
            raise ValueError("Stale candidate transition")
