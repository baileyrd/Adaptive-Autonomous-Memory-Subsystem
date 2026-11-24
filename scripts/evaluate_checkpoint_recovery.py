"""Disposable #124 checkpoint experiment; no product checkpoint persistence or model inference."""

import argparse
import json
import os
import platform
import random
import resource
import sqlite3
import statistics
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checkpoint_recovery_cases import RECIPE, cases, digest, oracle  # noqa: E402
from checkpoint_recovery_contract import (  # noqa: E402
    authorized,
    canonical_state,
    decide,
    reference,
    restore_path,
    result,
    visible,
)
from evaluate_cognitive_tasks import database_digest  # noqa: E402
from aams.contracts import (  # noqa: E402
    EpistemicState,
    Evidence,
    EvidenceStatus,
    MemoryFormation,
    MemoryKind,
)
from aams.storage import AccessContext, SQLiteMemoryStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = Path(__file__).with_name("checkpoint_recovery_preregistration.json")
EXECUTION = Path(__file__).with_name("checkpoint_recovery_execution.json")
ARMS = ("transcript", "checkpoint", "canonical_control")


def checked_inputs():
    registration = json.loads(REGISTRATION.read_text())
    for name, expected in json.loads(EXECUTION.read_text())["source_sha256"].items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Execution source checksum mismatch")
    if sha256(RECIPE.read_bytes()).hexdigest() != registration["recipe_sha256"]:
        raise ValueError("Recipe checksum mismatch")
    if (
        sha256((ROOT / "scripts/checkpoint_recovery_cases.py").read_bytes()).hexdigest()
        != registration["generator_sha256"]
    ):
        raise ValueError("Generator checksum mismatch")
    recipe = json.loads(RECIPE.read_text())
    episodes = cases(recipe)
    if digest(episodes) != registration["cases_sha256"]:
        raise ValueError("Case checksum mismatch")
    for field in ("id", "scope", "source_actor"):
        sets = [
            {r[field] for e in episodes if e["split"] == s for r in e["records"]}
            for s in ("design", "heldout")
        ]
        if sets[0] & sets[1]:
            raise ValueError("Source split leakage")
    return recipe, episodes


def evidence_digest(path):
    with sqlite3.connect(path) as db:
        return digest(
            db.execute(
                "SELECT scope,evidence_id,digest,hex(payload) FROM evidence ORDER BY scope,evidence_id"
            ).fetchall()
        )


def prepare(directory, episodes):
    directory.mkdir(parents=True, exist_ok=True)
    store = SQLiteMemoryStore(directory / "memory.db")
    for episode in episodes:
        for row in episode["records"]:
            record = Evidence(
                row["id"],
                row["scope"],
                row["source_actor"],
                row["source_locator"],
                row["producer"],
                row["observed_at"],
                row["recorded_at"],
                EvidenceStatus.RECORDED,
                row["text"].encode(),
                row["digest"],
            )
            formation = MemoryFormation(
                "f-" + row["id"],
                row["scope"],
                MemoryKind.EXPERIENCE,
                (row["id"],),
                row["producer"],
                row["recorded_at"],
                EpistemicState.OBSERVED,
            )
            store.ingest(
                AccessContext("fixture-host", row["scope"], True), row["id"], formation, (record,)
            )
        (directory / (episode["id"] + ".json")).write_text(
            json.dumps(episode["checkpoint"], sort_keys=True)
        )
    store.verify_integrity()


def transcript_state(store, access, authority, recipe):
    if not authorized(authority, access):
        return result("unavailable"), []
    candidates = {}
    for _, records in store.scan_recall(
        access, recorded_as_of=authority["as_of"], effective_at=authority["effective_at"], kinds=()
    ):
        candidates.update({r.evidence_id: r for r in records.values() if visible(r, authority)})
    ordered = sorted(
        candidates.values(), key=lambda r: (r.recorded_at, r.evidence_id), reverse=True
    )
    delivered = []
    for record in ordered[: recipe["transcript_records"]]:
        row = {**reference(record), "text": record.payload.decode()}
        if len(json.dumps([*delivered, row], sort_keys=True).encode()) > recipe["context_bytes"]:
            break
        delivered.append(row)
    ids = [r["evidence_id"] for r in delivered]
    return canonical_state(store, access, authority, ids), ids


