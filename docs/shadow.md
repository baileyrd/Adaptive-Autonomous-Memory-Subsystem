# Optional shadow observation

The trusted native host can bind a `ShadowObserver` to a single principal and scope, pass it to `CognitiveMemory`, and grant `shadow_observe`. Configuration defaults to disabled. Only a successful non-exact read with a visible canonical result is eligible. The worker receives two redacted Boolean features, an ephemeral opaque scope token and an opaque observation ID. The built-in evaluator uses an immutable two-bin artifact. It cannot access the store, provider, raw query, citations or serving packet.

There is one daemon worker at a time and no queue. The host configures a lifetime observation limit and a result deadline. Busy or over-budget submissions are skipped. Serving never joins the worker or depends on its decision. Late or failed work records a sanitized failure once it returns. The deadline discards late recommendations and does not forcibly interrupt a Python thread. The evaluator has no caller-supplied executable callback. Observations live in process memory and disappear when the observer is discarded. The same scope and principal with the observation grant can inspect them. No MCP, automatic activation, persistent writes or authority change is exposed.

## Paired measurements

Use `ShadowPairLedger` for explicitly supplied, scoped native measurements. It stores immutable pairs up to a host-set limit in process memory. A repeated task ID with identical observations is idempotent. Conflicting replays and overlapping independent group windows fail closed. Both runs must name the same canonical cutoff within the group's half-open window.

Each arm can explicitly lack a label. Missing or merely observational labels cannot establish a counterfactual. An alternate-mode comparison requires two controlled, identity-matched outcomes. Same-mode replay can assess invariance but does not measure an alternate treatment. Observer recommendations alone never produce paired utility labels. The ledger has no network, recall writes, or activation path.
