# One paired interrupted coding task with scoped AAMS recall

Base `9dc755258116af9cfccc55a805d505054d9f5b15`. The earlier #124 checkpoint study scored a deterministic actor with no tool interface. This pilot gives a real local instruction model control of a small read/recall/edit tool loop. It tests one first edit after interruption.

## Freeze before resume

The disposable checkout adds one fixture file, `resume_fixture/labels.py`, containing an identity return. Before interruption the pilot records a maintainer decision to strip only ASCII space and tab from the edges of display labels. It writes a trial using bare `strip()`, observes that NBSP at the edges disappears, and reverts the edit. It records the failed input, actual output and required output, and a separate inspection requirement to preserve NBSP. It stages a lesson supported by those two source records, then validates and approves it through AAMS's existing scoped review API with a separate fixture reviewer. It also records the unresolved question of stripping CR/LF and the provisional decision to preserve both. These preparations use native AAMS evidence, candidate and review interfaces. The model has no write access to AAMS.

The interruption occurs after the failed edit has been reverted and the evidence and review have been persisted. Both resumed processes use clean copies of the same Git tree. The common handoff says an attempted edit was reverted and asks for the pending display-label edit. It gives neither the approved character set nor the failing probe. The expected action and test oracle stay in the evaluator. The code agent has only the bounded tool interface, so it cannot read the evaluator or ledger directly.

## Matched execution

One Qwen2.5-3B-Instruct Q4_K_M model, GGUF SHA-256 `48f4925de3417c3e259c5b460024ec9907458c52c9a7aab81269a4befd473e5e`, with llama.cpp b6500 Linux CPU CLI SHA-256 `b411ede792661c7098a7bd8965ec92b062952010fecd816fd5f77b76b450631c`. Four CPU threads, zero GPU layers, 4,096 context, up to 160 new tokens per call, greedy temperature zero and seed 42. No model substitution after freeze. Raw model output determines all tool calls and writes. Every model call runs in a new process and sees only its own arm's prior tool results, if any.

Both arms use the same prompt (SHA-256 `040de7be274becfa7215dda305cd3746566e11b40dd7a4df63a3693636e566a1`), tool-call grammar (SHA-256 `f201c18e5769b23d078ca3d1fe738496d79097a73bdf296e3bd5c52ec1401e05`) and tools. The grammar restricts JSON shape. It does not decide what action to take. The tools read the fixed file, request scoped memory, apply one replacement return line, or stop. No shell or arbitrary filesystem access is exposed. Read and recall may be repeated within the same four-call budget. Stop each arm at its first edit attempt, explicit stop, malformed output or budget exhaustion. A runs first and its recall capability returns an empty packet. B can retrieve up to eight BM25 items and 8,192 bytes, including the approved lesson only if both sources and native review were verified. No transcript is shared between arms.

## Scoring and interpretation

1. The correct next step is to edit just the fixture return expression, strip ASCII edge padding, and preserve CR/LF and interior spacing. Check the observed file and Git diff. Use a restricted AST interpreter for string stripping, rather than executing model-supplied code.
2. The known mistake is deleting NBSP. Check the concrete prior failed input. If no eligible edit can be interpreted, mark avoidance unobserved.
3. Support requires a correct step and avoidance, cited IDs actually returned to that session, and the prior decision and open question plus either the failed trial or its approved, source-linked lesson. Correct work without these citations is a separate outcome. No self-reported claim earns credit.

Archive each rendered prompt, raw model output, tool call/result, final diff, probe and score. Discuss which exposed memories were cited or reflected in the work and how the paired outcomes differed. A single pair does not isolate the effect of individual memory records or establish general coding quality. Stop after the first pair even if both sessions tie. If real inference cannot start, record the blocker before scoring. No production changes.
