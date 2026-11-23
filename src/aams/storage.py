"""Scoped, transactional SQLite storage for canonical evidence and formations."""

import json
import sqlite3
from collections.abc import Iterator
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

from .learning import (
    CandidateDecision,
    CandidateRecord,
    CandidateState,
    CandidateTransitionRequest,
    CandidateValidation,
    LearningCandidate,
    OutcomeFeedback,
    OutcomeRevision,
)

from .retrieval_telemetry import _SCHEMA as _TELEMETRY_SCHEMA
from .vector_index import _SCHEMA as _REPRESENTATION_SCHEMA

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


_CANDIDATE_SCHEMA = (
    """CREATE TABLE learning_candidate (
        scope TEXT NOT NULL, candidate_id TEXT NOT NULL, proposer TEXT NOT NULL,
        claim TEXT NOT NULL, created_at TEXT NOT NULL, request_key TEXT NOT NULL,
        PRIMARY KEY(scope, candidate_id), UNIQUE(scope, proposer, request_key)
    )""",
    """CREATE TABLE candidate_evidence (
        scope TEXT NOT NULL, candidate_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('support', 'refute')), position INTEGER NOT NULL,
        PRIMARY KEY(scope, candidate_id, evidence_id), UNIQUE(scope, candidate_id, role, position),
        FOREIGN KEY(scope, candidate_id) REFERENCES learning_candidate(scope, candidate_id),
        FOREIGN KEY(scope, evidence_id) REFERENCES evidence(scope, evidence_id)
    )""",
    """CREATE TABLE candidate_decision (
        scope TEXT NOT NULL, candidate_id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version > 0),
        from_state TEXT NOT NULL, to_state TEXT NOT NULL, actor TEXT NOT NULL,
        rationale TEXT NOT NULL, requested_at TEXT NOT NULL, recorded_at TEXT NOT NULL,
        request_key TEXT NOT NULL,
        PRIMARY KEY(scope, candidate_id, version),
        UNIQUE(scope, candidate_id, actor, request_key),
        FOREIGN KEY(scope, candidate_id) REFERENCES learning_candidate(scope, candidate_id)
    )""",
    """CREATE TRIGGER candidate_decision_no_update BEFORE UPDATE ON candidate_decision
       BEGIN SELECT RAISE(ABORT, 'immutable candidate decision'); END""",
    """CREATE TRIGGER candidate_decision_no_delete BEFORE DELETE ON candidate_decision
       BEGIN SELECT RAISE(ABORT, 'immutable candidate decision'); END""",
)


_OUTCOME_SCHEMA = (
    """CREATE TABLE outcome_revision (
        scope TEXT NOT NULL, episode_id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0),
        candidate_id TEXT NOT NULL, producer TEXT NOT NULL, conditions TEXT NOT NULL,
        predicted REAL NOT NULL CHECK(predicted BETWEEN 0 AND 1),
        measured REAL NOT NULL CHECK(measured BETWEEN 0 AND 1),
        measured_at TEXT NOT NULL, recorded_at TEXT NOT NULL, request_key TEXT NOT NULL,
        PRIMARY KEY(scope, episode_id, version), UNIQUE(scope, episode_id, producer, request_key),
        FOREIGN KEY(scope, candidate_id) REFERENCES learning_candidate(scope, candidate_id)
    )""",
    """CREATE TABLE outcome_evidence (
        scope TEXT NOT NULL, episode_id TEXT NOT NULL, version INTEGER NOT NULL,
        evidence_id TEXT NOT NULL, position INTEGER NOT NULL,
        PRIMARY KEY(scope, episode_id, version, evidence_id),
        UNIQUE(scope, episode_id, version, position),
        FOREIGN KEY(scope, episode_id, version) REFERENCES outcome_revision(scope, episode_id, version),
        FOREIGN KEY(scope, evidence_id) REFERENCES evidence(scope, evidence_id)
    )""",
    """CREATE TRIGGER outcome_revision_no_update BEFORE UPDATE ON outcome_revision
       BEGIN SELECT RAISE(ABORT, 'immutable outcome revision'); END""",
    """CREATE TRIGGER outcome_revision_no_delete BEFORE DELETE ON outcome_revision
       BEGIN SELECT RAISE(ABORT, 'immutable outcome revision'); END""",
    """CREATE TRIGGER outcome_evidence_no_update BEFORE UPDATE ON outcome_evidence
       BEGIN SELECT RAISE(ABORT, 'immutable outcome evidence'); END""",
    """CREATE TRIGGER outcome_evidence_no_delete BEFORE DELETE ON outcome_evidence
       BEGIN SELECT RAISE(ABORT, 'immutable outcome evidence'); END""",
)


