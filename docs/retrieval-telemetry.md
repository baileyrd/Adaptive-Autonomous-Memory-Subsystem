# Retrieval outcome telemetry

A trusted native host can opt in using an `AccessContext` with the telemetry grant. It can append or delete with a writable grant. Each observation contains a host-generated opaque attempt ID, current policy version, actual mode, a measured outcome label, and integer milliseconds. The host must assign the label from an explicit task check. The store accepts no free-form query, documents, evidence IDs, or model feedback. No MCP tools expose this interface. Recall does not write telemetry implicitly.

Replay the same attempt with identical measurements to get the stored result. A different measurement for that ID conflicts, and a host cannot submit an obsolete policy version. Attempt IDs deduplicate retries within retention, rather than authenticate observations. Measurements cannot change routing weights, evidence, beliefs, or candidate states.

Only the same scoped principal can read or delete its observations. The limit is 256 retained records per principal and scope, with a 30-day window. Reads exclude expired rows. Successful writes prune expired rows for that principal, and explicit deletion removes its records from the live database. This cannot erase copies in backups, filesystem snapshots or external logs. The trusted host must apply its own backup retention and avoid encoding user content in attempt IDs.
