"""Immutable P0 schema contracts, not persistence or authority decisions."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from re import fullmatch


class MemoryKind(str, Enum):
    """The initial logical types; extensible in future schema versions."""

    EXPERIENCE = "experiential"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    CAUSAL = "causal"
    DECISION = "decision"
    HYPOTHESIS = "hypothetical"
    SELF_MODEL = "self_model"


class EpistemicState(str, Enum):
    """A recorded claim's epistemic classification, not a confidence percentage."""

    OBSERVED = "observed"
    INFERRED = "inferred"
    HYPOTHETICAL = "hypothetical"
    CONTESTED = "contested"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    evidence_id: str
    scope: str
    source: str
    digest: str

    def __post_init__(self) -> None:
        if not all((self.evidence_id, self.scope, self.source, self.digest)):
            raise ValueError("Evidence references require identity, scope, source and digest")


@dataclass(frozen=True, slots=True)
class MemoryFormation:
    formation_id: str
    scope: str
    kind: MemoryKind
    evidence_ids: tuple[str, ...]
    producer: str
    created_at: str
    epistemic_state: EpistemicState
    schema_version: str = "0.1.0"

    def __post_init__(self) -> None:
        require_text(self.formation_id, self.scope, self.producer)
        if not isinstance(self.kind, MemoryKind) or not isinstance(
            self.epistemic_state, EpistemicState
        ):
            raise ValueError("Expected a formation kind and epistemic state")
        if self.schema_version != "0.1.0":
            raise ValueError("Unsupported formation schema")
        object.__setattr__(self, "created_at", utc_timestamp(self.created_at))
        if not isinstance(self.evidence_ids, tuple) or not self.evidence_ids:
            raise ValueError("A formation must reference evidence")
        require_text(*self.evidence_ids)
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Evidence references must be unique")


def utc_timestamp(value: str) -> str:
    """Normalize an explicitly offset ISO 8601 timestamp for lexical ordering."""
    if (
        not isinstance(value, str)
        or not fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-5][0-9])",
            value,
        )
        or value.endswith("-00:00")
    ):
        raise ValueError("Expected an ISO 8601 timestamp with a known offset")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Timestamp requires an explicit offset")
    try:
        return parsed.astimezone(UTC).isoformat(timespec="microseconds")
    except OverflowError as error:
        raise ValueError("Timestamp falls outside the supported UTC range") from error


def require_text(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Expected nonempty text")


class EvidenceStatus(str, Enum):
    RECORDED = "recorded"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    scope: str
    source_actor: str
    source_locator: str
    producer: str
    observed_at: str
    recorded_at: str
    status: EvidenceStatus
    payload: bytes
    digest: str

    def __post_init__(self) -> None:
        require_text(
            self.evidence_id, self.scope, self.source_actor, self.source_locator, self.producer
        )
        if not isinstance(self.status, EvidenceStatus) or type(self.payload) is not bytes:
            raise ValueError("Expected an evidence status and immutable payload bytes")
        if self.digest != "sha256:" + sha256(self.payload).hexdigest():
            raise ValueError("Evidence digest does not match payload bytes")
        for field in ("observed_at", "recorded_at"):
            object.__setattr__(self, field, utc_timestamp(getattr(self, field)))


@dataclass(frozen=True, slots=True)
class BeliefProposal:
    proposition: str
    state: EpistemicState
    rationale: str
    valid_from: str
    valid_until: str | None = None
    support_ids: tuple[str, ...] = ()
    refute_ids: tuple[str, ...] = ()
    confidence_basis: str | None = None

    def __post_init__(self) -> None:
        require_text(self.proposition, self.rationale)
        if self.confidence_basis is not None:
            require_text(self.confidence_basis)
        if not isinstance(self.state, EpistemicState) or self.state is EpistemicState.OBSERVED:
            raise ValueError("Beliefs require a derived epistemic state")
        object.__setattr__(self, "valid_from", utc_timestamp(self.valid_from))
        if self.valid_until is not None:
            object.__setattr__(self, "valid_until", utc_timestamp(self.valid_until))
            if self.valid_until <= self.valid_from:
                raise ValueError("Belief validity interval must be nonempty")
        if not isinstance(self.support_ids, tuple) or not isinstance(self.refute_ids, tuple):
            raise ValueError("Evidence references must be immutable tuples")
        links = self.support_ids + self.refute_ids
        require_text(*links)
        if not links or len(links) != len(set(links)):
            raise ValueError("Belief revisions require distinct evidence links")


@dataclass(frozen=True, slots=True)
class BeliefRevision:
    belief_id: str
    revision_id: str
    parent_id: str | None
    sequence: int
    scope: str
    actor: str
    recorded_at: str
    proposal: BeliefProposal