_EVIDENCE_COLUMNS = (
    "evidence_id, scope, source_actor, source_locator, producer, "
    "observed_at, recorded_at, status, payload, digest"
)
_FORMATION_COLUMNS = (
    "formation_id, scope, kind, producer, created_at, epistemic_state, schema_version"
)

# Schema 7 replaces the global evidence/formation ID keys with scope-qualified keys.
_SCOPED_ID_SCHEMA = (
    """CREATE TABLE evidence_v7 (
        evidence_id TEXT NOT NULL, scope TEXT NOT NULL,
        source_actor TEXT NOT NULL, source_locator TEXT NOT NULL, producer TEXT NOT NULL,
        observed_at TEXT NOT NULL, recorded_at TEXT NOT NULL, status TEXT NOT NULL,
        payload BLOB NOT NULL, digest TEXT NOT NULL, PRIMARY KEY (scope, evidence_id)
    )""",
    f"INSERT INTO evidence_v7 ({_EVIDENCE_COLUMNS}) SELECT {_EVIDENCE_COLUMNS} FROM evidence",
    "DROP TABLE evidence",
    "ALTER TABLE evidence_v7 RENAME TO evidence",
    """CREATE TRIGGER evidence_no_update BEFORE UPDATE ON evidence
       BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END""",
    """CREATE TRIGGER evidence_no_delete BEFORE DELETE ON evidence
       BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END""",
    """CREATE TABLE formation_v7 (
        formation_id TEXT NOT NULL, scope TEXT NOT NULL, kind TEXT NOT NULL,
        producer TEXT NOT NULL, created_at TEXT NOT NULL, epistemic_state TEXT NOT NULL,
        schema_version TEXT NOT NULL, PRIMARY KEY (scope, formation_id)
    )""",
    f"INSERT INTO formation_v7 ({_FORMATION_COLUMNS}) SELECT {_FORMATION_COLUMNS} FROM formation",
    "DROP TABLE formation",
    "ALTER TABLE formation_v7 RENAME TO formation",
    """CREATE TABLE formation_evidence_v7 (
        scope TEXT NOT NULL, formation_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
        position INTEGER NOT NULL, PRIMARY KEY (scope, formation_id, position),
        UNIQUE (scope, formation_id, evidence_id),
        FOREIGN KEY (scope, formation_id) REFERENCES formation(scope, formation_id),
        FOREIGN KEY (scope, evidence_id) REFERENCES evidence(scope, evidence_id)
    )""",
    """INSERT INTO formation_evidence_v7 (scope, formation_id, evidence_id, position)
       SELECT scope, formation_id, evidence_id, position FROM formation_evidence""",
    "DROP TABLE formation_evidence",
    "ALTER TABLE formation_evidence_v7 RENAME TO formation_evidence",
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
    candidate_review: bool = False
    telemetry: bool = False
    shadow_observe: bool = False

    def __post_init__(self) -> None:
        require_text(self.principal, self.scope)
        if any(
            type(grant) is not bool
            for grant in (self.writable, self.candidate_review, self.telemetry, self.shadow_observe)
        ):
            raise ValueError("Access grants must be boolean")


class SQLiteMemoryStore:
    def __init__(self, path: str | Path) -> None:
        if str(path) in ("", ":memory:"):
            raise ValueError("A persistent database path is required")
        self.path = path
        try:
            with closing(self._connect()) as db, db:
                # SQLite requires foreign keys disabled outside the table-rebuild transaction.
                db.execute("PRAGMA foreign_keys = OFF")
                db.execute("BEGIN IMMEDIATE")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                migrations = (
                    _SCHEMA,
                    _BELIEF_SCHEMA,
                    _CANDIDATE_SCHEMA,
                    _OUTCOME_SCHEMA,
                    _REPRESENTATION_SCHEMA,
                    _TELEMETRY_SCHEMA,
                    _SCOPED_ID_SCHEMA,
                )
                if not 0 <= version <= len(migrations):
                    raise StoreIntegrityError(f"Unsupported database schema version {version}")
                for target, statements in enumerate(migrations[version:], start=version + 1):
                    for statement in statements:
                        db.execute(statement)
                    db.execute(f"PRAGMA user_version = {target}")
                if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise StoreIntegrityError("Migration left a broken canonical reference")
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

    def ingestion_time(self, access: AccessContext, request_key: str) -> str | None:
        """Return the trusted, previously committed ingestion time for an idempotency key."""
        require_text(request_key)
        try:
            with closing(self._connect()) as db:
                row = db.execute(
                    """SELECT formation.created_at FROM ingestion JOIN formation
                       ON formation.scope=ingestion.scope
                       AND formation.formation_id=ingestion.formation_id
                       WHERE ingestion.scope=? AND ingestion.principal=?
                       AND ingestion.request_key=?""",
                    (access.scope, access.principal, request_key),
                ).fetchone()
                return row["created_at"] if row is not None else None
        except sqlite3.DatabaseError as error:
            raise StoreIntegrityError("Cannot read ingestion record") from error

    def get_evidence(self, access: AccessContext, evidence_id: str) -> Evidence | None:
        try:
            with closing(self._connect()) as db:
                return self._read_evidence(db, access.scope, evidence_id)
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot verify evidence") from error

    def _read_evidence(
        self, db: sqlite3.Connection, scope: str, evidence_id: str
    ) -> Evidence | None:
        row = db.execute(
            "SELECT * FROM evidence WHERE scope=? AND evidence_id=?", (scope, evidence_id)
        ).fetchone()
        return self._decode_evidence(row) if row is not None else None

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
                return self._decode_formation(db, row)
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot verify formation") from error

    @staticmethod
    def _decode_formation(db: sqlite3.Connection, row: sqlite3.Row) -> MemoryFormation:
        values = dict(row)
        values["kind"] = MemoryKind(values["kind"])
        values["epistemic_state"] = EpistemicState(values["epistemic_state"])
        values["evidence_ids"] = tuple(
            link["evidence_id"]
            for link in db.execute(
                """SELECT evidence_id FROM formation_evidence
                   WHERE scope=? AND formation_id=? ORDER BY position""",
                (row["scope"], row["formation_id"]),
            )
        )
        return MemoryFormation(**values)

    def verify_integrity(self) -> None:
        """Check SQLite structure, scoped references and canonical record invariants."""
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise StoreIntegrityError("SQLite integrity check failed")
                if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise StoreIntegrityError("A canonical reference is broken")
                for row in db.execute("SELECT * FROM evidence"):
                    self._decode_evidence(row)
                for row in db.execute("SELECT * FROM formation"):
                    self._decode_formation(db, row)
                for row in db.execute("SELECT * FROM belief_revision"):
                    self._decode_revision(db, row)
                for row in db.execute("SELECT scope, candidate_id FROM learning_candidate"):
                    self._read_candidate(db, row["scope"], row["candidate_id"])
                for row in db.execute("SELECT * FROM outcome_revision"):
                    self._read_outcome(db, row)
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
                return self._read_belief(db, access.scope, belief_id, recorded, effective)
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot verify belief revision") from error

    def _read_belief(
        self,
        db: sqlite3.Connection,
        scope: str,
        belief_id: str,
        recorded: str | None,
        effective: str | None,
    ) -> BeliefRevision | None:
        row = db.execute(
            """SELECT * FROM belief_revision WHERE scope=? AND belief_id=?
               AND (? IS NULL OR recorded_at<=?)
               AND (? IS NULL OR (valid_from<=? AND (valid_until IS NULL OR ?<valid_until)))
               ORDER BY sequence DESC LIMIT 1""",
            (scope, belief_id, recorded, recorded, effective, effective, effective),
        ).fetchone()
        return self._decode_revision(db, row) if row is not None else None

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

    def scan_recall(
        self,
        access: AccessContext,
        *,
        recorded_as_of: str | None,
        effective_at: str | None,
        kinds: tuple[MemoryKind, ...],
    ) -> Iterator[tuple[MemoryFormation | BeliefRevision, dict[str, Evidence]]]:
        """Yield allowed records and their resolved evidence from one SQLite snapshot."""
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN")
                for row in db.execute(
                    """SELECT * FROM formation
                       WHERE scope=? AND (? IS NULL OR created_at<=?)
                       AND (? IS NULL OR created_at<=?)""",
                    (access.scope, recorded_as_of, recorded_as_of, effective_at, effective_at),
                ):
                    formation = self._decode_formation(db, row)
                    if not kinds or formation.kind in kinds:
                        yield (
                            formation,
                            self._resolve_evidence(db, access.scope, formation.evidence_ids),
                        )
                if kinds:
                    return
                for row in db.execute(
                    "SELECT DISTINCT belief_id FROM belief_revision WHERE scope=?", (access.scope,)
                ):
                    revision = self._read_belief(
                        db, access.scope, row["belief_id"], recorded_as_of, effective_at
                    )
                    if revision is not None:
                        proposal = revision.proposal
                        links = proposal.support_ids + proposal.refute_ids
                        yield revision, self._resolve_evidence(db, access.scope, links)
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot scan canonical memory") from error

    def _resolve_evidence(
        self,
        db: sqlite3.Connection,
        scope: str,
        identifiers: tuple[str, ...],
    ) -> dict[str, Evidence]:
        evidence = {}
        for identifier in identifiers:
            record = self._read_evidence(db, scope, identifier)
            if record is None:
                raise StoreIntegrityError("Canonical evidence link cannot be resolved")
            evidence[identifier] = record
        return evidence

    def create_candidate(
        self, access: AccessContext, request_key: str, proposal: LearningCandidate
    ) -> CandidateRecord:
        if (
            not access.writable
            or access.scope != proposal.scope
            or access.principal != proposal.proposer
        ):
            raise PermissionError("Candidate write denied")
        require_text(request_key)
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                previous = db.execute(
                    """SELECT candidate_id FROM learning_candidate
                       WHERE scope=? AND proposer=? AND request_key=?""",
                    (access.scope, access.principal, request_key),
                ).fetchone()
                if previous is not None:
                    record = self._read_candidate(db, access.scope, previous["candidate_id"])
                    if record.proposal != proposal:
                        raise WriteConflict("Candidate request key already used")
                    return record
                db.execute(
                    "INSERT INTO learning_candidate VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        proposal.scope,
                        proposal.candidate_id,
                        proposal.proposer,
                        proposal.claim,
                        proposal.created_at,
                        request_key,
                    ),
                )
                for role, identifiers in (
                    ("support", proposal.support_ids),
                    ("refute", proposal.refute_ids),
                ):
                    db.executemany(
                        "INSERT INTO candidate_evidence VALUES (?, ?, ?, ?, ?)",
                        (
                            (access.scope, proposal.candidate_id, evidence_id, role, position)
                            for position, evidence_id in enumerate(identifiers)
                        ),
                    )
        except sqlite3.IntegrityError as error:
            raise WriteConflict("Invalid or unavailable candidate reference") from error
        except (sqlite3.DatabaseError, TypeError) as error:
            raise StoreIntegrityError("Cannot store learning candidate") from error
        return CandidateRecord(proposal)

    def get_candidate(self, access: AccessContext, candidate_id: str) -> CandidateRecord | None:
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN")
                return self._read_candidate(db, access.scope, candidate_id)
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot read candidate") from error

    @staticmethod
    def _read_candidate(
        db: sqlite3.Connection, scope: str, candidate_id: str
    ) -> CandidateRecord | None:
        key = (scope, candidate_id)
        row = db.execute(
            "SELECT * FROM learning_candidate WHERE scope=? AND candidate_id=?", key
        ).fetchone()
        if row is None:
            return None
        links = {"support": [], "refute": []}
        for link in db.execute(
            """SELECT role, evidence_id FROM candidate_evidence WHERE scope=? AND candidate_id=?
               ORDER BY position""",
            key,
        ):
            links[link["role"]].append(link["evidence_id"])
        proposal = LearningCandidate(
            candidate_id,
            scope,
            row["proposer"],
            row["claim"],
            row["created_at"],
            tuple(links["support"]),
            tuple(links["refute"]),
        )
        decisions = []
        state = proposal.state
        for entry in db.execute(
            "SELECT * FROM candidate_decision WHERE scope=? AND candidate_id=? ORDER BY version",
            key,
        ):
            request = CandidateTransitionRequest(
                candidate_id,
                scope,
                CandidateState(entry["from_state"]),
                CandidateState(entry["to_state"]),
                entry["actor"],
                entry["rationale"],
                entry["requested_at"],
            )
            request.check_target(proposal, state)
            if entry["version"] != len(decisions) + 1:
                raise StoreIntegrityError("Candidate decision sequence is incomplete")
            decisions.append(CandidateDecision(entry["version"], request, entry["recorded_at"]))
            state = request.to_state
        return CandidateRecord(proposal, tuple(decisions))

    def validate_candidate(
        self, access: AccessContext, candidate_id: str
    ) -> CandidateValidation | None:
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN")
                record = self._read_candidate(db, access.scope, candidate_id)
                return (
                    self._candidate_validation(db, record.proposal) if record is not None else None
                )
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot validate candidate") from error

    def _candidate_validation(
        self, db: sqlite3.Connection, proposal: LearningCandidate
    ) -> CandidateValidation:
        evidence = self._resolve_evidence(
            db, proposal.scope, proposal.support_ids + proposal.refute_ids
        )
        unverified, eligible = [], []
        groups: list[tuple[set[tuple[str, str]], set[str]]] = []
        proposer = proposal.proposer.casefold().strip()
        for identifier in proposal.support_ids:
            record = evidence[identifier]
            actor = record.source_actor.casefold().strip()
            if record.status is not EvidenceStatus.RECORDED or proposer in (
                actor,
                record.producer.casefold().strip(),
            ):
                unverified.append(identifier)
                continue
            eligible.append(identifier)
            keys = {
                ("actor", actor),
                ("locator", record.source_locator.casefold().strip()),
                ("digest", record.digest),
            }
            members = {identifier}
            remaining = []
            for existing_keys, existing_members in groups:
                if keys & existing_keys:
                    keys.update(existing_keys)
                    members.update(existing_members)
                else:
                    remaining.append((existing_keys, existing_members))
            groups = [*remaining, (keys, members)]
        order = {identifier: index for index, identifier in enumerate(eligible)}
        representatives = {min(members, key=order.__getitem__) for _, members in groups}
        independent = [identifier for identifier in eligible if identifier in representatives]
        duplicate = [identifier for identifier in eligible if identifier not in representatives]
        return CandidateValidation(
            tuple(independent), tuple(duplicate), tuple(unverified), proposal.refute_ids
        )

    def decide_candidate(
        self,
        access: AccessContext,
        request_key: str,
        expected_version: int,
        request: CandidateTransitionRequest,
    ) -> CandidateRecord:
        if (
            not access.writable
            or not access.candidate_review
            or request.scope != access.scope
            or request.actor != access.principal
            or request.to_state is CandidateState.PROMOTED
        ):
            raise PermissionError("Candidate decision denied")
        require_text(request_key)
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("Expected a nonnegative candidate version")
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                record = self._read_candidate(db, access.scope, request.candidate_id)
                if record is None:
                    raise WriteConflict("Candidate unavailable")
                prior = db.execute(
                    """SELECT version FROM candidate_decision
                       WHERE scope=? AND candidate_id=? AND actor=? AND request_key=?""",
                    (access.scope, request.candidate_id, access.principal, request_key),
                ).fetchone()
                if prior is not None:
                    decision = record.history[prior["version"] - 1]
                    if decision.request != request or decision.version != expected_version + 1:
                        raise WriteConflict("Candidate decision request key already used")
                    return record
                if record.version != expected_version or request.from_state is not record.state:
                    raise VersionConflict("Expected candidate version or state does not match")
                if request.to_state is CandidateState.APPROVED:
                    result = self._candidate_validation(db, record.proposal)
                    if (
                        access.principal == record.proposal.proposer
                        or len(result.independent_support) < 2
                        or result.refute_ids
                    ):
                        raise PermissionError("Candidate approval denied")
                elif request.to_state is CandidateState.VALIDATED:
                    self._candidate_validation(db, record.proposal)
                decision = CandidateDecision(
                    record.version + 1,
                    request,
                    datetime.now(UTC).isoformat(timespec="microseconds"),
                )
                db.execute(
                    "INSERT INTO candidate_decision VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        access.scope,
                        request.candidate_id,
                        decision.version,
                        request.from_state,
                        request.to_state,
                        access.principal,
                        request.rationale,
                        request.requested_at,
                        decision.recorded_at,
                        request_key,
                    ),
                )
                return CandidateRecord(record.proposal, (*record.history, decision))
        except sqlite3.IntegrityError as error:
            raise WriteConflict("Candidate decision could not be committed") from error
        except sqlite3.DatabaseError as error:
            raise StoreIntegrityError("Cannot record candidate decision") from error

    def sample_learning_evidence(
        self, access: AccessContext, *, since: str, through: str, limit: int
    ) -> tuple[tuple[Evidence, ...], bool]:
        """Read a bounded chronological sample of scoped, small evidence records."""
        since, through = utc_timestamp(since), utc_timestamp(through)
        if since > through or type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("Invalid learning sample window or limit")
        try:
            with closing(self._connect()) as db:
                rows = db.execute(
                    """SELECT * FROM evidence WHERE scope=? AND recorded_at BETWEEN ? AND ?
                       AND length(payload)<=4096
                       ORDER BY recorded_at, evidence_id LIMIT ?""",
                    (access.scope, since, through, limit + 1),
                ).fetchall()
                return tuple(self._decode_evidence(row) for row in rows[:limit]), len(rows) > limit
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot read learning evidence sample") from error

    def append_outcome(
        self,
        access: AccessContext,
        request_key: str,
        expected_version: int,
        feedback: OutcomeFeedback,
    ) -> OutcomeRevision:
        if not access.writable or (access.scope, access.principal) != (
            feedback.scope,
            feedback.producer,
        ):
            raise PermissionError("Outcome write denied")
        require_text(request_key)
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("Expected a nonnegative outcome version")
        key = (access.scope, feedback.episode_id)
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    """SELECT version, candidate_id, producer FROM outcome_revision
                       WHERE scope=? AND episode_id=? ORDER BY version DESC LIMIT 1""",
                    key,
                ).fetchone()
                if current is not None and current["producer"] != access.principal:
                    raise PermissionError("Outcome write denied")
                previous = db.execute(
                    """SELECT * FROM outcome_revision
                       WHERE scope=? AND episode_id=? AND producer=? AND request_key=?""",
                    (*key, access.principal, request_key),
                ).fetchone()
                if previous is not None:
                    result = self._read_outcome(db, previous)
                    if result.feedback != feedback or result.version != expected_version + 1:
                        raise WriteConflict("Outcome request key already used")
                    return result
                if (current["version"] if current else 0) != expected_version:
                    raise VersionConflict("Expected outcome version does not match")
                if current is not None and current["candidate_id"] != feedback.candidate_id:
                    raise WriteConflict("Outcome candidate association is immutable")
                outcome = OutcomeRevision(
                    expected_version + 1,
                    feedback,
                    datetime.now(UTC).isoformat(timespec="microseconds"),
                )
                db.execute(
                    "INSERT INTO outcome_revision VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        *key,
                        outcome.version,
                        feedback.candidate_id,
                        access.principal,
                        feedback.conditions,
                        feedback.predicted,
                        feedback.measured,
                        feedback.measured_at,
                        outcome.recorded_at,
                        request_key,
                    ),
                )
                db.executemany(
                    "INSERT INTO outcome_evidence VALUES (?, ?, ?, ?, ?)",
                    (
                        (*key, outcome.version, evidence_id, index)
                        for index, evidence_id in enumerate(feedback.evidence_ids)
                    ),
                )
                return outcome
        except sqlite3.IntegrityError as error:
            raise WriteConflict("Invalid or unavailable outcome reference") from error
        except (sqlite3.DatabaseError, TypeError) as error:
            raise StoreIntegrityError("Cannot append outcome feedback") from error

    def outcome_history(
        self, access: AccessContext, episode_id: str
    ) -> tuple[OutcomeRevision, ...]:
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN")
                rows = db.execute(
                    "SELECT * FROM outcome_revision WHERE scope=? AND episode_id=? ORDER BY version",
                    (access.scope, episode_id),
                )
                return tuple(self._read_outcome(db, row) for row in rows)
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise StoreIntegrityError("Cannot verify outcome history") from error

    @staticmethod
    def _read_outcome(db: sqlite3.Connection, row: sqlite3.Row) -> OutcomeRevision:
        key = (row["scope"], row["episode_id"], row["version"])
        identifiers = tuple(
            link["evidence_id"]
            for link in db.execute(
                """SELECT evidence_id FROM outcome_evidence
                   WHERE scope=? AND episode_id=? AND version=? ORDER BY position""",
                key,
            )
        )
        feedback = OutcomeFeedback(
            row["episode_id"],
            row["scope"],
            row["candidate_id"],
            row["producer"],
            row["conditions"],
            row["predicted"],
            row["measured"],
            row["measured_at"],
            identifiers,
        )
        return OutcomeRevision(row["version"], feedback, row["recorded_at"])
