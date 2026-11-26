# Gemma shipment evidence diagnostic (#125, #105)

Base `0380e2ba868ecec7f8cedf44b386135146b3714a`, the merge of #140. The earlier gate observed 18 abstentions with one citation apiece. This experiment asks whether the actor can aggregate evidence and what it does once the current facts are supplied. It neither qualifies the actor nor opens the #137/#138 comparison.

## Frozen inputs and conditions

Reuse #140's Gemma 3 4B IT Q4_K_M text weights, llama.cpp b6500 CPU runtime, flags, greedy decoding, seed, 2,048-token context and 64-token output cap. The text GGUF SHA-256 is `04a43a22e8d2003deda5acc262f68ec1005fa76c735a9962a8c77042a74a7d19`. The pinned CLI and runtime archive are unchanged. Use a separate fresh process for every response. No other model is run.

Six new synthetic histories, two each for release, explicit stop and conflict abstention. Fixture digest `03f413a3cbda687c020097cd71cf0237927d22f528a83c234bf69854a563a81b`. Each case has hand-checked latest row IDs, cross-checked against the full source timestamps before inference. From those rows derive the current states, distinct nonempty receipt slots and exact latest row tuples. Derive the expected action from the current states and slots. Use these independently verified references to score the model. The cases include stale observations, reports without receipts, repeated slots, distinct original receipts and same-time conflict.

- A receives all observations and #140's unchanged action prompt and response grammar.
- B receives the same observations and IDs and extracts only latest states, distinct original slots and all latest rows as triples. B's prompt SHA-256 is `e4aeb06c8288d3a8714bc2dcf470b5414c9cc509dff74aee03229b66ee1ca1a6`. The extraction grammar SHA-256 is `cd0ba5224a475e52e06f003e68bdc01fa430db2ef58dee678aa026d03b9828e0`. It constrains syntax and allows empty, incomplete, stale or fabricated items. It does not enforce the gold values.
- C receives the independently verified latest rows, states and slots in B's exact JSON shape, including both sides of any conflict. It receives the same action rule, response grammar and rotated legend as A. The verified-facts prompt SHA-256 is `ef92bac19c129dbbfdb4b8bd9b4e23875ca5f6cbcf005ed81221947e7ca0e33f`. C does not receive B's output, any expected action, or any field encoding that action. A and B receive neither expected actions nor reference extractions.

Use all six permutations of condition order, assigned by case index. A and C share a legend, rotated once per trio so the six expected labels are balanced. Preserve rendered inputs, raw stdout, parsed outputs and per-case scores. Execute each condition once per case.

## Frozen scoring and interpretation

Score A and C on exact actions and current, unique and sufficient citations using #139's unchanged scorer. Count unsafe releases, missed explicit stops and unnecessary holds. Record the unmet citation requirement for an otherwise correct action. In B compare states, slots and row tuples as sets. Missing items are in the verified facts and absent in the output. Invented items are present in the output and absent from the verified facts, including stale rows or wrong row attributes. Report duplicate entries and malformed output separately. Exact extraction requires valid JSON of the required shape with no missing, invented or duplicate items.

On any case where B is incomplete, A lacks a supported correct action, and C supplies one, verified facts rescuing the action supports evidence aggregation as a likely bottleneck for that case. Compare exact-action improvements separately from citation improvements. If C still abstains on a required release or stop, record persistence of the action failure with verified facts. If C chooses the right action but cites insufficient evidence, record the specific citation failure separately. Report mixed patterns and limits. The verified-facts condition changes the presentation as well as removing the need to aggregate, so results do not identify a unique internal cause. Six constructed cases provide a bounded diagnostic, with no prevalence or deployment claim.
