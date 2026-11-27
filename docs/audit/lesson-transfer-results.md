# Reviewed pacing lesson transfer (#126)

The measured outcomes show that the reviewed lesson helped this deterministic agent on unfamiliar overload configurations and was too broad for small jobs. It prevented eight buffer-drop mistakes, introduced three slower choices and left correctness unchanged on nine cases. The **frozen key check failed on one tie**, so these are descriptive measurements of the frozen comparison.

| Held-out condition | Pairs | Raw experience | Reviewed lesson | Measured effect |
| --- | ---: | --- | --- | --- |
| Unseen overload | 8 | Direct, dropped items | Paced, no drops | 8 mistakes prevented |
| Previously observed operating point in a new family | 4 | Paced | Paced | 4 unchanged correct |
| Reversal with sufficient headroom | 4 | Direct | Direct, guard did not match | 4 unchanged correct |
| Reversal with short job | 4 | Direct | Paced, guard matched | 3 new slower choices, 1 tie |

Measured correctness was **12/20 raw and 17/20 reviewed**. The same action was chosen on eight pairs. Neither arm missed a deadline. In the eight prevented cases the direct action lost items because a burst exceeded free space. The rule recognized the wide-headroom reversal and left the direct default in place. It still fired on all four short jobs because it compared headroom with a four-item burst even when fewer items remained. In three of those jobs direct completed one tick sooner with no loss.

## Frozen key discrepancy

The frozen key expected direct to be the only winner on `microscope-slides-5`. Direct and paced both finished in two ticks with no drops. The first direct offer left one queued item after the drain. The paced arm used its second tick to send its last item. Both actions were therefore correct under the measured objective, despite the different choices.

The original runner at `1a098c331309b715ac7cb6a95860ae573fc8058c` stopped on this mismatch, as preregistered. The archive runner at `5a13747dd3749f750369e30cdae22ffef320126f` preserves the failed key check and both measured winners and emits the remaining descriptive traces. The cases, key, actor, queue mechanics and measured correctness rule stayed frozen. There was no retuning, additional arm or second lesson. The table uses measured outcomes, with the tied case counted as unchanged correct.

## Evidence and scope

The same stateless deterministic matcher made all decisions. It had no held-out labels or access to current simulator outcomes when deciding. Raw memory recommended the empirical winner at exact previous configurations. The authored lesson made a broader recommendation under an explicit guard. The common budget was two recommendations and 4,096 bytes. Raw occupied 2,362 bytes and reviewed occupied 380 bytes.

The disposable SQLite ledger preserved two source IDs, both successful review transitions, and measured-to-date and final revisions of direct-transfer retention. The approved candidate remained staged, survived restart, appeared in no canonical belief and was inaccessible from another scope. The decision replay left the ledger unchanged. The four work-cell families share queue mechanics, so this is transfer of an authored condition across new configurations and task names. It does not measure automatic lesson generation, a model agent, or raw-memory policies that generalize beyond exact matches.

The [frozen protocol](lesson-transfer-protocol.md), cases, key and actor were committed at `128feccd225b4630ee0e53791e0f0b523f3c27db`. The [archive](lesson-transfer-replay.json) contains the two paired memory packets, source-linked review and measured revisions, every decision, and tick-by-tick traces for both possible actions in all 20 cases. An independent recount confirmed the physical outcomes and paired counts from those traces. Two audit replays matched byte for byte at SHA-256 `72e1b17329119ed798563ac9b52e1e8e176f5c459f8a9d4a7b9c902858065d6b`.

**Next action:** Independently review the frozen key discrepancy and measured traces before deciding whether to test a lesson that accounts for the actual offered batch size.

Local Python 3.12.14 validation passed format, lint, compile, all 245 unit tests and the MCP demo.

## Exact replay

```sh
PYTHONPATH=src python scripts/evaluate_lesson_transfer.py > /tmp/aams-lesson-transfer.json
cmp docs/audit/lesson-transfer-replay.json /tmp/aams-lesson-transfer.json
sha256sum /tmp/aams-lesson-transfer.json
```

The replay JSON exposes `frozen_key_check_passed: false` and the mismatch explicitly.

```sh
python -m pip install '.[mcp]' ruff==0.14.6
ruff format --check src scripts tests
ruff check src scripts tests
python -m compileall -q src scripts tests
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```
