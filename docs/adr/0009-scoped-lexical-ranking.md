# ADR-0009: Scoped BM25 lexical ranking as host configuration

Status: Proposed
Date: 2026-11-23
Tracking: v0.8 goal #79 / #81

## Context

The v0.8 root-cause investigation (#80, [audit](../audit/retrieval-root-cause.md)) found that ranking, not routing, limits retrieval quality. The overlap ranker scores a record by its count of unique matched query terms, with no term weighting or length normalization. It also matches only the 512-byte citation preview, while the representation index encodes the full payload. A per-task oracle choosing between lexical and hybrid retrieval would add about 2 pp of tasks over guarded routing. That is below the registered 5 pp gate, so no router over the existing arms can qualify.

## Decision

Add `aams.ranking`: a pure `LexicalRanking` enum and an Okapi BM25 function (`k1=1.2`, `b=0.75`, non-negative IDF). `CognitiveMemory` accepts `lexical_ranking` as **host configuration**. It is not a `CognitiveNeed` field or an MCP argument, so callers can't select it per request. `OVERLAP` remains the default, and its response packets are byte-identical to v0.7.

With `BM25`:

- Corpus statistics (document frequency, average length) come only from the candidates that `scan_recall` returned for this request. Those candidates are already restricted to the caller's scope, the time cutoffs and the kind filter. A score therefore depends only on records the caller may read. Private or later records can't change it, so it can't serve as an existence oracle. This is tested.
- Matching uses the full canonical payload of each cited, time-visible evidence record, not the 512-byte preview. Packets still carry only the preview.
- `relevance.score` is the BM25 score. `relevance.ranker` is `"bm25"`, and `matched_terms` is unchanged. In hybrid mode the lexical component is BM25 divided by the request's maximum BM25, which keeps it in [0, 1] like the overlap fraction it replaces.
- It is deterministic: the same canonical inputs give identical packets. Ties keep the existing `(entity, id)` order.

## Consequences

- No new dependency, schema, persisted state or network use. Representation providers stay optional.
- Cost is linear in the visible candidates, as before. Full-payload tokenization is memoized in a per-instance LRU of 4,096 entries, keyed by `(scope, evidence_id, digest)`. This is safe because evidence is immutable, and the cache is filled only from records an authorized scan returned. Without the cache, p95 rose by 30 ms at about 324 records per scope; with it, by about 1 ms. A persisted inverted index is deferred until a measured scale need exists.
- Changing the default is a separate decision. It needs the #79 gate on independent workloads, a migration note for consumers that read `relevance.score`, and explicit authorization. This ADR does not change the default.
- No learned or live routing policy is activated, and no memory authority changes.
