"""Scope-bound, disposable vectors in the canonical store's SQLite database."""

import sqlite3
import struct
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from .contracts import utc_timestamp
from .representations import (
    DerivedVector,
    RepresentationProvider,
    RepresentationSpec,
    create_derived_vector,
)

_SCHEMA = (
    """CREATE TABLE representation_batch (
        scope TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, version TEXT NOT NULL,
        dimensions INTEGER NOT NULL, evidence_count INTEGER NOT NULL, vector_count INTEGER NOT NULL,
        generated_at TEXT NOT NULL, PRIMARY KEY(scope, provider, model, version, dimensions)
    )""",
    """CREATE TABLE representation_vector (
        scope TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, version TEXT NOT NULL,
        dimensions INTEGER NOT NULL, evidence_id TEXT NOT NULL, digest TEXT NOT NULL,
        values_blob BLOB NOT NULL, checksum TEXT NOT NULL,
        PRIMARY KEY(scope, provider, model, version, dimensions, evidence_id),
        FOREIGN KEY(scope, provider, model, version, dimensions)
           REFERENCES representation_batch(scope, provider, model, version, dimensions) ON DELETE CASCADE,
        FOREIGN KEY(scope, evidence_id) REFERENCES evidence(scope, evidence_id)
    )""",
)

_WHERE = "scope=? AND provider=? AND model=? AND version=? AND dimensions=?"


@dataclass(frozen=True, slots=True)
class RepresentationSnapshot:
    status: str
    vectors: tuple[DerivedVector, ...] = ()
    generated_at: str | None = None


def _key(access, spec):
    return (access.scope, spec.provider_id, spec.model_id, spec.model_version, spec.dimensions)


def _count(db, scope):
    return db.execute("SELECT count(*) FROM evidence WHERE scope=?", (scope,)).fetchone()[0]


class RepresentationIndex:
    def __init__(self, store):
        self.store = store

    def rebuild(self, access, provider: RepresentationProvider) -> RepresentationSnapshot:
        if not access.writable:
            raise PermissionError("Representation rebuild denied")
        spec = provider.spec
        key = _key(access, spec)
        previous = self.snapshot(access, spec)
        if previous.status == "fresh":
            return previous
        with self.store._reading() as db:
            db.execute("BEGIN")
            count = _count(db, access.scope)
            records = tuple(
                self.store._decode_evidence(row)
                for row in db.execute(
                    "SELECT * FROM evidence WHERE scope=? AND length(payload) BETWEEN 1 AND 4096 ORDER BY evidence_id",
                    (access.scope,),
                )
            )
        generated = datetime.now(UTC).isoformat(timespec="microseconds")
        vectors = []
        for record in records:
            try:
                text = record.payload.decode()
            except UnicodeDecodeError:
                continue
            vector = create_derived_vector(
                provider,
                source_id=record.evidence_id,
                scope=access.scope,
                source_payload=record.payload,
                text=text,
                generated_at=generated,
            )
            if vector.spec != spec:
                raise ValueError("Provider changed representation space during rebuild")
            vectors.append(vector)
        with self.store._index_publication(access.scope), closing(self.store._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if _count(db, access.scope) != count:
                return RepresentationSnapshot("stale")
            db.execute("DELETE FROM representation_batch WHERE " + _WHERE, key)
            db.execute(
                "INSERT INTO representation_batch VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (*key, count, len(vectors), generated),
            )
            for vector in vectors:
                blob = struct.pack(f"<{spec.dimensions}d", *vector.values)
                db.execute(
                    "INSERT INTO representation_vector VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (*key, vector.source_id, vector.source_digest, blob, sha256(blob).hexdigest()),
                )
        return RepresentationSnapshot("fresh", tuple(vectors), generated)

    def snapshot(self, access, spec: RepresentationSpec) -> RepresentationSnapshot:
        key = _key(access, spec)
        try:
            with self.store._reading() as db:
                db.execute("BEGIN")
                batch = db.execute(
                    "SELECT * FROM representation_batch WHERE " + _WHERE, key
                ).fetchone()
                if batch is None:
                    return RepresentationSnapshot("missing")
                generated_at = utc_timestamp(batch["generated_at"])
                if batch["evidence_count"] != _count(db, access.scope):
                    return RepresentationSnapshot("stale")
                rows = db.execute(
                    "SELECT * FROM representation_vector WHERE " + _WHERE + " ORDER BY evidence_id",
                    key,
                )
                vectors = []
                for row in rows:
                    source = self.store._read_evidence(db, access.scope, row["evidence_id"])
                    blob = row["values_blob"]
                    if (
                        source is None
                        or source.digest != row["digest"]
                        or sha256(blob).hexdigest() != row["checksum"]
                    ):
                        return RepresentationSnapshot("corrupt")
                    vectors.append(
                        DerivedVector(
                            row["evidence_id"],
                            access.scope,
                            row["digest"],
                            generated_at,
                            spec,
                            struct.unpack(f"<{spec.dimensions}d", blob),
                        )
                    )
                if len(vectors) != batch["vector_count"]:
                    return RepresentationSnapshot("corrupt")
                return RepresentationSnapshot("fresh", tuple(vectors), generated_at)
        except (sqlite3.DatabaseError, struct.error, ValueError, TypeError):
            return RepresentationSnapshot("corrupt")

    def invalidate(self, access, spec: RepresentationSpec) -> None:
        if not access.writable:
            raise PermissionError("Representation invalidation denied")
        with self.store._index_publication(access.scope), closing(self.store._connect()) as db, db:
            db.execute("DELETE FROM representation_batch WHERE " + _WHERE, _key(access, spec))
