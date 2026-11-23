"""Bounded, host-recorded retrieval measurements with no authority effects."""

from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from re import fullmatch
from typing import TYPE_CHECKING

from .retrieval_routing import ROUTING_POLICY_VERSION, RetrievalMode

if TYPE_CHECKING:
    from .storage import AccessContext, SQLiteMemoryStore

_SCHEMA = (
    """CREATE TABLE retrieval_observation (
        scope TEXT NOT NULL, principal TEXT NOT NULL, attempt_id TEXT NOT NULL,
        policy_version TEXT NOT NULL, mode TEXT NOT NULL,
        label TEXT NOT NULL, latency_ms INTEGER NOT NULL,
        recorded_at TEXT NOT NULL, PRIMARY KEY(scope, principal, attempt_id)
    )""",
)
RETENTION_DAYS = 30
MAX_OBSERVATIONS = 256


class MeasuredOutcome(str, Enum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    ABSTAINED = "abstained"


class TelemetryConflict(ValueError):
    """An observation replay differs, or the retained row budget is exhausted."""


@dataclass(frozen=True, slots=True)
class RetrievalObservation:
    attempt_id: str
    policy_version: str
    mode: RetrievalMode
    label: MeasuredOutcome
    latency_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.attempt_id, str) or not fullmatch(r"[0-9a-f]{32}", self.attempt_id):
            raise ValueError("Attempt ID must be an opaque lowercase UUID hex value")
        if not isinstance(self.policy_version, str) or not fullmatch(
            r"[1-9][0-9]{0,5}", self.policy_version
        ):
            raise ValueError("Invalid retrieval policy version")
        if type(self.mode) is not RetrievalMode or type(self.label) is not MeasuredOutcome:
            raise ValueError("Expected a retrieval mode and measured label")
        if type(self.latency_ms) is not int or not 0 <= self.latency_ms <= 60_000:
            raise ValueError("Latency must be a whole number of milliseconds from 0 to 60000")


@dataclass(frozen=True, slots=True)
class RecordedRetrieval:
    observation: RetrievalObservation
    recorded_at: str


def _decode(row) -> RecordedRetrieval:
    return RecordedRetrieval(
        RetrievalObservation(
            row["attempt_id"],
            row["policy_version"],
            RetrievalMode(row["mode"]),
            MeasuredOutcome(row["label"]),
            row["latency_ms"],
        ),
        row["recorded_at"],
    )


def _cutoff(now: datetime) -> str:
    return (now - timedelta(days=RETENTION_DAYS)).isoformat(timespec="microseconds")


class RetrievalTelemetry:
    def __init__(self, store: "SQLiteMemoryStore") -> None:
        self.store = store

    @staticmethod
    def _key(access: "AccessContext", *, write: bool = False) -> tuple[str, str]:
        if not access.telemetry or (write and not access.writable):
            raise PermissionError("Retrieval telemetry access denied")
        return access.scope, access.principal

    def record(
        self, access: "AccessContext", observation: RetrievalObservation
    ) -> RecordedRetrieval:
        key = self._key(access, write=True)
        if observation.policy_version != ROUTING_POLICY_VERSION:
            raise ValueError("Stale retrieval policy version")
        now = datetime.now(UTC)
        with closing(self.store._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "DELETE FROM retrieval_observation WHERE scope=? AND principal=? AND recorded_at<?",
                (*key, _cutoff(now)),
            )
            prior = db.execute(
                "SELECT * FROM retrieval_observation WHERE scope=? AND principal=? AND attempt_id=?",
                (*key, observation.attempt_id),
            ).fetchone()
            if prior is not None:
                result = _decode(prior)
                if result.observation != observation:
                    raise TelemetryConflict("Attempt already recorded with different measurements")
                return result
            count = db.execute(
                "SELECT count(*) FROM retrieval_observation WHERE scope=? AND principal=?", key
            ).fetchone()[0]
            if count >= MAX_OBSERVATIONS:
                raise TelemetryConflict("Retrieval telemetry budget exhausted")
            recorded_at = now.isoformat(timespec="microseconds")
            db.execute(
                "INSERT INTO retrieval_observation VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    *key,
                    observation.attempt_id,
                    observation.policy_version,
                    observation.mode,
                    observation.label,
                    observation.latency_ms,
                    recorded_at,
                ),
            )
            return RecordedRetrieval(observation, recorded_at)

    def observations(
        self, access: "AccessContext", *, limit: int = 32
    ) -> tuple[RecordedRetrieval, ...]:
        key = self._key(access)
        if type(limit) is not int or not 1 <= limit <= MAX_OBSERVATIONS:
            raise ValueError("Invalid retrieval telemetry limit")
        with closing(self.store._connect()) as db:
            rows = db.execute(
                """SELECT * FROM retrieval_observation WHERE scope=? AND principal=? AND recorded_at>=?
                   ORDER BY recorded_at DESC, attempt_id LIMIT ?""",
                (*key, _cutoff(datetime.now(UTC)), limit),
            )
            return tuple(map(_decode, rows))

    def delete(self, access: "AccessContext") -> int:
        key = self._key(access, write=True)
        with closing(self.store._connect()) as db, db:
            return db.execute(
                "DELETE FROM retrieval_observation WHERE scope=? AND principal=?",
                key,
            ).rowcount
