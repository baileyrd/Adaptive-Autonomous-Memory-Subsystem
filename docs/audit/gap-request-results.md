# When the staged request helped (#128)

**Asking was useful when the authorized packet lacked a decision-critical reading and the reviewer had a genuinely new, current receipt.** That happened on four of 16 tickets. Four other tickets recovered an already readable observation, which improved task completion but could have been handled by exact lookup before asking. Eight tickets produced no usable evidence.

| Mechanism | Baseline → candidate on four cases | Requests | New usable readings | Existing readings recovered |
| --- | --- | ---: | ---: | ---: |
| Reading surfaced | Correct → correct | 0 | 0 | 0 |
| Missing with current receipt | Abstain → correct | 4 | 4 | 0 |
| Overlooked scoped reading | Abstain → correct | 4 | 0 | 4 |
| Missing with empty inbox | Abstain → abstain | 4 | 0 | 0 |
| Missing with stale receipt | Abstain → abstain | 4 | 0 | 0 |

Supported correct decisions improved from **4/20 to 12/20**. Eight paired decisions improved, zero worsened and 12 were unchanged. There were zero incorrect substantive actions. Incomplete abstentions fell from 16 to eight. Eight uncertainties resolved, split equally between new and recovered evidence. Four requests were unnecessary because exact lookup could already find the reading. No-receipt and stale-receipt tickets account for the eight unresolved requests.

The candidate required 16 local ticket reviews, 16 manifest validations, 16 exact observation lookups and 12 inbox checks. The baseline required none. That is two processed tickets per improved decision, and four per decision improved using genuinely new information. These counts measure the fixed synthetic procedure. No real reviewer time, monetary cost or preference was measured.

## Scope and provenance

Each staged request in the archive lists the exact round and instrument, the scoped manifest ID and digest, what remains unknown, and how pass or fail could change the abstention. The reviewer used only the same scoped exact lookup and the pre-existing independent fixture inbox. Stale feedback was excluded. The inbox was never written into the native ledger, which remained unchanged in all primary and shadow runs.

All eight foreign-only shadows produced exactly the corresponding absent-case public responses in both arms, before and after review, and identical initial authorized packets. Four had a separately supplied local receipt and four had none. The harness verified that the foreign record existed under its own scope grant and that its ID was unavailable to the task's grant. The check covers response equality in these disposable cases. Timing and real reviewer behavior were outside the design.

A deterministic decision rule and fixed reviewer procedure produced these results. The cases use four instrument types with the same verification rule. The result does not establish a model's ability to identify gaps or show that adding a queue outperforms an agent that already performs a second exact lookup.

## Replay and checks

The [protocol and fixtures](gap-request-protocol.md) were frozen at `89797c27a0ccff55ca16f34d45c80c8f5c8d8a4f`. The executable and tests were frozen at `2d275f2dfbfd6e8b88cd31deb5d84f1b67ca3df0` before either arm ran. The [per-case archive](gap-request-replay.json) includes packet citations and payloads, staged requests, reviewed handoffs, final actions, evaluator keys, work counts and full public shadow responses. An independent recount checked the matched source IDs, receipt provenance and decision transitions. Two replays matched byte for byte at SHA-256 `cfc982a6ee9c05080b152f7563f5448000d98352acdd39a7869452b680147327`.

```sh
PYTHONPATH=src python scripts/evaluate_gap_requests.py > /tmp/aams-gap-requests.json
cmp docs/audit/gap-request-replay.json /tmp/aams-gap-requests.json
sha256sum /tmp/aams-gap-requests.json
```

```sh
python -m pip install '.[mcp]' ruff==0.14.6
ruff format --check src scripts tests
ruff check src scripts tests
python -m compileall -q src scripts tests
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```

**Next action:** Independently review the paired trace and scope controls before considering a bounded exact-lookup preflight to avoid the four unnecessary requests.