def reconstruct(arm, directory, store, access, authority, recipe, identifier):
    if arm == "transcript":
        return transcript_state(store, access, authority, recipe)
    if arm == "checkpoint":
        state = restore_path(directory / (identifier + ".json"), store, access, authority)
    elif arm == "canonical_control":
        state = canonical_state(store, access, authority)
    else:
        raise ValueError("Unknown recovery arm")
    return state, [r["evidence_id"] for r in state["citations"]]


def score(episode, arm, restored, action):
    authority, world = episode["authority"], episode["world"]
    state = restored["state"]
    ready = restored["status"] == "ready"
    denied = not authority["allowed"] and bool(state or restored["citations"])
    expired = (
        arm == "checkpoint"
        and episode["checkpoint"]["expires_at"] <= authority["now"]
        and bool(state or restored["citations"])
    )
    if denied or expired or ready != (state is not None):
        raise ValueError("Unauthorized/expired disclosure or partial restore")
    return {
        "task_id": authority["task_id"],
        "family": episode["family"],
        "split": episode["split"],
        "status": restored["status"],
        "action": action,
        "expected": oracle(episode),
        "success": action == oracle(episode),
        "abstained": action == "abstain",
        "invented_progress": len(set(state["completed"]) - set(world["completed"])) if ready else 0,
        "lost_constraints": sum(
            v and not state["constraints"].get(k, False) for k, v in world["constraints"].items()
        )
        if ready
        else 0,
        "constraint_state_unavailable": any(world["constraints"].values()) and not ready,
        "repeated_completed_work": action.startswith("do:") and action[3:] in world["completed"],
        "unauthorized_disclosure": denied,
        "expired_checkpoint_disclosure": expired,
        "state": state,
        "citations": restored["citations"],
        "context_sha256": digest(restored),
    }


def summary(rows):
    return {
        "cases": len(rows),
        "families": len({r["family"] for r in rows}),
        "correct_actions": sum(r["success"] for r in rows),
        "success_rate": statistics.mean(r["success"] for r in rows),
        "ready_cases": sum(r["status"] == "ready" for r in rows),
        **{
            field: sum(r[field] for r in rows)
            for field in (
                "abstained",
                "invented_progress",
                "lost_constraints",
                "constraint_state_unavailable",
                "repeated_completed_work",
                "unauthorized_disclosure",
                "expired_checkpoint_disclosure",
            )
        },
        "citation_count": sum(len(r["citations"]) for r in rows),
        "status_counts": {
            s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})
        },
    }


def worker(directory, episodes, arm, recipe):
    path = directory / "memory.db"
    store = SQLiteMemoryStore(path)
    before, evidence_before = database_digest(path), evidence_digest(path)
    sidecars_before = digest(
        {p.name: sha256(p.read_bytes()).hexdigest() for p in directory.glob("*.json")}
    )
    rows, elapsed, cpu = [], [], []
    for episode in episodes:
        authority = episode["authority"]
        access = AccessContext(authority["principal"], authority["scope"])
        previous = None
        for _ in range(recipe["repetitions"]):
            started, processor = perf_counter_ns(), process_time_ns()
            state, delivered = reconstruct(
                arm, directory, store, access, authority, recipe, episode["id"]
            )
            action = decide(state, authority)
            elapsed.append((perf_counter_ns() - started) / 1e6)
            cpu.append((process_time_ns() - processor) / 1e6)
            if len(json.dumps(state, sort_keys=True).encode()) > recipe["context_bytes"]:
                raise ValueError("Recovery context overflow")
            for ref in state["citations"]:
                record = store.get_evidence(access, ref["evidence_id"])
                if (
                    not authorized(authority, access)
                    or not visible(record, authority)
                    or reference(record) != ref
                ):
                    raise ValueError("Invalid restored citation")
            if previous is not None and previous != (state, action, delivered):
                raise ValueError("Nondeterministic reconstruction")
            previous = (state, action, delivered)
        row = score(episode, arm, state, action)
        row["delivered_ids"] = delivered
        rows.append(row)
    evidence_after = evidence_digest(path)
    sidecars_after = digest(
        {p.name: sha256(p.read_bytes()).hexdigest() for p in directory.glob("*.json")}
    )
    if (
        before != database_digest(path)
        or evidence_before != evidence_after
        or sidecars_before != sidecars_after
    ):
        raise ValueError("Recovery mutated evidence or sidecar state")
    return {
        "arm": arm,
        "pid": os.getpid(),
        "rows": rows,
        "canonical_unchanged": True,
        "evidence_digest_before": evidence_before,
        "evidence_digest_after": evidence_after,
        "sidecars_unchanged": True,
        "cost": {
            "p50_ms": statistics.median(elapsed),
            "p95_ms": sorted(elapsed)[int(0.95 * (len(elapsed) - 1))],
            "cpu_median_ms": statistics.median(cpu),
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "database_bytes": path.stat().st_size,
            "checkpoint_bytes": sum(p.stat().st_size for p in directory.glob("*.json")),
        },
    }


