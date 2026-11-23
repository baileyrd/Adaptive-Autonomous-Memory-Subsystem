# AAMS v0.2 engineering baseline

This audit advances the [v0.1 MVP](MVP-v0.1.md) through bounded recovery, MCP runtime and retrieval changes. The v0.1 release and its recorded results remain historical evidence.

## Verified implementation heads

| Slice | Tested PR head | CI |
| --- | --- | --- |
| Canonical recovery verification (#15) | `5e3ce8f` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45160664080) |
| Local stdio limits (#16) | `f920e8500b59f3dcd2f216d30228ecccafbeaf99` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45160945006) |
| Recall scaling (#17) | `e0869d2b85f1cf927c02fff7b3c7dd26a6faf1ab` | [Python 3.11 and 3.12](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/actions/runs/45161487888) |

The integrated implementation at `6749967` is the base of this matrix. The [v0.2 coordination issue](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/14) records the final integrated commit and CI run.

## Acceptance matrix

Install and set up the repository as described in the [README](../../README.md). The check and demo commands are the same on Linux with Python 3.11 or 3.12 and Python MCP SDK 2.3.0.

| Area | Status and evidence |
| --- | --- |
| Canonical integrity, backup and restore | **PASS.** The audit reproduced two post-recovery gaps in full verification and corrected them. In-memory or temporary-database tests cover incomplete provenance, malformed digests and timestamps, broken scoped links, and the SQLite backup API. Run the audit, storage and recovery groups. [Initial audit](../audit/v0.2-initial.md) |
| Interrupted writes and restart | **PASS.** Barrier-driven subprocess termination exercises before-commit rollback and after-commit durability. The standalone demo starts separate client and service processes, verifies the original observation and digest after restart, reconstructs historical belief and checks authorization. |
| Scoped and temporal reads | **PASS.** Fixtures check exact and ranked scope filtering, support/refute links, deterministic ties, time cutoffs and concurrent revision conflicts. Ranked recall reads one SQLite snapshot with the same canonical scoring and evidence decoding as before. [Recall contract](../recall.md) |
| MCP frame and tool validation | **PASS.** The real-process tests cover the 256 KiB frame limit, fixed stderr diagnostic, protocol envelopes, argument bounds, immutable launch grant, cross-scope responses, and a relaunch with writes revoked. [MCP contract](../mcp.md) |
| Recall scaling | **PASS.** Repeated matched runs at 264, 1,032 and 4,104 formations showed lower contextual latency on all datasets. The largest case improved from 155–156 ms median to 15–17 ms, with the same database footprint. [Benchmark and limitations](../audit/recall-scaling.md) |
| Independent approval | **NOT OBTAINED.** The coordination policy encourages independent review when available. GitHub protections and verified current-head CI remain mandatory. |
| Disk-full, operating-system power loss and non-Linux | **NOT TESTED.** Process termination is the tested fault model. |
| Write contention during long ranking scans | **NOT TESTED.** The single-snapshot scan holds a read transaction while reading and ranking the eligible corpus. |
| Other client profiles and in-process grant revocation | **NOT TESTED.** This baseline tests local stdio with the pinned SDK. The host terminates and relaunches a child to revoke a process grant. |

```sh
ruff format --check src tests scripts
ruff check src tests scripts
python -m compileall -q src tests scripts
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```

## Operational limits

Keep the SQLite files and backups in a private directory. The host that supplies launch grants and controls direct file access is trusted. The integrity check verifies structural consistency and canonical invariants. It does not attest the origin of a database or detect every logically valid content change. Restore from a verified backup using the [README procedure](../../README.md).

The stdio adapter limits individual frames before SDK parsing. A disconnected or cancelled request may already have committed. Retry observation ingestion with the same key or read the current belief revision before attempting another update. Evidence content remains unverified model input, even when it resembles instructions. Provider behavior on that input is outside the server guarantee.

## Next phase

Start with scoped, inspectable learning candidates that link to existing evidence and name the proposer. Keep candidates separate from canonical evidence and authoritative beliefs. Require explicit approval and independent provenance checks before any promotion. Evaluate candidate usefulness and false promotion on a fixed offline corpus against this lexical baseline. Record criteria and measured results before considering any autonomous consolidation.
