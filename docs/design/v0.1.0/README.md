# Adaptive Autonomous Memory Subsystem (AAMS)

**Project documentation version:** 0.1.0 (concept/design baseline)  
**Date:** 2026-11-22  
**Status:** Proposed; no implementation or empirical claims  
**Scope:** Greenfield memory infrastructure exclusively for AI consumers

## Executive summary

AAMS is an independent, model-neutral, evidence-preserving cognitive memory system designed to help AI agents learn from experience without conflating generated beliefs with historical observations. Its core consists of a durable evidence ledger, typed Memory Formations, versioned belief states, contextual recall, and governed lifecycle operations. Neural components may improve association, ranking, generalization and utility estimation; they never become the sole authoritative representation of evidence. MCP is a first-class interoperability adapter, complemented by a native event/API interface for high-throughput host integration.

**Design thesis:** The purpose of memory is not to make an AI retain more information, but to measurably improve its reasoning, reliability, continuity and future decisions.

## Documentation index

| Document | Contents |
|---|---|
| [01 – Product requirements](docs/01-product-requirements.md) | Vision, stakeholders, boundaries, functional/nonfunctional requirements |
| [02 – Architecture](docs/02-architecture.md) | Components, deployment, data flows, consistency, storage strategy |
| [03 – Memory model](docs/03-memory-model.md) | Formations, evidence, belief revision, time, consolidation, deletion |
| [04 – Protocol and APIs](docs/04-protocol-and-api.md) | MCP contracts, host adapter, example schemas and error semantics |
| [05 – Security and governance](docs/05-security-governance.md) | Threat model, permissions, integrity, privacy, lifecycle |
| [06 – Roadmap](docs/06-roadmap.md) | Milestones, dependencies, deliverables, exit gates, backlog slices |
| [07 – Implementation plan](docs/07-implementation-plan.md) | Repository design, build strategy, test plan, release criteria |
| [08 – Research and evaluation](docs/08-research-evaluation.md) | Experiments, hypotheses, benchmarks, success thresholds |
| [09 – Decisions and open questions](docs/09-decisions-open-questions.md) | ADRs, deferred choices, risks and questions |

## Project invariants

1. Original evidence and derived interpretations remain distinguishable and independently addressable.
2. A memory never becomes authoritative solely because it was repeated or recalled.
3. Every change to a belief retains its source, reason and historical revision linkage.
4. Model-specific embeddings/latent codes are disposable indexes, never the sole source of truth.
5. Permission checks occur before recall, association, consolidation, export and deletion.
6. Deletion semantics cover derived data, caches, indexes and replicas within declared boundaries.
7. Agents cannot silently promote unverified hypotheses into authoritative facts.
8. MCP and native interfaces share the same domain semantics and authorization system.
9. Model/runtime internals are not assumed accessible via MCP.
10. Claim of benefit requires controlled evaluation against explicit baselines.

## First executable vertical slice

An authorized agent records an immutable observation; AAMS creates a traceable Memory Formation; another agent asks through MCP for relevant prior observations; AAMS returns bounded ranked memory with provenance and uncertainty; a correction produces a new belief revision without mutating the observation; the full sequence passes crash-recovery and permission tests.

## Documentation status and usage

This is a design baseline, not an existing software implementation. All proposed interfaces, examples and milestone numbers are project-defined and may change under versioned architecture decisions. Start by reviewing [ADR-001 through ADR-009](docs/09-decisions-open-questions.md), then execute M00 and M01 in the [roadmap](docs/06-roadmap.md).

## External standards reference

MCP is documented against protocol release **2026-07-28**. Its stateless request model differs materially from earlier versions: do not assume protocol sessions, GET stream endpoints, or legacy initialization handshakes. See [protocol/API document](docs/04-protocol-and-api.md) for references and compatibility policy.
