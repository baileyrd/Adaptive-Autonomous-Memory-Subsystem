"""Scoped, transactional SQLite storage for canonical evidence and formations."""

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from .contracts import (
    EpistemicState,
    Evidence,
    EvidenceStatus,
    MemoryFormation,
    MemoryKind,
    require_text,
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


class WriteConflict(ValueError):
    """A canonical identifier, evidence link or idempotency key conflicts."""


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
                if version == 0:
                    for statement in _SCHEMA:
                        db.execute(statement)
                    db.execute("PRAGMA user_version = 1")
                elif version != 1:
                    raise StoreIntegrityError(f"Unsupported database schema version {version}")
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
