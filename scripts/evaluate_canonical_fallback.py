"""Execute the preregistered disposable canonical fallback comparison (issue #124)."""

import argparse
import json
import sqlite3
import statistics
import subprocess
import sys
import tempfile

from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
from aams.contracts import Evidence  # noqa: E402
from aams.storage import AccessContext, SQLiteMemoryStore  # noqa: E402
from canonical_fallback_cases import ARMS, check_separation, episodes  # noqa: E402
from checkpoint_recovery_amended import restore_path  # noqa: E402
from checkpoint_recovery_cases import digest  # noqa: E402
from checkpoint_recovery_contract import authorized, canonical_state, decide, result  # noqa: E402
from evaluate_checkpoint_recovery import paired, prepare  # noqa: E402


def frozen_inputs() -> list[dict]:
    """Verify the preregistration against disk before constructing any store."""
    pins = json.loads((ROOT / "scripts/canonical_fallback_freeze.json").read_bytes())
    for name, expected in pins["files"].items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Source freeze mismatch: {name}")
    batch = episodes()
    if digest(batch) != pins["cases_sha256"]:
        raise ValueError("Case freeze mismatch")
    check_separation(batch)
    return batch


def manifest(directory: Path) -> dict[str, str]:
    """Hash every prepared database and sidecar file including its name."""
    return {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir())}


class Reader(SQLiteMemoryStore):
    """Reuse scoped canonical decoding with a read-only URI and no migration constructor."""

    def __init__(self, path: Path) -> None:
        self.uri = path.resolve().as_uri() + "?mode=ro"
        self.reads: list[tuple[str, str]] = []

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.uri, uri=True)
        db.row_factory = sqlite3.Row
        return db

    def get_evidence(self, access: AccessContext, evidence_id: str) -> Evidence | None:
        self.reads.append((access.scope, evidence_id))
        return super().get_evidence(access, evidence_id)


def canonical_read(store: Reader, access: AccessContext, task: str, host: dict) -> dict:
    """Resolve only the trusted task and fresh grant; failure has one public shape."""
    if host["task_id"] != task or not authorized(host, access):
        return result("unavailable")
    state = canonical_state(store, access, host)
    return state if state["status"] == "ready" else result("unavailable")


def attempt(arm: str, path: Path, store: Reader, initial: dict, fresh: dict) -> tuple:
    """Run one request without supplying labels, world state or family to the reader."""
    access = AccessContext(initial["principal"], initial["scope"])
    checkpoint_status = None
    if arm != "canonical":
        state = restore_path(path, store, access, initial)
        checkpoint_status = state["status"]
        if arm == "checkpoint" or checkpoint_status == "ready" or not authorized(initial, access):
            return state, checkpoint_status, False, 0
    start = len(store.reads)
    bounded = {**fresh, **{key: min(initial[key], fresh[key]) for key in ("as_of", "effective_at")}}
    state = canonical_read(store, access, initial["task_id"], bounded)
    return state, checkpoint_status, True, len(store.reads) - start


def audit(e: dict, state: dict, source: str, store: Reader, fresh_reads: int) -> None:
    """Independently validate public visibility, immutable citation bytes and bounds."""
    host = e["fresh"]
    refs = state["citations"]
    ready = state["status"] == "ready"
    denied = not host["allowed"] or host["principal"] not in host["readers"]
    if denied and (ready or fresh_reads):
        raise ValueError("Disclosure or canonical lookup under a denied grant")
    if not e["authority"]["allowed"] and store.reads:
        raise ValueError("Lookup before initial authorization")
    if any(scope != host["scope"] for scope, _ in store.reads):
        raise ValueError("Foreign-scope lookup")
    if ready != (state["state"] is not None) or bool(refs) != ready:
        raise ValueError("Partial response")
    if len(json.dumps(state, sort_keys=True).encode()) > 8192:
        raise ValueError("Budget exceeded")
    if not ready:
        if host["principal"] != host["owner"] and state != result("unavailable"):
            raise ValueError("Lifecycle detail exposed")
        return
    if source == "checkpoint" and e["checkpoint"]["expires_at"] <= host["now"]:
        raise ValueError("Expired checkpoint returned")
    if e["family"] in ("contradictory_state", "head_after_cutoff"):
        raise ValueError("Unsafe canonical resolution")
    if {r["evidence_id"] for r in refs} != set(host["head_ids"]) or len(refs) != len(
        host["head_ids"]
    ):
        raise ValueError("Returned citations differ from required heads")
    records = {(r["scope"], r["id"]): r for r in e["records"]}
    for ref in refs:
        row = records[(host["scope"], ref["evidence_id"])]
        expected = {
            key: row[key]
            for key in (
                "scope",
                "digest",
                "source_actor",
                "source_locator",
                "producer",
                "observed_at",
                "recorded_at",
            )
        }
        expected["evidence_id"] = row["id"]
        if (
            ref != expected
            or row["digest"] != "sha256:" + sha256(row["text"].encode()).hexdigest()
            or row["source_actor"] != host["executor"]
            or row["producer"] != host["executor"]
            or row["source_locator"] != host["source_locator"]
            or row["recorded_at"] > host["as_of"]
            or row["observed_at"] > host["effective_at"]
        ):
            raise ValueError("Invalid returned citation")


