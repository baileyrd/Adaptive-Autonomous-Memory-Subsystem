"""Offline-only retrieval policy evaluation with explicit matched observations.

These structures neither train policies nor modify live routing, telemetry, or memory.
A controlled pair describes two actually measured runs; it cannot infer unrun outcomes.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from re import fullmatch

from .retrieval_routing import RetrievalMode


class OutcomeLabel(str, Enum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    ABSTAINED = "abstained"


class EvidenceBasis(str, Enum):
    CONTROLLED_REPLAY = "controlled_replay"
    OBSERVATIONAL = "observational"


def _opaque(value: str) -> bool:
    return isinstance(value, str) and fullmatch(r"[0-9a-f]{32}", value) is not None


@dataclass(frozen=True, slots=True)
class OfflineOutcome:
    """A measured outcome without queries, contents, or source identifiers."""

    task_id: str
    group_id: str
    mode: RetrievalMode
    label: OutcomeLabel
    latency_ms: float
    policy_version: str
    basis: EvidenceBasis

    def __post_init__(self) -> None:
        if not _opaque(self.task_id) or not _opaque(self.group_id):
            raise ValueError("Task and group IDs must be opaque lower-case hex")
        if type(self.mode) is not RetrievalMode or type(self.label) is not OutcomeLabel:
            raise ValueError("Invalid mode or measured outcome")
        if type(self.basis) is not EvidenceBasis:
            raise ValueError("Unspecified measurement basis")
        if not isinstance(self.policy_version, str) or not fullmatch(
            r"[1-9][0-9]{0,5}", self.policy_version
        ):
            raise ValueError("Invalid policy version")
        if type(self.latency_ms) is not float or not isfinite(self.latency_ms):
            raise ValueError("Invalid latency")
        if not 0 <= self.latency_ms <= 60_000:
            raise ValueError("Latency outside bounded measurement range")


@dataclass(frozen=True, slots=True)
class OfflineRiskBudget:
    """Pre-registered comparison limits; utility counts a satisfied task as one."""

    max_latency_ms: float
    max_unsatisfied_fraction: float

    def __post_init__(self) -> None:
        if type(self.max_latency_ms) is not float or not isfinite(self.max_latency_ms):
            raise ValueError("Invalid latency budget")
        if not 0 < self.max_latency_ms <= 60_000:
            raise ValueError("Latency budget must be positive")
        if (
            type(self.max_unsatisfied_fraction) is not float
            or not isfinite(self.max_unsatisfied_fraction)
            or not 0 <= self.max_unsatisfied_fraction <= 1
        ):
            raise ValueError("Invalid unsatisfied fraction")


@dataclass(frozen=True, slots=True)
class OfflineComparison:
    """An evidence summary of controlled paired outcomes; not a policy promotion."""

    sample_count: int
    baseline_satisfied: int
    candidate_satisfied: int
    baseline_unsatisfied: int
    candidate_unsatisfied: int
    candidate_mean_latency_ms: float
    meets_risk_budget: bool


def compare_controlled(
    baseline: tuple[OfflineOutcome, ...],
    candidate: tuple[OfflineOutcome, ...],
    budget: OfflineRiskBudget,
) -> OfflineComparison:
    """Compare measured, exactly paired tasks; forbid observational counterfactuals."""
    if type(baseline) is not tuple or type(candidate) is not tuple:
        raise ValueError("Outcomes must be immutable tuples")
    if not isinstance(budget, OfflineRiskBudget):
        raise ValueError("Expected an explicit risk budget")
    if not baseline or len(baseline) != len(candidate):
        raise ValueError("Equal nonempty measured samples required")
    for rows in (baseline, candidate):
        if any(not isinstance(row, OfflineOutcome) for row in rows):
            raise ValueError("Invalid outcome")
        if any(row.basis is not EvidenceBasis.CONTROLLED_REPLAY for row in rows):
            raise ValueError("Observational logs cannot prove counterfactual outcomes")
        if len(set(row.task_id for row in rows)) != len(rows):
            raise ValueError("Duplicate task IDs are not independent matched runs")
    before = {row.task_id: row for row in baseline}
    after = {row.task_id: row for row in candidate}
    if before.keys() != after.keys():
        raise ValueError("Comparison requires identical measured tasks")
    if any(
        before[key].group_id != after[key].group_id or before[key].mode is after[key].mode
        for key in before
    ):
        raise ValueError("Group mismatch or no alternate-mode comparison")
    total = len(candidate)
    baseline_satisfied = sum(row.label is OutcomeLabel.SATISFIED for row in baseline)
    candidate_satisfied = sum(row.label is OutcomeLabel.SATISFIED for row in candidate)
    baseline_unsatisfied = sum(row.label is OutcomeLabel.UNSATISFIED for row in baseline)
    candidate_unsatisfied = sum(row.label is OutcomeLabel.UNSATISFIED for row in candidate)
    mean_latency = sum(row.latency_ms for row in candidate) / total
    meets_budget = (
        mean_latency <= budget.max_latency_ms
        and candidate_unsatisfied / total <= budget.max_unsatisfied_fraction
    )
    return OfflineComparison(
        total,
        baseline_satisfied,
        candidate_satisfied,
        baseline_unsatisfied,
        candidate_unsatisfied,
        mean_latency,
        meets_budget,
    )
