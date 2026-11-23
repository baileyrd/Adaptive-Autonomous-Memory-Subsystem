"""Bounded, in-process shadow observation for a trusted native host."""

from threading import Lock, Thread
from time import monotonic
from uuid import uuid4

from .offline_candidate import FEATURE_VERSION, MODEL_VERSION, FeatureBin, StagedRoutingCandidate
from .retrieval_routing import ROUTING_POLICY_VERSION
from .shadow import ShadowConfig, ShadowIntent, ShadowObservation, shadow_allowed
from .storage import AccessContext


def _suggest(eligible: frozenset[bool], short_query: bool, opt_in: bool) -> str:
    return "hybrid" if opt_in and short_query in eligible else "lexical"


class ShadowObserver:
    """One in-flight evaluation, no queue, no persistent writes, no callback injection."""

    def __init__(
        self,
        access: AccessContext,
        config: ShadowConfig,
        artifact: StagedRoutingCandidate,
        *,
        timeout_ms: int = 25,
    ) -> None:
        if (
            not isinstance(config, ShadowConfig)
            or type(timeout_ms) is not int
            or not 1 <= timeout_ms <= 1000
        ):
            raise ValueError("Expected bounded shadow configuration")
        if (
            type(artifact) is not StagedRoutingCandidate
            or artifact.feature_version != FEATURE_VERSION
            or artifact.model_version != MODEL_VERSION
            or artifact.policy_version != ROUTING_POLICY_VERSION
            or type(artifact.bins) is not tuple
            or len(artifact.bins) > 2
            or any(type(bucket) is not FeatureBin for bucket in artifact.bins)
        ):
            raise ValueError("Unsupported staged shadow artifact")
        self._config = config
        self._owner = (access.scope, access.principal)
        self._eligible = frozenset(
            bucket.short_query for bucket in artifact.bins if bucket.eligible
        )
        self._candidate_version = artifact.model_version
        self._scope_id = uuid4().hex
        self._timeout = timeout_ms / 1000
        self._lock = Lock()
        self._started = 0
        self._busy = False
        self._observations: list[ShadowObservation] = []

    def _authorized(self, access: AccessContext) -> bool:
        return access.shadow_observe and self._owner == (access.scope, access.principal)

    def submit(self, access: AccessContext, *, short_query: bool, opt_in: bool) -> None:
        if not shadow_allowed(self._config, self._authorized(access)):
            return
        if (
            type(short_query) is not bool
            or type(opt_in) is not bool
            or not self._lock.acquire(False)
        ):
            return
        try:
            if self._busy or self._started >= self._config.max_observations:
                return
            intent = ShadowIntent(self._scope_id, uuid4().hex, self._candidate_version)
            worker = Thread(
                target=self._run, args=(intent, short_query, opt_in, monotonic()), daemon=True
            )
            self._busy = True
            self._started += 1
            try:
                worker.start()
            except RuntimeError:
                self._busy = False
        finally:
            self._lock.release()

    def _run(self, intent: ShadowIntent, short_query: bool, opt_in: bool, started: float) -> None:
        success = True
        try:
            suggestion = _suggest(self._eligible, short_query, opt_in)
        except Exception:
            suggestion, success = "lexical", False
        elapsed = monotonic() - started
        if elapsed > self._timeout:
            suggestion, success = "lexical", False
        with self._lock:
            self._observations.append(
                ShadowObservation(intent, suggestion, min(elapsed * 1000, 60000.0), success)
            )
            self._busy = False

    def observations(self, access: AccessContext) -> tuple[ShadowObservation, ...]:
        if not self._authorized(access):
            raise PermissionError("Shadow observation access denied")
        with self._lock:
            return tuple(self._observations)