def paired(before, after, recipe):
    if [(r["task_id"], r["family"]) for r in before] != [
        (r["task_id"], r["family"]) for r in after
    ]:
        raise ValueError("Unmatched tasks")
    groups = sorted({r["family"] for r in before})
    values = {
        g: [
            int(b["success"]) - int(a["success"])
            for a, b in zip(before, after, strict=True)
            if a["family"] == g
        ]
        for g in groups
    }
    rng = random.Random(recipe["bootstrap_seed"])
    draws = sorted(
        statistics.mean(v for g in rng.choices(groups, k=len(groups)) for v in values[g])
        for _ in range(recipe["bootstrap_samples"])
    )
    return {
        "mean_delta": statistics.mean(
            int(b["success"]) - int(a["success"]) for a, b in zip(before, after, strict=True)
        ),
        "ci95": [
            draws[int(0.025 * len(draws))],
            draws[min(len(draws) - 1, int(0.975 * len(draws)))],
        ],
        "families": len(groups),
        "limitation": "Twelve synthetic family units; descriptive, not model-agent evidence.",
    }


def run(recipe, episodes):
    arms = {}
    with tempfile.TemporaryDirectory(prefix="aams-checkpoint124-") as root:
        for arm in ARMS:
            directory = Path(root) / arm
            common = [
                sys.executable,
                "-I",
                str(Path(__file__).resolve()),
                "--directory",
                str(directory),
            ]
            prepared = subprocess.run(
                [*common, "--prepare"], capture_output=True, text=True, check=True, timeout=60
            )
            completed = subprocess.run(
                [*common, "--arm", arm], capture_output=True, text=True, check=True, timeout=120
            )
            arms[arm] = json.loads(completed.stdout)
            arms[arm]["prepare_pid"] = json.loads(prepared.stdout)["pid"]
            arms[arm]["summary"] = {
                s: summary([r for r in arms[arm]["rows"] if r["split"] == s])
                for s in ("design", "heldout")
            }
    return {
        "status": "completed_disposable_contract_experiment",
        "tested_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "registration": json.loads(REGISTRATION.read_text()),
        "execution": json.loads(EXECUTION.read_text()),
        "cases_sha256": digest(episodes),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "arms": arms,
        "checkpoint_minus_transcript": {
            s: paired(
                [r for r in arms["transcript"]["rows"] if r["split"] == s],
                [r for r in arms["checkpoint"]["rows"] if r["split"] == s],
                recipe,
            )
            for s in ("design", "heldout")
        },
        "not_measured": {
            "model_replacement": "NOT RUN: no model/runtime available; interpreter replacement only",
            "model_agent_utility": "NOT MEASURED: deterministic reconstruction and action control",
            "product_persistence": "NOT IMPLEMENTED: proposed contract and temporary sidecars only",
            "real_completion_attestation": "NOT IMPLEMENTED: trusted synthetic host/executor fixture",
            "cold_start_concurrency": "NOT MEASURED",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--prepare", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--arm", choices=ARMS, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "linux":
        raise ValueError("Linux required for RSS protocol")
    recipe, episodes = checked_inputs()
    if args.prepare:
        prepare(args.directory, episodes)
        print(json.dumps({"pid": os.getpid()}))
    else:
        print(
            json.dumps(
                worker(args.directory, episodes, args.arm, recipe)
                if args.arm
                else run(recipe, episodes),
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "invalid_or_failed", "reason": str(error)}))
        sys.exit(3)
