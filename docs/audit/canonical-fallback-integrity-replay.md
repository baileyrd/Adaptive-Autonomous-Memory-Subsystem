# PR #131 integrity replay

This supplement reconciles the physical fingerprint in the [first-run evidence](canonical-fallback-results.json) and the [independent review](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/pull/131#pullrequestreview-6049078135). It reruns the frozen preparer and three readers from `794e637` on the original cases. Each replay verifies the archived trace hash and compares all 252 decision objects. The first-run artifacts and source pins remain at `ecf70d6`.

| Replay environment | Physical manifest SHA-256 | Matches first-run manifest |
| --- | --- | --- |
| [Producer-environment replay, Python 3.14.8 / SQLite 3.51.2](canonical-fallback-integrity-producer-replay.json) | `1f5fc81a2e15f02f65fe219c25716ef3d227db441f426e6634a540797167e016` | Yes |
| [Alternate replay, Python 3.12.16 / SQLite 3.54.1](canonical-fallback-integrity-alternate-replay.json) | `752be02ad4ab2e50378a3b4d6ceba558c7e6f13b6dccd287bc6ecddaa41d6f19` | No |

**Within each run**, all 79 per-file hashes matched the preparer after each of the three readers exited. Each JSON links the measured SQLite version to four complete snapshots. **Between runs**, all 78 sidecars matched. The only differing file was `memory.db`. Its logical digest in all eight snapshots was `b214b870ab4c7448b3738e318459f6a409e78f87dd356c0c5f1983ca73e3433d`.

The original run recorded Python/platform and the combined physical digest, but omitted SQLite version and individual hashes. The producer-environment replay records those details now and reproduces the historical digest. The replay provides a matching baseline; its SQLite version was measured during replay. The alternate replay establishes equality of schema and table contents across these two environments. It does not identify the origin of every differing byte or reconstruct the reviewer's unarchived individual file hashes.

## Reproduction

Run `python scripts/replay_fallback_integrity.py > integrity.json` from a clean Linux checkout. Compare the `files` maps by filename at the prepare stage and after each reader. Compare `logical_sha256` across environments. The standalone observer opens the database with SQLite read-only mode. It leaves the decision path and scoring unchanged.

The versioned logical digest covers the user version, sorted catalog definitions (tables, indexes, triggers and views with SQL), column order and the multiset of typed rows in each table. It preserves duplicate rows, represents BLOBs as tagged hexadecimal and sorts encoded rows independently of insertion order. It excludes file headers, page allocation, implicit row identifiers and other storage layout details. The physical manifest remains the within-run check for all bytes. These measurements concern the disposable fixtures; the original fallback and #130 scorecards retain their published denominators.
