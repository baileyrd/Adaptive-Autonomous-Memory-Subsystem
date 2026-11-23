# Disposable representation index

Schema 5 stores one derived batch per scope and exact provider, model, version and dimensions. Sources are immutable scoped evidence. Only complete UTF-8 payloads from 1 to 4096 bytes are eligible. Every vector carries the canonical digest and a checksum for its encoded bytes.

A writable scope grant is required to rebuild or invalidate a batch. Rebuild samples one read snapshot, encodes outside the transaction and atomically replaces the batch if the scoped evidence count still matches. Repeating a fresh rebuild reuses the batch. Reads return missing, stale, corrupt or fresh status and only fresh batches expose vectors. A write or encoder failure preserves the preceding batch. Invalidation deletes derived rows and leaves canonical data intact.

The watermark is the scoped count of immutable evidence in the append-only application model. Backups made outside that model should discard derived rows and rebuild. The index cannot authenticate a SQLite file or certify a provider. Vectors remain retrieval aids and have no epistemic authority.

## Opt-in hybrid recall

Pass an explicit `provider` to `CognitiveMemory.recall(access, need, provider=provider)` after building a batch. Without a provider, lexical behavior is unchanged. Exact lookup bypasses vectors. Missing, stale, corrupt, incompatible or unavailable vectors and zero eligible semantic matches fall back to the deterministic lexical ranking. The response identifies its mode and status without exposing provider errors.

Hybrid scoring averages the fraction of lexical query terms matched and the highest authorized cosine similarity of at least 0.35. Ties use entity and stable ID. Scope, time, kind and canonical citation checks precede output. Derived evidence IDs and digests must match canonical citations. The packet records lexical and semantic components and, when depth permits, the semantic source. The existing response budgets still apply.
