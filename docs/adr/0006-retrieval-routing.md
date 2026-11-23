# ADR-0006 — Conservative, explicit retrieval mode selection

Status: Proposed
Date: 2026-11-23
Tracking: #45 / #46

## Context

The v0.4 evaluation found lower recall@3 and nDCG@3 for the tested local neural encoder compared with lexical retrieval, alongside higher latency and memory usage. We must not infer that neural selection is generally better from provider availability.

## Decision

Define a pure, immutable request/decision contract. Lexical remains the default. A caller must explicitly request hybrid. An exact identifier lookup always selects canonical lexical mode. Hybrid eligibility additionally requires a provider-ready signal and a fresh representation index; missing either causes a lexical decision with a stable, non-sensitive reason. Provider-ready/fresh signals are *trusted integration inputs*, never values accepted as authorization or proof of neural quality.

The selector does not retrieve data, authorize principals, inspect a database, call providers, or promote candidate knowledge. No existing MCP or native recall behavior is changed in this slice. #47 must derive freshness from the scoped canonical index, maintain canonical reauthorization and implement safe fallback if readiness changes between decision and use.

## Invariants

- Selection cannot increase the trust status of retrieved information or change evidence, beliefs, candidates, permissions, or historical knowledge.
- Decisions carry an explicit policy version and reason for testability.
- Provider outages, stale indexes, malformed inputs and exact-ID requests never select hybrid.
- No online learning, query logging, telemetry or source-sensitive routing information is added here.
- Real effectiveness requires held-out evaluation in #49, not the offline fixture encoder.

## Follow-up gates

#47: integrate this policy into native recall with scope/time checks and runtime fallback.
#48: outcome telemetry kept separate from authority.
#49: matched held-out comparisons and honest negative results.
#50: v0.5 acceptance and deployment limitations.
