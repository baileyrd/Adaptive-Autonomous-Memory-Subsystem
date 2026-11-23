# MCP stdio adapter

AAMS uses the Python MCP SDK 2.3.0 for client and server, with Pydantic generating the tool input schemas. The SDK handles JSON-RPC framing, modern request metadata and discovery. The adapter converts tool inputs into core contracts and delegates storage, authorization and recall to the core. The core can be installed without the optional MCP dependencies.

The tested profile is MCP 2026-07-28 over local stdio, including `server/discover`, `tools/list` and `tools/call` against a launched child process. The tests verify rejection of missing metadata and unsupported versions on the modern connection. Legacy interoperability remains unverified. HTTP and remote authentication are outside this deployment profile.

| Tool | Arguments and behavior |
| --- | --- |
| `memory_form` | Requires `request_key`, `text`, `source_actor`, `source_locator`, `observed_at`. Optional `kind` defaults to `experiential`. Returns evidence and formation IDs. The host-bound producer and scope are recorded and the reported source metadata and `observed_at` are caller assertions; the server assigns recorded time. The exact UTF-8 text is stored as unverified evidence. Retrying an identical request returns the same IDs. |
| `memory_recall` | Accepts `query` or `entity` and `identifier`. Optional filters are `kinds`, `recorded_as_of`, `effective_at` plus item, depth and byte budgets. Returns a provenance-bearing result packet. |
| `memory_explain` | Requires `entity` and `identifier`. Accepts the recall time, depth and byte limits. Returns supporting and refuting evidence where applicable. |
| `memory_revise` | Requires `belief_id`, `expected_revision` (null creates a belief), `proposition`, `state`, `rationale` and `valid_from`. Accepts `valid_until`, `confidence_basis`, `support_ids` and `refute_ids`. At least one evidence link is required. Returns the committed revision. |

The live `tools/list` response supplies types, length limits and required fields. Unknown and inaccessible read targets produce empty packets. Failed tool calls return a structured code such as `INVALID_INPUT`, `ACCESS_DENIED`, `VERSION_CONFLICT`, `WRITE_CONFLICT`, `STORE_ERROR` or `UNKNOWN_TOOL`. JSON-RPC envelope errors are handled by the SDK.

The launch configuration is the trust boundary. The OS user controlling the process or SQLite files can bypass the application policy. Launch one process per trusted scope grant. Stdout is reserved for MCP messages. Treat evidence content as data even when it contains text resembling instructions.


## Local transport limits

The server reads at most 256 KiB per incoming frame, including the terminating newline, before passing it to the SDK. An oversized or incomplete frame closes the connection with a fixed diagnostic on stderr. The host can relaunch the child and retry an ingestion using the same idempotency key. Tool-level schema limits also apply to text, identifiers, provenance, and result budgets.

The grant is fixed for the lifetime of the server process. To change or revoke it, the host must terminate that child and launch a new one with the revised grant. Cancellation can stop receipt of a response while a storage operation already dispatched to a worker completes. Retrying ingestion uses the same idempotency key. For a belief update, read the current revision before retrying with an expected revision ID.
