# Gemma literal recognition of current blocked inspections (#125, #105)

**Gemma tracked the decisive observation on three of four matched pairs per wording.** It scored **7/8** on “Are all current inspections blocked?” and **7/8** on “Is at least one current inspection clear?” It reversed its literal answer across wordings on six of eight sets, and both answers were correct on all six of those sets. All 16 outputs were valid literal answers.

| Pair | Changed row | Current states after flip | All blocked before → after | Any clear before → after |
| --- | --- | --- | --- | --- |
| l01 | R2 | Clear | YES → NO | **YES → YES** |
| l02 | R1 | Clear | YES → NO | NO → YES |
| l03 | R2 | Blocked and clear | YES → NO | NO → YES |
| l04 | R4 | Blocked and clear | **YES → YES** | NO → YES |

The all-blocked question was correct on all four blocked sets and three changed sets. It missed the new clear row in l04. The any-clear question was correct on three blocked sets and all four changed sets. It incorrectly answered YES on l01's blocked singleton. Both errors produced inconsistent YES/YES answers on identical facts. In l02 and l03 both wordings responded correctly to the same one-row flip.

| Behavior | Correct, all blocked (of 8) | Correct, any clear (of 8) | Wording reversals (of 8) | Evidence flips, all blocked (of 4) | Evidence flips, any clear (of 4) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemma literal answers | 7 | 7 | 6 | 3 | 3 |
| Always YES | 4 | 4 | 0 | 0 | 0 |
| Always NO | 4 | 4 | 0 | 0 | 0 |
| All-blocked YES, any-clear NO | 4 | 4 | 8 | 0 | 0 |
| All-blocked NO, any-clear YES | 4 | 4 | 8 | 0 | 0 |

Each observed evidence flip was correct in both variants. The wording-only baselines reversed every wording pair while remaining insensitive to the evidence. The fixed-wording flips therefore provide the evidence of recognition on these packets. The two errors show that recognition was incomplete. This diagnostic changed the response contract from #143 and measured no shipment decision, so it does not establish whether a literal predicate helps Gemma stop a shipment. The #137/#138 memory comparison still requires a qualified model.

**Next action:** Freeze a matched shipment-action probe that gives the same verified observations with or without an independently verified unanimous-blocking fact. Test whether supplying that fact changes missed stops.

## Evidence and checks

The [protocol, fixtures, prompt and grammar](shipment-gemma-literal-protocol.md) were frozen at `4d3ec028735b0a5df54b36cbc44efcece2ddb0e3`. The runner and scoring tests were frozen at `6f0a13b1ac7992197570b1790820508f5658bbe0` before inference. The [archive](shipment-gemma-literal-replay.json) preserves all 16 rendered prompts and raw outputs, the two source variants per pair, the exact row changed, and the scores and baselines. SHA-256 is `7357bf69afcbf2086e8b0768a52a691acc8c65e8cac745d4432f2c3655b6ef1d`.

An independent recount regenerated current rows from source timestamps, verified the one-row changes and identical displayed facts across wordings, decoded literal answers from stdout and reproduced all reported counts and baselines. All 243 local unit tests, the MCP demo, format, lint and compile passed on Python 3.12.14. Production code is unchanged.

## Exact replay

Reuse the [pinned text model and CPU runtime acquisition commands](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/blob/0380e2ba868ecec7f8cedf44b386135146b3714a/docs/audit/shipment-gemma-results.md#exact-replay) from #140. They place the local artifacts in `/tmp/aams-gemma-artifacts`. Run from the repository root. The runner checks the hashes and runs inference offline.

```sh
PYTHONPATH=src python scripts/evaluate_gemma_literal.py \
  --cli /tmp/aams-gemma-artifacts/build/bin/llama-cli \
  --model /tmp/aams-gemma-artifacts/model.gguf > /tmp/aams-gemma-literal-replay.json
cmp docs/audit/shipment-gemma-literal-replay.json /tmp/aams-gemma-literal-replay.json
sha256sum /tmp/aams-gemma-literal-replay.json
```

```sh
python -m pip install '.[mcp]' ruff==0.14.6
ruff format --check src scripts tests
ruff check src scripts tests
python -m compileall -q src scripts tests
PYTHONPATH=src python -m unittest discover -s tests -v
python -m aams.demo
```
