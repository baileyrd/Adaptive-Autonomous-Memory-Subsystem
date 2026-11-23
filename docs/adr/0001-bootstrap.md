# ADR-0001: Provisional MVP bootstrap and module boundaries

Date: 2026-11-22
Status: **Proposed**, pending independent review in #2

## Context
The original AAMS concept intentionally does not prescribe an existing implementation or language. The next slice needs a reproducible test/build environment without forcing neural, vector, distributed or transport choices prematurely.

## Decision (provisional)
Use a Python 3.11+ stdlib-first modular monolith for the initial MVP iteration, with durable storage technology and the specific MCP adapter library selected on measured compatibility evidence in later slices. Keep domain contracts pure and independent from storage/adapters. Use unit tests and GitHub Actions immediately. Python was chosen to minimize first-demo setup friction and allow direct agent-host integration; not because it was a prior user preference.

## Alternatives
Rust: stronger static safety and systems deployment advantages but adds integration and build friction for the first prototype. Multi-service architecture: adds needless distributed consistency overhead before the semantics are validated. Pure vector database: cannot represent authoritative evidence and temporal revisions by itself.

## Constraints
- Zero hidden network/model dependency in core tests.
- Future storage must provide transactions, restart persistence, and schema migration support.
- Verify MCP specification and actual SDK/client versions before implementing wire semantics.
- Supersede this ADR if the evidence or implementation risk changes; don't silently switch stacks.

## Review questions
Is Python the right implementation target for production? Should durable storage start with SQLite, or another transactional engine? What is the minimum supported MCP transport/profile? These are not prerequisites to creating the contract scaffold.
