"""Train an inspectable two-bin candidate for offline replay only."""

import json
from dataclasses import dataclass
from hashlib import sha256

from .offline_policy import EvidenceBasis, OfflineOutcome, OutcomeLabel
from .retrieval_routing import ROUTING_POLICY_VERSION, RetrievalMode

FEATURE_VERSION = "short-query-and-opt-in-v1"
MODEL_VERSION = "group-votes-v1"


@dataclass(frozen=True, slots=True)
class TrainingPair:
    short_query: bool
    opted_in: bool
    lexical: OfflineOutcome
    hybrid: OfflineOutcome

    def __post_init__(self) -> None:
        if type(self.short_query) is not bool or type(self.opted_in) is not bool:
            raise ValueError("Training features must be boolean")
        if not isinstance(self.lexical, OfflineOutcome) or not isinstance(
            self.hybrid, OfflineOutcome
        ):
            raise ValueError("Expected controlled outcomes")
        left, right = self.lexical, self.hybrid
        if (
            (left.task_id, left.group_id) != (right.task_id, right.group_id)
            or left.mode is not RetrievalMode.LEXICAL
            or right.mode is not RetrievalMode.HYBRID
            or left.basis is not EvidenceBasis.CONTROLLED_REPLAY
            or right.basis is not EvidenceBasis.CONTROLLED_REPLAY
            or left.policy_version != ROUTING_POLICY_VERSION
            or right.policy_version != ROUTING_POLICY_VERSION
        ):
            raise ValueError("Expected a matched, current, controlled lexical/hybrid pair")


@dataclass(frozen=True, slots=True)
class FeatureBin:
    short_query: bool
    groups: int
    wins: int
    losses: int

    @property
    def probability_of_gain(self) -> float:
        return (self.wins + 1) / (self.groups + 2)

    @property
    def eligible(self) -> bool:
        return self.groups >= 2 and self.wins == self.groups and not self.losses


@dataclass(frozen=True, slots=True)
class StagedRoutingCandidate:
    training_checksum: str
    bins: tuple[FeatureBin, ...]
    model_version: str = MODEL_VERSION
    feature_version: str = FEATURE_VERSION
    policy_version: str = ROUTING_POLICY_VERSION

    def suggests_hybrid(self, *, short_query: bool, opt_in: bool) -> bool:
        if type(short_query) is not bool or type(opt_in) is not bool or not opt_in:
            return False
        return any(bucket.short_query == short_query and bucket.eligible for bucket in self.bins)


def train_candidate(pairs: tuple[TrainingPair, ...]) -> StagedRoutingCandidate:
    if type(pairs) is not tuple or not 1 <= len(pairs) <= 4096:
        raise ValueError("Expected 1 to 4096 immutable controlled pairs")
    if any(not isinstance(pair, TrainingPair) for pair in pairs):
        raise ValueError("Invalid training pair")
    if len({pair.lexical.task_id for pair in pairs}) != len(pairs):
        raise ValueError("Repeated task IDs cannot add training weight")

    manifest = []
    grouped: dict[tuple[bool, str], list[int]] = {}
    for pair in sorted(pairs, key=lambda pair: pair.lexical.task_id):
        left, right = pair.lexical, pair.hybrid
        manifest.append(
            [
                left.task_id,
                left.group_id,
                pair.short_query,
                pair.opted_in,
                left.label.value,
                right.label.value,
            ]
        )
        if not pair.opted_in or OutcomeLabel.ABSTAINED in (left.label, right.label):
            continue
        change = int(right.label is OutcomeLabel.SATISFIED) - int(
            left.label is OutcomeLabel.SATISFIED
        )
        grouped.setdefault((pair.short_query, left.group_id), []).append(change)

    bins = []
    for short in (False, True):
        votes = [group for (flag, _), group in grouped.items() if flag == short]
        bins.append(
            FeatureBin(
                short,
                len(votes),
                sum(min(group) >= 0 and max(group) > 0 for group in votes),
                sum(min(group) < 0 for group in votes),
            )
        )
    checksum = "sha256:" + sha256(json.dumps(manifest, separators=(",", ":")).encode()).hexdigest()
    return StagedRoutingCandidate(checksum, tuple(bins))
