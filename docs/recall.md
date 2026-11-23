# Scoped recall and explanation

Use `CognitiveMemory(store)` with the host's trusted `AccessContext`. For lexical recall, pass `CognitiveNeed(query="rain storm", max_items=5)`. For exact lookup or explanation, pass `CognitiveNeed(entity="belief", identifier="weather")`. Exact lookup also supports formations and original evidence. Unknown and inaccessible targets return an empty packet.

Since v0.8, ranking uses Okapi BM25 (`k1=1.2`, `b=0.75`) over the ID, kind, proposition, source locator and the **full** payload of each cited, time-visible evidence record. Tokens are case-folded Unicode alphanumeric runs. Corpus statistics come only from the request's authorized, time-filtered candidates, so out-of-scope and later records cannot influence a score. `relevance.score` holds the BM25 value, `relevance.ranker` is `"bm25"`, and `matched_terms` lists the distinct matched query tokens. Ties sort by entity type and ID. Term counts of immutable evidence are cached per `CognitiveMemory` instance in a bounded LRU. Callers cannot choose the ranker per request. See [ADR-0009](adr/0009-scoped-lexical-ranking.md).

### Migrating from v0.7 and earlier

- **Scores changed scale and meaning.** Legacy `relevance.score` was an integer count of distinct matched tokens. It is now an unbounded, non-negative BM25 value that depends on the request's visible candidate set. Do not compare scores across rankers, releases, scopes, cutoffs or requests, and do not use fixed score thresholds. In hybrid mode the score remains a [0, 1] blend, but its lexical half is now BM25 divided by the request maximum.
- **Ordering and membership can change.** Rare terms weigh more, long records are length-normalized, and matches beyond the 512-byte preview now count, so records that previously did not match can appear. Packets still carry only the 512-byte preview.
- **Rollback.** A host restores the legacy ranker with `CognitiveMemory(store, lexical_ranking=LexicalRanking.OVERLAP)`. Legacy packets are byte-identical to v0.7 and have no `relevance.ranker` key.
- Exact identity lookup, scope and time filtering, citations, contradiction fields and routing are unchanged.

Empty or punctuation-only queries return an empty packet. Lexical recall scans eligible formations and belief identities in one SQLite read snapshot scoped to the caller. Exact lookup continues to use indexed identity reads. No derived index is required. It does not rank standalone evidence, which is addressable directly and through citations.

Belief time filters use the recorded and effective semantics in [ADR-0003](adr/0003-belief-history.md). Formation times filter creation. Evidence times filter recording and observation, respectively. Kind filters restrict retrieval to matching formations. Results can show original evidence previews, locators, digests and the roles of supporting and refuting links. Citations establish provenance without inferring independent corroboration.

Depth zero omits citations and depth one returns direct evidence links. The schema has no recursive edges. Payload previews are limited to 512 bytes and decoded as UTF-8 with replacement. Item and serialized byte budgets return a prefix with an explicit truncation flag. Invalid arguments raise `ValueError`. Failed canonical reads raise `StoreIntegrityError`.

Run `PYTHONPATH=src python -m unittest discover -s tests -p test_recall.py -v` for the offline fixture. The fixture measures precision@2 of 1.0 for its fixed query and tests stable ties, a duplicate source, a lexical false positive, historical scope isolation and contradiction visibility. This scan-based baseline targets small local stores.
