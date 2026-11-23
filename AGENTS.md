# AAMS agent workflow

Repository: https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem
Goal: https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/1

## Start or resume
- Read main, open issues #1–#7, PRs, CI, previous review feedback and `docs/MVP_SPEC.md`.
- Do not create overlapping implementations or duplicate PRs.
- Work on the first dependency-unblocked issue in order #2, #3, #4, #5, #6, #7.
- Use the original AAMS v0.1.0 concept/design dossier when available. If it is missing from the repository, report this as a documentation import gap.
- Keep canonical data semantics independent of MCP and optional neural indexes.

## Development loop
Plan -> implement one bounded vertical slice -> validate locally -> open linked PR -> independent review -> fix findings -> merge **only if authorized** and CI/review requirements pass -> advance. Never fabricate checks, invent Codex task IDs, or claim CI passed without run evidence. Prefer direct, reproducible tests and one clear next action. Preserve all GitHub issue/PR links for resumption.

## Code contract
- Evidence is immutable; beliefs are explicitly revised rather than overwritten.
- Every persisted record has scope, identity, provenance, and temporal metadata.
- Unauthorized reads must not reveal whether protected memory exists.
- Model output is not independent evidence by repetition.
- Every MCP tool uses the same policy and domain validation as internal APIs.
- Keep dependencies minimal and record architecture decisions as ADRs.

## Review gate
No merge until actual head-specific checks are green, all relevant threads addressed, and independent approval is present according to repository policy. A draft PR is appropriate when acceptance is incomplete.
