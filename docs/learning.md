# Governed learning candidates

Schema 3 adds scoped proposals, ordered support and refutation links, and append-only reviewer decisions. Proposal creation binds the author to the trusted AccessContext. An exact replay returns the current stored proposal and history. Decisions require a host-issued writable review grant and the expected version. The client cannot grant review to itself through a transition request.

Validation checks canonical byte digests and scope. It groups connected sources by conservative overlaps in recorded actor, locator or digest. Unverified records and reports attributed to the proposer do not count toward independent support. These rules use recorded source labels and cannot authenticate external origins or adjudicate truth. Reviewers must remain within the local trust boundary.

Approval requires a different reviewer, two eligible support groups and no recorded refutation. Evidence links and contradictory material remain available for inspection and rejection. An approval is a staged decision. It never writes a belief or changes evidence. The native API denies promotion. No learning or review tools are exposed through MCP.
