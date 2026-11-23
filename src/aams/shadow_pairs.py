"""Scoped, bounded in-memory ledger for explicitly measured shadow comparisons."""

from dataclasses import dataclass
from enum import Enum
from threading import Lock

from .contracts import utc_timestamp
from .offline_policy import EvidenceBasis, OfflineOutcome, _opaque
from .storage import AccessContext


class PairStatus(str, Enum):
    MISSING_LABEL = "missing_label"
    OBSERVATIONAL = "observational"
    SAME_MODE = "same_mode"
    CONTROLLED_ALTERNATE = "controlled_alternate"


@dataclass(frozen=True, slots=True)
class ShadowArm:
    cutoff: str
    outcome: OfflineOutcome | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff", utc_timestamp(self.cutoff))
        if self.outcome is not None and type(self.outcome) is not OfflineOutcome:
            raise ValueError("Expected measured or explicitly missing outcome")


@dataclass(frozen=True, slots=True)
class ShadowPair:
    task_id: str
    group_id: str
    window_start: str
    window_end: str
    serving: ShadowArm
    shadow: ShadowArm

    def __post_init__(self) -> None:
        if not _opaque(self.task_id) or not _opaque(self.group_id):
            raise ValueError("Expected opaque task and group IDs")
        if type(self.serving) is not ShadowArm or type(self.shadow) is not ShadowArm:
            raise ValueError("Both arms must declare a snapshot cutoff")
        for field in ("window_start", "window_end"):
            object.__setattr__(self, field, utc_timestamp(getattr(self, field)))
        if (
            self.serving.cutoff != self.shadow.cutoff
            or not self.window_start <= self.serving.cutoff < self.window_end
        ):
            raise ValueError("Both arms must share a cutoff within a half-open group window")
        for arm in (self.serving, self.shadow):
            if arm.outcome is not None and (
                arm.outcome.task_id != self.task_id or arm.outcome.group_id != self.group_id
            ):
                raise ValueError("Measurement identity mismatch")
        if (
            self.serving.outcome
            and self.shadow.outcome
            and (self.serving.outcome.policy_version != self.shadow.outcome.policy_version)
        ):
            raise ValueError("Policy version mismatch")

    @property
    def status(self) -> PairStatus:
        baseline, candidate = self.serving.outcome, self.shadow.outcome
        if baseline is None or candidate is None:
            return PairStatus.MISSING_LABEL
        if any(row.basis is not EvidenceBasis.CONTROLLED_REPLAY for row in (baseline, candidate)):
            return PairStatus.OBSERVATIONAL
        if baseline.mode is candidate.mode:
            return PairStatus.SAME_MODE
        return PairStatus.CONTROLLED_ALTERNATE


class ShadowPairLedger:
    def __init__(self, access: AccessContext, *, limit: int = 100) -> None:
        if not access.shadow_observe:
            raise PermissionError("Shadow pairing denied")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Expected bounded pair limit")
        self._scope = (access.scope, access.principal)
        self._limit = limit
        self._lock = Lock()
        self._pairs: dict[str, ShadowPair] = {}
        self._windows: dict[str, tuple[str, str]] = {}

    def _authorize(self, access: AccessContext) -> None:
        if not access.shadow_observe or self._scope != (access.scope, access.principal):
            raise PermissionError("Shadow pairing denied")

    def record(self, access: AccessContext, pair: ShadowPair) -> ShadowPair:
        self._authorize(access)
        if type(pair) is not ShadowPair:
            raise ValueError("Expected an immutable pair")
        with self._lock:
            previous = self._pairs.get(pair.task_id)
            if previous is not None:
                if previous != pair:
                    raise ValueError("Task already recorded with different measurements")
                return previous
            if len(self._pairs) >= self._limit:
                raise ValueError("Shadow pair limit reached")
            window = pair.window_start, pair.window_end
            previous_window = self._windows.get(pair.group_id)
            if previous_window is not None and previous_window != window:
                raise ValueError("Group window cannot change")
            for group, (start, end) in self._windows.items():
                if group != pair.group_id and start < window[1] and window[0] < end:
                    raise ValueError("Independent group windows cannot overlap")
            self._windows[pair.group_id] = window
            self._pairs[pair.task_id] = pair
            return pair

    def pairs(self, access: AccessContext) -> tuple[ShadowPair, ...]:
        self._authorize(access)
        with self._lock:
            return tuple(self._pairs.values())
