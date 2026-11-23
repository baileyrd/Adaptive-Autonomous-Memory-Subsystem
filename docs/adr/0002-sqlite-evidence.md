# ADR-0002 · Local canonical storage

Date: 2026-11-23  
Status: Accepted for the MVP evidence slice

Use SQLite through Python's standard library. A single local database holds immutable evidence bytes, formation metadata, ordered scoped links, and replay keys. SQLite supplies transactions and foreign keys without operating a separate database service. A flat file would require custom transaction and recovery logic. Storing blobs externally would require coordinating commits across two resources.

Every ingestion uses one immediate transaction with foreign keys enabled and full synchronization. Composite references enforce scope consistency. Evidence IDs and formation IDs are caller-assigned and unique within their respective record types. Evidence update and delete triggers protect ordinary SQL writes. The local host must restrict direct database access to trusted processes.

The host binds the principal and scope before calling storage. A write grant is explicit. Reads outside the bound scope return the same result as unknown IDs. Replay keys are scoped to principal and scope. Identical normalized inputs return the same formation. Changed inputs using the same key cause a conflict. Payload integrity uses the digest `sha256:<lowercase hexadecimal>` over the exact bytes. A valid digest establishes content correspondence. It does not verify the source's claims.

The first migration creates schema 1 and sets SQLite `user_version` in the same transaction. Opening a newer schema fails without rewriting it. New versions must add ordered transactional migrations and upgrade tests. Integrity failures surface as errors. Operators can verify the database with `SQLiteMemoryStore.verify_integrity()` and restore from a known-good backup when needed.

The issue #3 tests cover a fresh database, a second-process read, invalid links, rollback, replay, and digest corruption. Belief revisions and broader authorization build on this storage seam in issue #4.
