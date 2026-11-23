"""Scoped, transactional SQLite storage for canonical evidence and formations."""

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from .contracts import (
    BeliefProposal,
    BeliefRevision,
    EpistemicState,
    Evidence,
    EvidenceStatus,
    MemoryFormation,
    MemoryKind,
    require_text,
    utc_timestamp,
)

_SCHEMA = (
    """CREATE TABLE evidence (
        evidence_id TEXT PRIMARY KEY NOT NULL, scope TEXT NOT NULL,
        source_actor TEXT NOT NULL, source_locator TEXT NOT NULL, producer TEXT NOT NULL,
        observed_at TEXT NOT NULL, recorded_at TEXT NOT NULL, status TEXT NOT NULL,
        payload BLOB NOT NULL, digest TEXT NOT NULL, UNIQUE (scope, evidence_id)
    )""",
    """CREATE TABLE formation (
        formation_id TEXT PRIMARY KEY NOT NULL, scope TEXT NOT NULL, kind TEXT NOT NULL,
        producer TEXT NOT NULL, created_at TEXT NOT NULL, epistemic_state TEXT NOT NULL,
        schema_version TEXT NOT NULL, UNIQUE (scope, formation_id)
    )""",
    """CREATE TABLE formation_evidence (
        scope TEXT NOT NULL, formation_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
        position INTEGER NOT NULL, PRIMARY KEY (formation_id, position),
        UNIQUE (formation_id, evidence_id),
        FOREIGN KEY (scope, formation_id) REFERENCES formation(scope, formation_id),
        FOREIGN KEY (scope, evidence_id) REFERENCES evidence(scope, evidence_id)
    )""",
    """CREATE TABLE ingestion (
        scope TEXT NOT NULL, principal TEXT NOT NULL, request_key TEXT NOT NULL,
        fingerprint TEXT NOT NULL, formation_id TEXT NOT NULL,
        PRIMARY KEY (scope, principal, request_key),
        FOREIGN KEY (scope, formation_id) REFERENCES formation(scope, formation_id)
    )""",
    """CREATE TRIGGER evidence_no_update BEFORE UPDATE ON evidence
       BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END""",
    """CREATE TRIGGER evidence_no_delete BEFORE DELETE ON evidence
       BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END""",
)


_BELIEF_SCHEMA = (
    """CREATE TABLE belief_revision (
        scope TEXT NOT NULL, belief_id TEXT NOT NULL, revision_id TEXT NOT NULL,
        parent_id TEXT, sequence INTEGER NOT NULL CHECK(sequence > 0),
        actor TEXT NOT NULL, recorded_at TEXT NOT NULL, proposition TEXT NOT NULL,
        state TEXT NOT NULL, rationale TEXT NOT NULL, valid_from TEXT NOT NULL,
        valid_until TEXT, confidence_basis TEXT,
        PRIMARY KEY(scope, belief_id, revision_id), UNIQUE(scope, belief_id, sequence),
        FOREIGN KEY(scope, belief_id, parent_id)
            REFERENCES belief_revision(scope, belief_id, revision_id)
    )""",
    """CREATE TABLE belief_evidence (
        scope TEXT NOT NULL, belief_id TEXT NOT NULL, revision_id TEXT NOT NULL,
        evidence_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('support', 'refute')),
        position INTEGER NOT NULL,
        PRIMARY KEY(scope, belief_id, revision_id, evidence_id),
        UNIQUE(scope, belief_id, revision_id, role, position),
        FOREIGN KEY(scope, belief_id, revision_id)
            REFERENCES belief_revision(scope, belief_id, revision_id),
        FOREIGN KEY(scope, evidence_id) REFERENCES evidence(scope, evidence_id)
    )""",
    """CREATE TRIGGER belief_no_update BEFORE UPDATE ON belief_revision
       BEGIN SELECT RAISE(ABORT, 'immutable revision'); END""",
    """CREATE TRIGGER belief_no_delete BEFORE DELETE ON belief_revision
       BEGIN SELECT RAISE(ABORT, 'immutable revision'); END""",
    """CREATE TRIGGER belief_evidence_no_update BEFORE UPDATE ON belief_evidence
       BEGIN SELECT RAISE(ABORT, 'immutable revision provenance'); END""",
    """CREATE TRIGGER belief_evidence_no_delete BEFORE DELETE ON belief_evidence
       BEGIN SELECT RAISE(ABORT, 'immutable revision provenance'); END""",
)


