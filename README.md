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
ruff format --check src tests scripts
ruff check src tests scripts
python -m compileall -q src tests scripts
PYTHONPATH=src python -m unittest discover -s tests -v
```

- [MVP acceptance contract](docs/MVP_SPEC.md)
- [Original v0.1.0 design dossier](docs/design/v0.1.0/README.md)
- [Storage and recovery design](docs/adr/0002-sqlite-evidence.md)
- [Belief history and time semantics](docs/adr/0003-belief-history.md)
- [Recall and evaluation](docs/recall.md)
- [Development instructions](AGENTS.md)

## Local database operation

On Linux, create a private data directory with `umask 077; mkdir -p "$HOME/.local/share/aams"`. Point the launch configuration at an absolute database path in that directory. SQLite initializes the schema on first use. Point the service at a new path to start with empty memory. The demo seeds and removes its own temporary database.

Use the SQLite backup API for a consistent snapshot while another process may be writing. Choose a fresh destination in a private directory.

```sh
python - /absolute/path/to/memory.sqlite3 /absolute/path/to/backup.sqlite3 <<'PY'
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

source, destination = map(Path, sys.argv[1:])
if destination.exists():
    raise SystemExit("Backup destination must be new")
with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as live:
    with closing(sqlite3.connect(destination)) as snapshot:
        live.backup(snapshot)
PY
python - /absolute/path/to/backup.sqlite3 <<'PY'
import sys
from aams.storage import SQLiteMemoryStore

SQLiteMemoryStore(sys.argv[1]).verify_integrity()
print("backup verified")
PY
```

To restore, stop the service and launch it against the verified backup path or a private copy. Keep the damaged database for diagnosis. The acceptance tests exercise backup and restore and process-kill recovery. This procedure covers a single local SQLite database and requires the host to protect both originals and backups.

## Tested profile and limitations

CI covers Ubuntu with Python 3.11 and 3.12. The MCP interoperability profile is local stdio, protocol 2026-07-28 and Python MCP SDK 2.3.0. The host must limit access to the process launch configuration and data directory, and treat returned evidence as untrusted content.

AAMS uses lexical recall and does not perform automatic source verification, autonomous learning, model-internal inspection, or distributed replication. No guarantee is made about model behavior when a host supplies instruction-like evidence as context. See the [v0.2 engineering baseline](docs/acceptance/MVP-v0.2.md) for current measurements and verification limits and the [v0.1 MVP matrix](docs/acceptance/MVP-v0.1.md) for the original release evidence.

The [v0.3 governed learning acceptance](docs/acceptance/MVP-v0.3.md) documents the native workflow, fixture results, and known limits.

The [v0.4 acceptance matrix](docs/acceptance/MVP-v0.4.md) records optional hybrid recall, its measured encoder tradeoffs, and recovery procedures.

The [v0.5 acceptance matrix](docs/acceptance/MVP-v0.5.md) documents guarded routing, bounded outcome telemetry, and the held-out comparison.
