"""Immutable P0 schema contracts, not persistence or authority decisions."""

from dataclasses import dataclass
from enum import Enum


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
        if not all((self.formation_id, self.scope, self.producer, self.created_at)):
            raise ValueError("Formation identity, scope, producer and time are required")
        if not self.evidence_ids:
            raise ValueError("A formation must reference evidence")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Evidence references must be unique")
