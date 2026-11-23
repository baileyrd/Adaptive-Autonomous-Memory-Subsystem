# AAMS v0.1 MVP acceptance

Scope comes from [goal #1](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/1) and the [MVP acceptance contract](../MVP_SPEC.md). This record describes the release candidate. See the linked release PR for its exact tested commit and CI run. Local results below were captured on Linux x86-64, Python 3.12.14, SQLite 3.53.1 and MCP SDK 2.3.0.

## Verification matrix

From a fresh checkout, use the [README setup](../../README.md), then run `PYTHONPATH=src python -m unittest discover -s tests -v`. To run one group, add `-p 'test_storage.py'` or the corresponding filename below. The Python 3.11 and 3.12 CI jobs run the same suite, format, lint and compilation checks, and the standalone demo.

| Requirement | Reproduction and observed result | Status |
| --- | --- | --- |
| Start a local, model-neutral service and store a scoped observation | `python -m aams.demo` launches the collector client and stdio child. `test_storage.py` checks stable IDs, immutable bytes, SHA-256, timestamps, provenance and transaction replay. | PASS |
| Restart and retrieve the original via MCP | The collector client and child exit before the analyzer client and fresh child open the same file. The demo returns `Rain gauge recorded 12 mm.` and verifies the stored digest. | PASS |
| Revise a derived belief with evidence and reconstruct prior knowledge | The demo returns `Rainfall was 12 mm.` for the prior revision and `Rainfall was reported as 12 mm; calibration is uncertain.` for the current one. `test_beliefs.py` covers corrected effective dates, schema upgrades, competing writers and retained history. | PASS |
| Explain the current belief with provenance and contradictions | The demo returns evidence roles `support` and `refute`. `test_recall.py` verifies scoped exact reads, temporal filtering, deterministic ranking, bounded results and provenance. The fixed fixture measured precision@2 of 1.0. | PASS |
| Verify permissions and model-output boundaries | The demo returns an empty packet for the out-of-scope belief and `ACCESS_DENIED` for a write. `test_mcp.py` uses overlapping scoped belief IDs, checks forged scope and relaunch with a read-only grant, and verifies instruction-like text stays unverified evidence with its producer and origin. `test_beliefs.py` checks scope-mismatched links and revision rollback. | PASS |
| Verify four MCP tools and protocol behavior | `test_mcp.py` uses the SDK client and raw stdio against running children. It checks discovery, tool listing, all four calls, schemas, malformed frames, argument bounds, missing metadata, unsupported versions and an error stream without the malformed input marker. | PASS |
| Demonstrate crash durability and recovery | `test_recovery.py` stops children at explicit SQLite barriers before ingestion and revision commit and after ingestion commit. Reopening shows no partial state and retains committed data. Backup and restore recover an intact copy after corrupting a link. `test_storage.py` detects altered payloads and unsupported schemas. | PASS |
| Verify documented local setup and automated checks | The README documents installation, host config and backup/restore. Local Ruff formatting, lint, compilation and all 25 tests passed. The release PR records head-specific CI evidence. | PASS locally |
| Verify independent release review | Issue #7 requests a distinct eligible reviewer and an approval link. See the release PR for the current decision. | PENDING |

## Fault harness and limits

The crash tests use temporary databases. A connection-local test trigger emits a pipe marker immediately before a final ingestion write or before a revision link insert. The parent kills the child only after receiving the marker. A separate case kills the child after the ingestion API returns successfully. Restart checks confirm both rolled-back and durable outcomes. The suite also runs an online SQLite backup and opens the copy in place.

Disk-full, operating-system power loss, live revocation inside an already launched stdio process, and operating systems beyond Linux were **not tested**. For revocation, the trusted host terminates the existing server and relaunches with a new grant. Tool inputs and returned packets have application budgets. There is no separate AAMS limit on SDK wire frame allocation before parsing. Scope checks cover API responses within the trusted local host model, and no constant-time guarantee is made. The server does not execute evidence text. A host model may still be influenced by text it reads.

## Measured baseline

Run `PYTHONPATH=src python scripts/benchmark.py --records 256 --samples 40 --warmup 8`. The generator uses seed 1081, four scopes and 264 formations including warmup, with repeated payloads and a belief with two contradicting revisions. The measurements cover native Python ingestion and recall without MCP transport overhead.

| Operation | Median | p95 |
| --- | ---: | ---: |
| Atomic ingestion | 0.241 ms | 0.379 ms |
| Exact lookup with provenance | 0.279 ms | 0.441 ms |
| Contextual recall | 20.623 ms | 22.509 ms |

Measured ingestion throughput was 3,771.7 records/s over the timed writes. The SQLite file was 237,568 bytes. A separate traced contextual query peaked at 66,993 bytes of Python allocations. These measurements describe one synthetic run on Linux 6.18.57 x86-64 and do not include process RSS or predict other deployments.
