# Adaptive Autonomous Memory Subsystem (AAMS)

AAMS is a greenfield, AI-native, model-independent memory service. It preserves **historical evidence** separately from **revisable beliefs**, with scoped recall, provenance, and an interoperable MCP adapter.

## Status

**MVP bootstrap in progress. Not a working memory server.** See [goal #1](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/1) and [bootstrap #2](https://github.com/baileyrd/Adaptive-Autonomous-Memory-Subsystem/issues/2).

## Documentation

- [MVP acceptance contract](docs/MVP_SPEC.md)
- [Initial architecture decision](docs/adr/0001-bootstrap.md)
- [Development instructions](AGENTS.md)
- The original AAMS v0.1.0 design dossier is pending import. The MVP acceptance contract records the issue-backed baseline and open decisions.

## Bootstrap development

This repository starts with a dependency-light Python 3.11+ **contract/testing scaffold**. Python is a provisional MVP implementation choice, not an irreversible architecture decision.

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src
```

CI runs tests, compile checks, and pinned Ruff lint/format checks. No database, neural index, or MCP server exists yet. Those are work packages #3–#6.

## Non-negotiable boundaries

1. Evidence and generated interpretations must remain distinguishable.
2. Memory is model-neutral; embeddings must remain disposable indexes.
3. Revisions preserve history and provenance.
4. Access policy applies to every interface, including MCP.
5. No automatic promotion of model-generated claims to verified observations.
6. No MVP success claim without demonstrated persistence, revision, recall, MCP, security, and recovery.
