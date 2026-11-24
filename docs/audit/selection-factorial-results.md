# Wider inspection and copy filtering jointly changed rule-agent decisions

The preregistered interaction was +16.67 percentage points in correctness (paired ten-family bootstrap 95% interval +3.33 to +33.33). Neither factor alone changed any action. Across the 120 new paired tasks, widening alone moved 44 failure diagnoses from missing the pool to exclusion at the context boundary. Filtering the original packet could free space but could never refill from outside that packet. Native packet order was common to all arms. Per-task A/D contexts exactly matched the merged comparators.

| Arm | Correct | Unsafe proceed | Latest negative surfaced / 60 | Conflict abstentions / 12 | Abstentions against physical oracle | Candidates validated | ByT5 context tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| A original |48|52|12|0|12|960|485668|
| B wider |48|52|12|0|12|2362|485668|
| C filter |48|52|12|0|12|960|198540|
| D both |68|32|32|8|20|2362|212804|

**Cognitive utility — verified within this synthetic replay.** D gained 20 correct physical actions, reduced unsafe decisions by 20 (interval −33.33 to −3.33 points), and lost zero baseline-correct benign decisions. Its eight extra abstentions correctly recognized a conflict while missing the simulator's physical action. Model reasoning and learning were not measured. Ten constructed mechanism families limit inference.

**Retrieval — mixed.** D still missed the pool on 12 incorrect decisions, dropped relevant retrieved evidence on 16, lacked sufficient eligible evidence on 16 (four delayed, twelve missing a check), and abstained on eight visible disputes. Zero additional errors were classified as presented-but-misinterpreted or correct-without-justification. The long histories exhausted even the expanded window. Alias and derived-report families each retained eight unsafe actions. In each, declared groups outnumbered simulated underlying origins by 84 summed across final contexts. Genuine independent clear observations were retained, with 12/12 correct. The paraphrase family used one repeated natural-language rendering and the fixed parser only understands JSON. Its 12/12 correct outcomes do not demonstrate general paraphrase detection.

**Memory safety — verified on these tasks.** Every inspected/delivered row passed the canonical validator and the database digest matched after each arm. The synthetic histories include foreign-scope and future decoys. Attestation of real source independence remains unmeasured.

**Operating cost — measured for this replay.** Counts above describe validated pool rows and unframed ByT5 tokens across all decisions. Pool validation and decision time on the shared warm process had medians 1.74, 2.44, 1.74 and 2.59 ms respectively. Single-pass timings are descriptive. CPU, peak RSS and deployment SLO were not measured.

Reproduce in a Linux checkout with the project installed using `python scripts/evaluate_selection_factorial.py > replay.json`. The new case digest is pinned under scripts. Exclude elapsed time when comparing traces. Preregistration commit 1b56847107673c7897a5e9065cb4930d19cc492f preceded first execution at 6023d4384e2e73d0169aea2ae4d97fd305454513. Trace SHA-256 is 3be453724f745002d0429916889ba7c6fe1a5c233444ad95d8803f08765c22c8. The JSON summary contains every preregistered contrast. No serving change follows from this experiment.
