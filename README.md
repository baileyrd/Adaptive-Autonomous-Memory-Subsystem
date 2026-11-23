# Adaptive Autonomous Memory Subsystem (AAMS)

AAMS is a local, model-independent memory service. It stores original evidence and append-only belief revisions in SQLite and exposes scoped recall and explanation through MCP.

## Run the demo

Use Python 3.11 or 3.12 from the repository root.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install '.[mcp]'
python -m aams.demo
```

The demo launches an MCP server process, stores a reported observation, exits, and starts a fresh process against the same database. It checks observation replay and recall, reconstructs a prior belief, and explains the current belief with supporting and refuting evidence. A third process confirms scope isolation and write denial. The demo uses a temporary database and emits a JSON result.

## Connect an MCP client

Use the following command and arguments in a host that supports MCP 2026-07-28 stdio. Replace paths with absolute paths. The example grants writes. Omit `--write` for a read-only grant.

```json
{
  "mcpServers": {
    "aams": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": [
        "-m", "aams.mcp_server",
        "--db", "/absolute/path/to/memory.sqlite3",
        "--principal", "my-agent",
        "--scope", "project",
        "--write"
      ]
    }
  }
}
```

The host controls these launch arguments and must restrict access to the database and its directory. Tool callers receive that process's scope and cannot change it through tool arguments. AAMS currently targets local stdio with the Python MCP SDK 2.3.0 client and server against protocol 2026-07-28. [MCP adapter and tool contracts](docs/mcp.md)

## Develop and test

```sh
python -m pip install '.[mcp]' ruff==0.14.6
ruff format --check src tests
ruff check src tests
python -m compileall -q src tests
PYTHONPATH=src python -m unittest discover -s tests -v
```

- [MVP acceptance contract](docs/MVP_SPEC.md)
- [Original v0.1.0 design dossier](docs/design/v0.1.0/README.md)
- [Storage and recovery design](docs/adr/0002-sqlite-evidence.md)
- [Belief history and time semantics](docs/adr/0003-belief-history.md)
- [Recall and evaluation](docs/recall.md)
- [Development instructions](AGENTS.md)
