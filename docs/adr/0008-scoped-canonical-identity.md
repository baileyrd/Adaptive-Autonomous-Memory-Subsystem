# ADR-0008 — Scope-keyed canonical identity

Date: 2026-11-23
Status: Proposed, pending verified migration CI

## Problem
In schemas 1–6, evidence_id and formation_id were globally unique. An otherwise authorized writer in scope B could infer that an ID already existed in another scope from a uniqueness conflict in its own ingest, despite scoped reads suppressing the record.

## Decision
Schema 7 uses (scope, evidence_id) and (scope, formation_id) as primary keys, and qualifies the formation/evidence link primary and unique keys by scope. Canonical public signatures remain unchanged.

Existing tables are rebuilt in one opening transaction using SQLite's create/copy/drop/rename approach. Foreign-key enforcement is disabled only on the dedicated migration connection before BEGIN; foreign_key_check runs before commit. If violated, the transaction rolls back, leaving the previous schema version intact. The evidence immutability triggers are recreated.

## Security and operations
MCP-generated IDs already incorporate scope and principal; the direct library was the demonstrated collision channel. The migration is designed to preserve dependent links (belief, candidate, outcome, representation, ingestion) and idempotency records. Back up the database before applying migrations and test opening a representative populated schema-6 backup. Successful foreign_key_check is not a guarantee of full application-level integrity; verify_integrity must also pass.

## Limitations
This does not protect against a process with unrestricted raw SQLite file access or address encrypted/remote tenancy. Direct library writes remain authorized by trusted AccessContext. Schema migration is irreversible without a supported restore procedure.
