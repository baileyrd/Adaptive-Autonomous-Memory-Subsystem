# Scoped recall and explanation

Use `CognitiveMemory(store)` with the host's trusted `AccessContext`. For lexical recall, pass `CognitiveNeed(query="rain storm", max_items=5)`. For exact lookup or explanation, pass `CognitiveNeed(entity="belief", identifier="weather")`. Exact lookup also supports formations and original evidence. Unknown and inaccessible targets return an empty packet.

Ranking counts distinct query tokens found in the ID, kind, proposition, source locator or evidence preview. Tokens are case-folded Unicode alphanumeric runs. A match contributes once regardless of how often sources repeat it. Ties sort by entity type and ID. Empty or punctuation-only queries return an empty packet. Lexical recall scans eligible formations and belief identities in the caller's scope. It does not rank standalone evidence, which is addressable directly and through citations.

Belief time filters use the recorded and effective semantics in [ADR-0003](adr/0003-belief-history.md). Formation times filter creation. Evidence times filter recording and observation, respectively. Kind filters restrict retrieval to matching formations. Results can show original evidence previews, locators, digests and the roles of supporting and refuting links. Citations establish provenance without inferring independent corroboration.

Depth zero omits citations and depth one returns direct evidence links. The schema has no recursive edges. Payload previews are limited to 512 bytes and decoded as UTF-8 with replacement. Item and serialized byte budgets return a prefix with an explicit truncation flag. Invalid arguments raise `ValueError`. Failed canonical reads raise `StoreIntegrityError`.

Run `PYTHONPATH=src python -m unittest discover -s tests -p test_recall.py -v` for the offline fixture. The fixture measures precision@2 of 1.0 for its fixed query and tests stable ties, a duplicate source, a lexical false positive, historical scope isolation and contradiction visibility. This scan-based baseline targets small local stores.
