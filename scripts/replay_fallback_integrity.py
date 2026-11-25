"""Append-only integrity replay for #131 using the frozen preparer and all three readers."""

import json
import platform
import sqlite3
import tempfile
from contextlib import closing
from hashlib import sha256
from pathlib import Path

from evaluate_canonical_fallback import ARMS, ROOT, child, digest, manifest


def logical_digest(path: Path) -> str:
    """Hash schema, schema version, ordered columns and row multisets, excluding physical layout."""
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        schema = db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE sql IS NOT NULL ORDER BY type,name,tbl_name"
        ).fetchall()
        tables = {}
        for kind, name, _, _ in schema:
            if kind != "table":
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            cursor = db.execute("SELECT * FROM " + quoted)
            rows = [
                json.dumps(
                    [{"blob": v.hex()} if isinstance(v, bytes) else v for v in row],
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                for row in cursor
            ]
            tables[name] = {"columns": [d[0] for d in cursor.description], "rows": sorted(rows)}
        version = db.execute("PRAGMA user_version").fetchone()[0]
    return digest(
        {
            "algorithm": "aams-logical-v1",
            "user_version": version,
            "schema": schema,
            "tables": tables,
        }
    )


def replay() -> dict:
    """Emit observed per-stage file evidence after verifying every original decision trace."""
    audit = ROOT / "docs/audit"
    original = json.loads((audit / "canonical-fallback-results.json").read_bytes())
    raw = (audit / "canonical-fallback-decisions.jsonl").read_bytes()
    if sha256(raw).hexdigest() != original["trace_sha256"]:
        raise ValueError("Archived trace fingerprint mismatch")
    expected = [json.loads(line) for line in raw.splitlines()]
    stages = {}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        files = child(path, "prepare")
        if files != manifest(path) or len(files) != original["file_count"]:
            raise ValueError("Preparer and first inspector disagree")
        logical = logical_digest(path / "memory.db")
        for arm in ("prepare", *ARMS):
            if arm != "prepare":
                rows = child(path, arm)["rows"]
                if rows != [r for r in expected if r["arm"] == arm]:
                    raise ValueError(f"Decision trace mismatch in {arm}")
            observed = manifest(path)
            current = logical_digest(path / "memory.db")
            if observed != files or current != logical:
                raise ValueError(f"Integrity mismatch after {arm}")
            stages[arm] = {
                "files": observed,
                "manifest_sha256": digest(observed),
                "logical_sha256": current,
            }
    return {
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(),
        "stages": stages,
        "verified_rows": len(expected),
        "trace_sha256": original["trace_sha256"],
        "matches_first_run_physical_manifest": digest(files) == original["manifest_sha256"],
    }


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2, sort_keys=True))
