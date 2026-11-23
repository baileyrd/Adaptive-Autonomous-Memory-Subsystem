# AAMS agent workflow

Repository: https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem
Goal: https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/1

## Start or resume
- Read main, the active coordination issue and its work queue, linked PRs, CI, review feedback, and `docs/MVP_SPEC.md`.
- Do not create overlapping implementations or duplicate PRs.
- Work on the first dependency-unblocked issue from the active coordination hub.
- Use the [AAMS v0.1.0 design dossier](docs/design/v0.1.0/README.md) and follow the scope reconciliation in the MVP specification.
- Keep canonical data semantics independent of MCP and optional neural indexes.

## GitHub coordination

- For v0.4 work, use [issue #34](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/34) as the coordination hub. Issues #1, #14 and #23 retain the previous milestones. Read its latest comments when starting, resuming, and before moving to another implementation slice.
- Follow the links to the active implementation issue and PR. Read the PR conversation, review submissions, and inline review threads. Check CI on the current head and address or explicitly route outstanding findings before advancing.
- At each handoff, update the active coordination issue with the implementation issue and PR, current state, verification, any blockers, and one next action. Record code-specific findings and their resolution on the associated PR so the next session can pick up directly from GitHub.

## Development loop
Plan -> implement one bounded vertical slice -> validate locally -> open linked PR -> address material findings -> merge **only if authorized** and required CI/repository protections pass -> advance. Independent review is encouraged when available, but it is not an AAMS-imposed prerequisite. Never fabricate checks, invent Codex task IDs, or claim CI passed without run evidence. Prefer direct, reproducible tests and one clear next action. Preserve all GitHub issue/PR links for resumption.

## Code contract
- Evidence is immutable; beliefs are explicitly revised rather than overwritten.
- Every persisted record has scope, identity, provenance, and temporal metadata.
- Unauthorized reads must not reveal whether protected memory exists.
- Model output is not independent evidence by repetition.
- Every MCP tool uses the same policy and domain validation as internal APIs.
- Keep dependencies minimal and record architecture decisions as ADRs.

## Review gate
No merge until actual head-specific required checks are green, material findings are resolved or explicitly documented with rationale, and GitHub branch protections and repository policy permit merging. An independent approving review is **not required by the AAMS project workflow** unless GitHub itself enforces one. Authorized agents may merge routine changes without owner approval. A draft PR is appropriate when acceptance is incomplete.
