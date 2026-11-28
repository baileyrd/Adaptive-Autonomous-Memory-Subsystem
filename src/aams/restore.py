"""Open a guarded, scope-local projection of a verified SQLite backup."""

import json
import shutil
import sqlite3
from contextlib import closing, contextmanager
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryDirectory

from .storage import SQLiteMemoryStore, StoreIntegrityError

_CLOSURE = ("evidence", "formations", "beliefs", "candidates", "episodes")
_INDEX_TABLES = {"representation_batch", "representation_vector"}
# Keep whole revision chains. Dropping only a tainted revision can make an older
# claim appear current, or leave a descendant carrying its parent's content.
_LINKS = (
    ("formations", "formation_evidence", "formation_id"),
    ("beliefs", "belief_evidence", "belief_id"),
    ("candidates", "candidate_evidence", "candidate_id"),
    ("episodes", "outcome_evidence", "episode_id"),
)
_COPY = (
    ("evidence", "evidence", "evidence_id"),
    ("formation", "formations", "formation_id"),
    ("formation_evidence", "formations", "formation_id"),
    ("belief_revision", "beliefs", "belief_id"),
    ("belief_evidence", "beliefs", "belief_id"),
    ("learning_candidate", "candidates", "candidate_id"),
    ("candidate_evidence", "candidates", "candidate_id"),
    ("candidate_decision", "candidates", "candidate_id"),
    ("outcome_revision", "episodes", "episode_id"),
    ("outcome_evidence", "episodes", "episode_id"),
)
_TABLES = {table for table, _, _ in _COPY} | _INDEX_TABLES | {"ingestion", "retrieval_observation"}


class RestoreUnavailable(StoreIntegrityError):
    """This scope cannot prove that its restored view is current."""

    def __init__(self):
        super().__init__("Restored scope unavailable")


def _uri(path, mode):
    return Path(path).resolve().as_uri() + "?mode=" + mode


def _unique_members(pairs):
    members = {}
    for key, value in pairs:
        if key in members:
            raise RestoreUnavailable()
        members[key] = value
    return members


@contextmanager
def _lease(authority, scope, backup_digest):
    # An external writer advancing the head must serialize with publication.
    # BEGIN IMMEDIATE keeps that invariant in WAL and rollback-journal modes.
    try:
        with closing(sqlite3.connect(_uri(authority, "rw"), uri=True)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT h.generation, c.closure
                   FROM restore_scope_head h JOIN restore_coverage c
                     ON h.scope=c.scope AND h.generation=c.generation
                   WHERE h.scope=? AND c.backup_sha256=? AND c.complete=1""",
                (scope, backup_digest),
            ).fetchone()
            if row is None or type(row[0]) is not int or row[0] < 0:
                raise RestoreUnavailable()
            closure = json.loads(row[1], object_pairs_hook=_unique_members)
            if (
                not isinstance(closure, dict)
                or set(closure) != set(_CLOSURE)
                or any(
                    not isinstance(ids, list)
                    or any(not isinstance(i, str) or not i for i in ids)
                    or len(set(ids)) != len(ids)
                    for ids in closure.values()
                )
            ):
                raise RestoreUnavailable()
            yield row[0], row[1], closure
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        raise RestoreUnavailable() from exc


def _project(backup, store, scope, closure):
    with closing(sqlite3.connect(_uri(store.path, "rw"), uri=True)) as db, db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("ATTACH DATABASE ? AS snapshot", (_uri(backup, "ro"),))
        db.execute("BEGIN")
        tables = {
            name
            for (name,) in db.execute(
                "SELECT name FROM snapshot.sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        expected_version = db.execute("PRAGMA main.user_version").fetchone()
        if (
            tables != _TABLES
            or db.execute("PRAGMA snapshot.user_version").fetchone() != expected_version
        ):
            raise RestoreUnavailable()
        if (
            db.execute("PRAGMA snapshot.integrity_check").fetchall() != [("ok",)]
            or db.execute("PRAGMA snapshot.foreign_key_check").fetchone() is not None
        ):
            raise RestoreUnavailable()

        for kind, ids in closure.items():
            db.execute(f"CREATE TEMP TABLE denied_{kind}(id TEXT PRIMARY KEY)")
            db.executemany(f"INSERT INTO denied_{kind} VALUES (?)", ((i,) for i in ids))
        for kind, table, column in _LINKS:
            db.execute(
                f"""INSERT OR IGNORE INTO denied_{kind}
                    SELECT {column} FROM snapshot.{table}
                    WHERE scope=? AND evidence_id IN (SELECT id FROM denied_evidence)""",
                (scope,),
            )
        db.execute(
            """INSERT OR IGNORE INTO denied_episodes
               SELECT episode_id FROM snapshot.outcome_revision
               WHERE scope=? AND candidate_id IN (SELECT id FROM denied_candidates)""",
            (scope,),
        )
        for table, kind, column in _COPY:
            db.execute(
                f"""INSERT INTO main.{table}
                    SELECT * FROM snapshot.{table}
                    WHERE scope=? AND {column} NOT IN (SELECT id FROM denied_{kind})""",
                (scope,),
            )


def _read_only_canonical(operation, table, _column, database, _trigger):
    if operation in {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}:
        if database != "main" or table not in _INDEX_TABLES:
            return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class _RestoredStore(SQLiteMemoryStore):
    def __init__(self, path, authority, scope, backup_digest, head):
        # The private projection already has the current verified schema.
        self.path = path
        self._authority = authority
        self._scope = scope
        self._backup_digest = backup_digest
        self._head = head

    def _deny_canonical_write(self, *_args, **_kwargs):
        raise PermissionError("Restored scope is read-only")

    ingest = revise = create_candidate = decide_candidate = append_outcome = _deny_canonical_write

    def _connect(self):
        db = sqlite3.connect(_uri(self.path, "rw"), uri=True)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA synchronous = FULL")
            db.set_authorizer(_read_only_canonical)
            return db
        except BaseException:
            db.close()
            raise

    @contextmanager
    def _index_publication(self, scope):
        if scope != self._scope:
            raise PermissionError("Restore scope mismatch")
        with _lease(self._authority, scope, self._backup_digest) as (generation, raw, _):
            if (generation, raw) != self._head:
                raise RestoreUnavailable()
            yield

    def check_current(self):
        with self._index_publication(self._scope):
            pass


@contextmanager
def open_restored_scope(backup, authority, scope):
    """Yield a guarded view. The host supplies the trusted external authority path."""
    backup, authority = Path(backup).resolve(), Path(authority).resolve()
    with TemporaryDirectory(prefix="aams-restore-") as directory:
        root = Path(directory)
        captured = root / "quarantined.sqlite"
        try:
            if authority.samefile(backup):
                raise RestoreUnavailable()
            # Require a standalone SQLite backup rather than copying a live DB.
            if any(Path(str(backup) + suffix).exists() for suffix in ("-wal", "-journal")):
                raise RestoreUnavailable()
            shutil.copyfile(backup, captured)
            with captured.open("rb") as source:
                digest = file_digest(source, "sha256").hexdigest()
            with _lease(authority, scope, digest) as (generation, raw, closure):
                head = generation, raw
            path = root / "projection.sqlite"
            store = SQLiteMemoryStore(path)
            _project(captured, store, scope, closure)
            store.verify_integrity()
            view = _RestoredStore(path, authority, scope, digest, head)
            view.check_current()
        except (OSError, sqlite3.Error, StoreIntegrityError) as exc:
            raise RestoreUnavailable() from exc
        yield view
