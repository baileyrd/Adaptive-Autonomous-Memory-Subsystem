"""Deterministic, opt-in generation of proposals for review."""

import json
import unicodedata
from dataclasses import dataclass
from hashlib import sha256

from .contracts import utc_timestamp
from .learning import LearningCandidate
from .storage import AccessContext, SQLiteMemoryStore


@dataclass(frozen=True, slots=True)
class ConsolidationBatch:
    proposals: tuple[LearningCandidate, ...]
    truncated: bool
    policy: str = "repeated-text-v1"
    uncertainty: str = "Textual matches only; review lineage and counterexamples."


def propose(
    store: SQLiteMemoryStore,
    access: AccessContext,
    *,
    since: str,
    through: str,
    limit: int = 128,
) -> ConsolidationBatch:
    """Preview repeat groups and explicit 'not:' counterexamples without writing."""
    through = utc_timestamp(through)
    records, truncated = store.sample_learning_evidence(
        access, since=since, through=through, limit=limit
    )
    supports: dict[str, list[str]] = {}
    refutes: dict[str, list[str]] = {}
    for record in records:
        try:
            value = unicodedata.normalize("NFKC", record.payload.decode()).casefold()
        except UnicodeDecodeError:
            continue
        value = " ".join(value.split())
        is_refutation = value.startswith("not:")
        claim = value[4:].strip() if is_refutation else value
        if claim:
            groups = refutes if is_refutation else supports
            groups.setdefault(claim, []).append(record.evidence_id)
    proposals = []
    for claim, identifiers in sorted(supports.items()):
        if len(identifiers) < 2:
            continue
        exceptions = refutes.get(claim, [])
        key = json.dumps([access.scope, access.principal, through, claim, identifiers, exceptions])
        identifier = "candidate-" + sha256(key.encode()).hexdigest()
        proposals.append(
            LearningCandidate(
                identifier,
                access.scope,
                access.principal,
                claim,
                through,
                tuple(identifiers),
                tuple(exceptions),
            )
        )
    return ConsolidationBatch(tuple(proposals), truncated)
