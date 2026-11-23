# Governed learning candidates

Schema 3 adds scoped proposals, ordered support and refutation links, and append-only reviewer decisions. Proposal creation binds the author to the trusted AccessContext. An exact replay returns the current stored proposal and history. Decisions require a host-issued writable review grant and the expected version. The client cannot grant review to itself through a transition request.

Validation checks canonical byte digests and scope. It groups connected sources by conservative overlaps in recorded actor, locator or digest. Unverified records and reports attributed to the proposer do not count toward independent support. These rules use recorded source labels and cannot authenticate external origins or adjudicate truth. Reviewers must remain within the local trust boundary.

Approval requires a different reviewer, two eligible support groups and no recorded refutation. Evidence links and contradictory material remain available for inspection and rejection. An approval is a staged decision. It never writes a belief or changes evidence. The native API denies promotion. No learning or review tools are exposed through MCP.

## Previewing consolidation

Call `aams.consolidation.propose(store, access, since=..., through=..., limit=128)` for an opt-in preview of up to 256 small evidence records in the caller's scope and recorded-time window. The rule groups repeated UTF-8 text after Unicode normalization, case folding and whitespace folding. A record prefixed with `not:` is an explicit counterexample for the matching group. This is a textual rule with a fixed uncertainty label. Paraphrases, implicit negation and source credibility require review.

Each preview carries the proposer, ordered evidence IDs, exceptions, rule version and whether the sample hit its record cap. Calling `create_candidate` explicitly stages a selected proposal. Even a repeated text group can consist of one source; the independent-support check still runs separately.

## Recording utility feedback

Schema 4 adds a native outcome log. Use `append_outcome(access, request_key, expected_version, feedback)` to append a measured outcome for a scoped decision episode and candidate. Record the conditions, predicted and measured scores on the same zero-to-one scale, measurement time and supporting evidence IDs. The host grant binds the producer. An episode retains its original producer and candidate association across revisions.

Use `outcome_history` for scoped ordered revisions. Retries with the same key and input return the original revision. Count an episode once when aggregating measurements, using the appropriate revision for the analysis. Feedback is attributed input and does not authenticate a measurement. High scores, repeated feedback and corrective revisions leave candidate decisions, evidence and canonical beliefs unchanged.