def measure(arm: str, directory: Path, e: dict, store: Reader) -> tuple[dict, int]:
    """Score a public result against the precommitted world label."""
    store.reads.clear()
    start = perf_counter_ns()
    state, status, canonical, reads = attempt(
        arm, directory / (e["id"] + ".json"), store, e["authority"], e["fresh"]
    )
    action = decide(state, e["fresh"])
    ns = perf_counter_ns() - start
    source = "canonical" if canonical else "checkpoint"
    audit(e, state, source, store, reads)
    actual, world = state["state"], e["world"]
    success = action == e["expected"]
    return {
        "arm": arm,
        "split": e["split"],
        "family": e["family"],
        "task_id": e["authority"]["task_id"],
        "checkpoint_status": status,
        "canonical_attempt": canonical,
        "canonical_reads": reads,
        "result": state,
        "action": action,
        "expected": e["expected"],
        "success": success,
        "resumed_correctly": success and actual is not None,
        "correct_denial": success and not e["fresh"]["allowed"],
        "invented_progress": len(set(actual["completed"]) - set(world["completed"]))
        if actual
        else 0,
        "lost_constraints": sum(
            v and not actual["constraints"].get(k, False) for k, v in world["constraints"].items()
        )
        if actual
        else 0,
        "unavailable_active_constraints": actual is None and any(world["constraints"].values()),
        "repeat": action.startswith("do:") and action[3:] in world["completed"],
        "valid_citations": len(state["citations"]),
    }, ns


def child(directory: Path, mode: str) -> dict:
    """Start a fresh interpreter with a fixed input directory."""
    proc = subprocess.run(
        [sys.executable, "-I", __file__, "--directory", str(directory), "--mode", mode],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        timeout=120,
    )
    return json.loads(proc.stdout)


def run() -> dict:
    """Prepare once, reopen in three independent readers, compare all bytes and pair scores."""
    arms = {}
    with tempfile.TemporaryDirectory(prefix="aams124-fallback-") as name:
        directory = Path(name)
        before = child(directory, "prepare")
        for arm in ARMS:
            arms[arm] = child(directory, arm)
            if before != manifest(directory):
                raise ValueError(f"Store mutation across reopen: {arm}")
    splits = {}
    for split in ("design", "heldout"):
        groups = {a: [r for r in arms[a]["rows"] if r["split"] == split] for a in ARMS}
        totals = {}
        for a, rows in groups.items():
            totals[a] = {
                k: sum(row[k] for row in rows)
                for k in (
                    "success",
                    "resumed_correctly",
                    "correct_denial",
                    "invented_progress",
                    "lost_constraints",
                    "unavailable_active_constraints",
                    "repeat",
                    "valid_citations",
                )
            }
            totals[a]["by_family_correct"] = {
                f: sum(r["success"] for r in rows if r["family"] == f)
                for f in sorted({r["family"] for r in rows})
            }
        pairs = list(zip(groups["checkpoint"], groups["fallback"], strict=True))
        interval = paired(
            groups["checkpoint"],
            groups["fallback"],
            {"bootstrap_seed": 0, "bootstrap_samples": 2000},
        )
        interval.pop(
            "limitation"
        )  # The shared bootstrap helper hardcodes #130's family count in its prose.
        splits[split] = {
            "totals": totals,
            "delta": interval,
            "gains": sum(b["success"] and not a["success"] for a, b in pairs),
            "regressions": sum(a["success"] and not b["success"] for a, b in pairs),
        }
    return {
        "splits": splits,
        "arms": arms,
        "manifest_sha256": digest(before),
        "file_count": len(before),
        "cases_sha256": digest(frozen_inputs()),
    }


def main() -> None:
    """Emit a JSON evidence bundle or execute a private preparation/reading phase."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--mode", choices=("prepare", *ARMS))
    args = parser.parse_args()
    if args.mode is None:
        print(json.dumps(run(), sort_keys=True))
        return
    batch = frozen_inputs()
    if args.mode == "prepare":
        prepare(args.directory, batch)
        for e in batch:
            if e["family"] == "missing_candidate":
                (args.directory / (e["id"] + ".json")).unlink()
        print(json.dumps(manifest(args.directory)))
        return
    store = Reader(args.directory / "memory.db")
    samples = [measure(args.mode, args.directory, e, store) for e in batch]
    print(
        json.dumps(
            {
                "rows": [r for r, _ in samples],
                "median_decision_ns": statistics.median(ns for _, ns in samples),
            }
        )
    )


if __name__ == "__main__":
    main()