class WriteConflict(ValueError):
    """A canonical identifier, evidence link or idempotency key conflicts."""


class VersionConflict(WriteConflict):
    """The expected belief revision is stale."""

    code = "VERSION_CONFLICT"


class StoreIntegrityError(RuntimeError):
    """The store could not verify the integrity of canonical data."""


@dataclass(frozen=True, slots=True)
class AccessContext:
    """Trusted host-provided scope grant. Never construct from untrusted request fields."""

    principal: str
    scope: str
    writable: bool = False

    def __post_init__(self) -> None:
        require_text(self.principal, self.scope)
        if type(self.writable) is not bool:
            raise ValueError("Writable must be boolean")


class SQLiteMemoryStore:
    def __init__(self, path: str | Path) -> None:
        if str(path) in ("", ":memory:"):
            raise ValueError("A persistent database path is required")
        self.path = path
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                migrations = (_SCHEMA, _BELIEF_SCHEMA)
                if not 0 <= version <= len(migrations):
                    raise StoreIntegrityError(f"Unsupported database schema version {version}")
                for target, statements in enumerate(migrations[version:], start=version + 1):
                    for statement in statements:
                        db.execute(statement)
                    db.execute(f"PRAGMA user_version = {target}")
        except sqlite3.DatabaseError as error:
            raise StoreIntegrityError("Cannot initialize memory store") from error

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA synchronous = FULL")
            return db
        except BaseException:
            db.close()
            raise

    def ingest(
        self,
        access: AccessContext,
        request_key: str,
        formation: MemoryFormation,
        evidence: tuple[Evidence, ...],
    ) -> MemoryFormation:
        if not access.writable or access.scope != formation.scope:
            raise PermissionError("Write denied")
        require_text(request_key)
        for record in evidence:
            if record.scope != access.scope:
                raise PermissionError("Write denied")
            if record.evidence_id not in formation.evidence_ids:
                raise ValueError("New evidence must be linked by the formation")
        # Each digest was verified against its bytes when the evidence was constructed.
        manifest = [asdict(record) for record in evidence]
        for entry in manifest:
            del entry["payload"]
        manifest.sort(key=lambda entry: entry["evidence_id"])
        request = json.dumps([asdict(formation), manifest], sort_keys=True, separators=(",", ":"))
        fingerprint = sha256(request.encode()).hexdigest()
        key = (access.scope, access.principal, request_key)
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                previous = db.execute(
                    "SELECT fingerprint FROM ingestion WHERE scope=? AND principal=? AND request_key=?",
                    key,
                ).fetchone()
                if previous is not None:
                    if previous["fingerprint"] != fingerprint:
                        raise WriteConflict("Idempotency key already used for a different request")
                    return formation
                db.executemany(
                    """INSERT INTO evidence VALUES (
                        :evidence_id, :scope, :source_actor, :source_locator, :producer,
                        :observed_at, :recorded_at, :status, :payload, :digest
                    )""",
                    (asdict(record) for record in evidence),
                )
                db.execute(
                    """INSERT INTO formation VALUES (
                        :formation_id, :scope, :kind, :producer, :created_at,
                        :epistemic_state, :schema_version
                    )""",
                    asdict(formation),
                )
                db.executemany(
                    "INSERT INTO formation_evidence VALUES (?, ?, ?, ?)",
                    (
                        (access.scope, formation.formation_id, evidence_id, position)
                        for position, evidence_id in enumerate(formation.evidence_ids)
                    ),
                )
                db.execute(
                    "INSERT INTO ingestion VALUES (?, ?, ?, ?, ?)",
                    (*key, fingerprint, formation.formation_id),
                )
        except sqlite3.IntegrityError as error:
            raise WriteConflict("Invalid or duplicate canonical record or evidence link") from error
        except sqlite3.DatabaseError as error:
            raise StoreIntegrityError("Cannot write memory store") from error
        return formation

    def get_evidence(self, access: AccessContext, evidence_id: str) -> Evidence | None:
        try:
            with closing(self._connect()) as db:
                row = db.execute(
                    "SELECT * FROM evidence WHERE scope=? AND evidence_id=?",
                    (access.scope, evidence_id),
                ).fetchone()
                return self._decode_evidence(row) if row is not None else None
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot verify evidence") from error

    @staticmethod
    def _decode_evidence(row: sqlite3.Row) -> Evidence:
        values = dict(row)
        values["status"] = EvidenceStatus(values["status"])
        return Evidence(**values)

    def get_formation(self, access: AccessContext, formation_id: str) -> MemoryFormation | None:
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN")
                row = db.execute(
                    "SELECT * FROM formation WHERE scope=? AND formation_id=?",
                    (access.scope, formation_id),
                ).fetchone()
                if row is None:
                    return None
                values = dict(row)
                values["kind"] = MemoryKind(values["kind"])
                values["epistemic_state"] = EpistemicState(values["epistemic_state"])
                values["evidence_ids"] = tuple(
                    link["evidence_id"]
                    for link in db.execute(
                        """SELECT evidence_id FROM formation_evidence
                           WHERE scope=? AND formation_id=? ORDER BY position""",
                        (access.scope, formation_id),
                    )
                )
                return MemoryFormation(**values)
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot verify formation") from error

    def verify_integrity(self) -> None:
        """Check physical integrity, scoped references and all stored evidence digests."""
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise StoreIntegrityError("SQLite integrity check failed")
                if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise StoreIntegrityError("A canonical reference is broken")
                for row in db.execute("SELECT * FROM evidence"):
                    self._decode_evidence(row)
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot verify memory store") from error

    def revise(
        self,
        access: AccessContext,
        belief_id: str,
        expected_revision: str | None,
        proposal: BeliefProposal,
    ) -> BeliefRevision:
        """Append using the current revision ID, or pass None to create a belief."""
        if not access.writable:
            raise PermissionError("Write denied")
        require_text(belief_id)
        if expected_revision is not None:
            require_text(expected_revision)
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    """SELECT revision_id, sequence, recorded_at FROM belief_revision
                       WHERE scope=? AND belief_id=? ORDER BY sequence DESC LIMIT 1""",
                    (access.scope, belief_id),
                ).fetchone()
                if expected_revision != (current["revision_id"] if current else None):
                    raise VersionConflict(
                        "Expected revision does not match scoped current revision"
                    )
                now = datetime.now(UTC)
                if current is not None:
                    previous_time = datetime.fromisoformat(current["recorded_at"])
                    now = max(now, previous_time + timedelta(microseconds=1))
                revision = BeliefRevision(
                    belief_id,
                    uuid4().hex,
                    expected_revision,
                    current["sequence"] + 1 if current else 1,
                    access.scope,
                    access.principal,
                    now.isoformat(timespec="microseconds"),
                    proposal,
                )
                db.execute(
                    """INSERT INTO belief_revision VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        revision.scope,
                        belief_id,
                        revision.revision_id,
                        expected_revision,
                        revision.sequence,
                        revision.actor,
                        revision.recorded_at,
                        proposal.proposition,
                        proposal.state,
                        proposal.rationale,
                        proposal.valid_from,
                        proposal.valid_until,
                        proposal.confidence_basis,
                    ),
                )
                for role, ids in (
                    ("support", proposal.support_ids),
                    ("refute", proposal.refute_ids),
                ):
                    db.executemany(
                        "INSERT INTO belief_evidence VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            (
                                access.scope,
                                belief_id,
                                revision.revision_id,
                                identifier,
                                role,
                                position,
                            )
                            for position, identifier in enumerate(ids)
                        ),
                    )
            return revision
        except sqlite3.IntegrityError as error:
            raise WriteConflict("Invalid or unavailable scoped revision reference") from error
        except sqlite3.DatabaseError as error:
            raise StoreIntegrityError("Cannot append belief revision") from error

    def belief_history(self, access: AccessContext, belief_id: str) -> tuple[BeliefRevision, ...]:
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN")
                rows = db.execute(
                    """SELECT * FROM belief_revision WHERE scope=? AND belief_id=?
                       ORDER BY sequence""",
                    (access.scope, belief_id),
                )
                return tuple(self._decode_revision(db, row) for row in rows)
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot verify belief history") from error

    def get_belief(
        self,
        access: AccessContext,
        belief_id: str,
        *,
        recorded_as_of: str | None = None,
        effective_at: str | None = None,
    ) -> BeliefRevision | None:
        """Return the newest applicable revision in the caller's scope."""
        recorded = utc_timestamp(recorded_as_of) if recorded_as_of is not None else None
        effective = utc_timestamp(effective_at) if effective_at is not None else None
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN")
                row = db.execute(
                    """SELECT * FROM belief_revision WHERE scope=? AND belief_id=?
                       AND (? IS NULL OR recorded_at<=?)
                       AND (? IS NULL OR (valid_from<=? AND (valid_until IS NULL OR ?<valid_until)))
                       ORDER BY sequence DESC LIMIT 1""",
                    (access.scope, belief_id, recorded, recorded, effective, effective, effective),
                ).fetchone()
                return self._decode_revision(db, row) if row is not None else None
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot verify belief revision") from error

    @staticmethod
    def _decode_revision(db: sqlite3.Connection, row: sqlite3.Row) -> BeliefRevision:
        links = {"support": [], "refute": []}
        for link in db.execute(
            """SELECT role, evidence_id FROM belief_evidence
               WHERE scope=? AND belief_id=? AND revision_id=? ORDER BY position""",
            (row["scope"], row["belief_id"], row["revision_id"]),
        ):
            links[link["role"]].append(link["evidence_id"])
        proposal = BeliefProposal(
            row["proposition"],
            EpistemicState(row["state"]),
            row["rationale"],
            row["valid_from"],
            row["valid_until"],
            tuple(links["support"]),
            tuple(links["refute"]),
            row["confidence_basis"],
        )
        return BeliefRevision(
            row["belief_id"],
            row["revision_id"],
            row["parent_id"],
            row["sequence"],
            row["scope"],
            row["actor"],
            row["recorded_at"],
            proposal,
        )

    def recall_candidates(
        self, access: AccessContext, *, recorded_as_of: str | None, effective_at: str | None
    ) -> tuple[tuple[str, str], ...]:
        """Enumerate scoped stable identities eligible for canonical lookups."""
        try:
            with closing(self._connect()) as db:
                rows = db.execute(
                    """SELECT 'formation' AS entity, formation_id AS id FROM formation
                       WHERE scope=? AND (? IS NULL OR created_at<=?)
                         AND (? IS NULL OR created_at<=?)
                       UNION
                       SELECT 'belief', belief_id FROM belief_revision
                       WHERE scope=? AND (? IS NULL OR recorded_at<=?)
                         AND (? IS NULL OR (valid_from<=? AND (valid_until IS NULL OR ?<valid_until)))
                       ORDER BY entity, id""",
                    (
                        access.scope,
                        recorded_as_of,
                        recorded_as_of,
                        effective_at,
                        effective_at,
                        access.scope,
                        recorded_as_of,
                        recorded_as_of,
                        effective_at,
                        effective_at,
                        effective_at,
                    ),
                )
                return tuple((row["entity"], row["id"]) for row in rows)
        except sqlite3.DatabaseError as error:
            raise StoreIntegrityError("Cannot enumerate memory") from error
