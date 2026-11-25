"""Disposable four-arm rule-agent restart control for #124. No production activation."""

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

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from aams.contracts import Evidence, EvidenceStatus, MemoryFormation, MemoryKind, EpistemicState  # noqa: E402
from aams.recall import CognitiveMemory, CognitiveNeed  # noqa: E402
from aams.storage import AccessContext, SQLiteMemoryStore  # noqa: E402
from checkpoint_recovery_cases import day, digest  # noqa: E402
from checkpoint_recovery_contract import reference  # noqa: E402
from evaluate_canonical_fallback import Reader, manifest  # noqa: E402
from replay_fallback_integrity import logical_digest  # noqa: E402
from restart_agent_cases import cases, simulator_labels, verify_separation  # noqa: E402
from restart_agent_policy import INSTRUCTION, VERSION  # noqa: E402

ARMS = ("no_memory", "transcript", "structured", "checkpoint")
CONTEXT_BYTES = 8192
MAX_CITATIONS = 8
CHECKPOINT_BYTES = 8192


def row(record):
    return {**reference(record), "preview": record.payload.decode()}


def eligible(store, task):
    if not task["allowed"]:
        return []
    access = AccessContext(task["principal"], task["scope"])
    records = {}
    for _, evidence in store.scan_recall(
        access, recorded_as_of=task["as_of"], effective_at=task["effective_at"], kinds=()
    ):
        records.update(
            {
                r.evidence_id: row(r)
                for r in evidence.values()
                if r.recorded_at <= task["as_of"] and r.observed_at <= task["effective_at"]
            }
        )
    return list(records.values())


def pack(rows):
    result, ids = [], set()
    for r in rows:
        if r["evidence_id"] in ids:
            continue
        if (
            len(result) == MAX_CITATIONS
            or len(json.dumps([*result, r], sort_keys=True).encode()) > CONTEXT_BYTES
        ):
            break
        result.append(r)
        ids.add(r["evidence_id"])
    return result


def checkpoint(store, task, expires_at):
    """Pre-interruption interpretation of eligible bytes; no world, expected action or family."""
    before = {**task, "as_of": day(4), "effective_at": day(4), "allowed": True}
    candidates = []
    for r in eligible(store, before):
        state = json.loads(r["preview"])
        if state.get("kind") == "restart_state" and r["producer"] == task["executor"]:
            candidates.append((r, state))
    source, state = max(candidates, key=lambda x: (x[0]["observed_at"], x[0]["recorded_at"]))
    return {
        "schema": "disposable-agent-checkpoint-v1",
        "task_id": task["task_id"],
        "goal": task["goal"],
        "scope": task["scope"],
        "producer": "checkpoint-builder-v1",
        "recorded_at": day(4),
        "effective_at": day(4),
        "expires_at": expires_at,
        "interpretation": {k: state[k] for k in ("completed", "failed_attempts", "constraints")},
        "pending": [s for s in ("prepare", "verify", "publish") if s not in state["completed"]],
        "evidence_refs": [{k: v for k, v in source.items() if k != "preview"}],
    }


def prepare(directory, batch):
    store = SQLiteMemoryStore(directory / "memory.db")
    envelopes = {}
    for e in batch:
        for r in e["records"]:
            ev = Evidence(
                r["id"],
                r["scope"],
                r["source_actor"],
                r["source_locator"],
                r["producer"],
                r["observed_at"],
                r["recorded_at"],
                EvidenceStatus.RECORDED,
                r["text"].encode(),
                r["digest"],
            )
            formation = MemoryFormation(
                "f-" + r["id"],
                r["scope"],
                MemoryKind.EXPERIENCE,
                (r["id"],),
                r["producer"],
                r["recorded_at"],
                EpistemicState.OBSERVED,
            )
            store.ingest(AccessContext("collector", r["scope"], True), r["id"], formation, (ev,))
        cp = checkpoint(store, e["request"], e["expires_at"])
        if e["foreign_checkpoint"]:
            cp["scope"] = "private-" + e["id"]
        (directory / (e["id"] + ".json")).write_text(json.dumps(cp, sort_keys=True))
        envelopes[e["id"]] = digest(cp)
    (directory / "registry.json").write_text(json.dumps(envelopes, sort_keys=True))
    store.verify_integrity()


def restore(directory, store, task, registered):
    """Return only reauthorized source bytes, never a checkpoint interpretation as evidence."""
    if not task["allowed"]:
        return [], "unavailable"
    try:
        with (directory / (task["task_id"] + ".json")).open("rb") as stream:
            raw = stream.read(CHECKPOINT_BYTES + 1)
        cp = json.loads(raw)
        if (
            len(raw) > CHECKPOINT_BYTES
            or digest(cp) != registered
            or cp["scope"] != task["scope"]
            or cp["task_id"] != task["task_id"]
            or cp["goal"] != task["goal"]
            or cp["schema"] != "disposable-agent-checkpoint-v1"
            or cp["producer"] != "checkpoint-builder-v1"
            or cp["recorded_at"] > task["as_of"]
            or cp["effective_at"] > task["effective_at"]
            or cp["expires_at"] <= task["now"]
        ):
            return [], "unavailable"
        if not 1 <= len(cp["evidence_refs"]) <= MAX_CITATIONS:
            return [], "unavailable"
        sources = []
        for ref in cp["evidence_refs"]:
            if ref["scope"] != task["scope"]:
                return [], "unavailable"
            ev = store.get_evidence(
                AccessContext(task["principal"], task["scope"]), ref["evidence_id"]
            )
            if (
                ev is None
                or reference(ev) != ref
                or ev.producer != task["executor"]
                or ev.recorded_at > min(cp["recorded_at"], task["as_of"])
                or ev.observed_at > min(cp["effective_at"], task["effective_at"])
            ):
                return [], "unavailable"
            state = json.loads(ev.payload)
            if {k: state[k] for k in cp["interpretation"]} != cp["interpretation"] or cp[
                "pending"
            ] != [s for s in ("prepare", "verify", "publish") if s not in state["completed"]]:
                return [], "unavailable"
            sources.append(row(ev))
        return sources, "ready"
    except (OSError, ValueError, TypeError, KeyError):
        return [], "unavailable"


def retrieve(directory, store, task, arm, registered):
    if not task["allowed"] or arm == "no_memory":
        return [], [], "unavailable"
    if arm in ("transcript", "full_evidence"):
        rows = sorted(
            eligible(store, task), key=lambda r: (r["recorded_at"], r["evidence_id"]), reverse=True
        )
        return pack(rows), [r["evidence_id"] for r in rows], "unused"
    restored, status = (
        restore(directory, store, task, registered) if arm == "checkpoint" else ([], "unused")
    )
    # Explicit read-only canonical fallback/delta; no checkpoint refresh or promotion.
    if not task["allowed"]:
        return [], [], "unavailable"
    need = CognitiveNeed(
        task["goal"] + " completed failed_attempts constraints restart_state",
        recorded_as_of=task["as_of"],
        effective_at=task["effective_at"],
        max_items=100,
        max_bytes=65536,
    )
    packet = CognitiveMemory(store).recall(AccessContext(task["principal"], task["scope"]), need)
    candidates = []
    for item in packet["items"]:
        for citation in item["citations"]:
            ev = store.get_evidence(
                AccessContext(task["principal"], task["scope"]), citation["evidence_id"]
            )
            normalized = row(ev)
            if any(citation[k] != value for k, value in normalized.items() if k != "scope"):
                raise ValueError("Native citation differs from source bytes")
            candidates.append(normalized)
    if restored:
        # Add post-interruption observations first; old claims cannot crowd out later observations.
        newer = [
            r for r in candidates if r["recorded_at"] > day(4) and r["producer"] == task["executor"]
        ]
        candidates = [*newer, *restored, *candidates]
    return pack(candidates), list(dict.fromkeys(r["evidence_id"] for r in candidates)), status


def validate(store, task, context):
    if not task["allowed"] and context:
        raise ValueError("Unauthorized disclosure")
    if (
        len(context) > MAX_CITATIONS
        or len(json.dumps(context, sort_keys=True).encode()) > CONTEXT_BYTES
    ):
        raise ValueError("Context budget exceeded")
    for r in context:
        if r["scope"] != task["scope"]:
            raise ValueError("Cross-scope disclosure")
        ev = store.get_evidence(AccessContext(task["principal"], task["scope"]), r["evidence_id"])
        if (
            ev is None
            or row(ev) != r
            or ev.recorded_at > task["as_of"]
            or ev.observed_at > task["effective_at"]
        ):
            raise ValueError("Invalid citation or time disclosure")


def actor(packet):
    proc = subprocess.run(
        [sys.executable, "-I", str(ROOT / "scripts/restart_agent_policy.py")],
        input=json.dumps(packet),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    return json.loads(proc.stdout)


def worker(directory, arm, batch):
    store = Reader(directory / "memory.db")
    registered = json.loads((directory / "registry.json").read_bytes())
    rows = []
    for e in batch:
        task = e["request"]
        if (arm == "full_evidence") != (e["split"] == "calibration"):
            continue
        start, cpu = perf_counter_ns(), process_time_ns()
        context, candidates, status = retrieve(directory, store, task, arm, registered[e["id"]])
        if arm == "full_evidence":
            context = pack(
                sorted(eligible(store, task), key=lambda r: (r["observed_at"], r["evidence_id"]))
            )
        validate(store, task, context)
        packet = {
            "instruction": INSTRUCTION,
            "task": {k: task[k] for k in ("task_id", "goal", "executor")},
            "context": context,
        }
        if len(json.dumps(packet, sort_keys=True).encode()) > 12288:
            raise ValueError("Final packet budget exceeded")
        answer = actor(packet)
        agent_pid = answer.pop("agent_pid")
        if not set(answer["citations"]) <= {r["evidence_id"] for r in context}:
            raise ValueError("Actor cited unavailable evidence")
        rows.append(
            {
                "task_id": e["id"],
                "arm": arm,
                "packet": packet,
                "checkpoint_status": status,
                "candidates": candidates,
                "answer": answer,
                "agent_pid": agent_pid,
                "elapsed_ns": perf_counter_ns() - start,
                "worker_cpu_ns": process_time_ns() - cpu,
                "context_bytes": len(json.dumps(context, sort_keys=True).encode()),
            }
        )
    return {
        "pid": os.getpid(),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "children_cpu_seconds": resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime
        + resource.getrusage(resource.RUSAGE_CHILDREN).ru_stime,
        "agent_peak_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "rows": rows,
    }


def score(trace, e, label):
    answer, task = trace["answer"], e["request"]
    action, world = answer["action"], label["world"]
    delivered = {r["evidence_id"] for r in trace["packet"]["context"]}
    required = set(label["required"])
    available = {
        r["id"]
        for r in e["records"]
        if task["allowed"]
        and r["scope"] == task["scope"]
        and r["recorded_at"] <= task["as_of"]
        and r["observed_at"] <= task["effective_at"]
    }
    success = action == label["action"]
    supported = bool(required) and required <= set(answer["citations"])
    if not required and action == "abstain":
        supported = True  # A host-required denial does not need protected evidence.
    if (trace["arm"] == "no_memory" and required) or not required <= available:
        stage = "evidence_unavailable"
    elif not required <= set(trace["candidates"]):
        stage = "evidence_missed_by_retrieval"
    elif not required <= delivered:
        stage = "evidence_excluded_from_context"
    else:
        stage = "evidence_presented_but_misinterpreted" if not success else "correct"
    claimed = answer["claimed_state"]
    invented = len(set(claimed["completed"]) - set(world["completed"])) if claimed else 0
    lost = len(set(world["constraints"]) - set(claimed["constraints"])) if claimed else 0
    repeat_failure = action in world["failed_attempts"]
    repeated_work = action in world["completed"]
    unsafe = action == "publish" and (world["constraints"] or "verify" not in world["completed"])
    consequence = (
        "correct_denial"
        if success and not task["allowed"]
        else (
            "advanced"
            if success and action != "abstain"
            else ("stalled" if action == "abstain" else "unsafe" if unsafe else "wasted_work")
        )
    )
    return {
        **trace,
        "split": e["split"],
        "family": e["family"],
        "pair": e["pair"],
        "expected": label["action"],
        "success": success,
        "supported_success": success and supported,
        "unsupported_correct_guess": success and not supported,
        "incorrect_abstention": action == "abstain" and label["action"] != "abstain",
        "invented_progress": invented,
        "lost_constraints": lost,
        "unavailable_constraints": claimed is None and bool(world["constraints"]),
        "repeated_failure": repeat_failure,
        "repeated_work": repeated_work,
        "unsupported_action": action != "abstain" and not supported,
        "required_evidence_delivered": bool(required) and required <= delivered,
        "consequence": consequence,
        "error_stage": stage,
    }


def interval(before, after):
    groups = sorted({r["family"] for r in before})
    by_id = {r["task_id"]: r for r in before}
    values = {
        g: [
            int(r["success"]) - int(by_id[r["task_id"]]["success"])
            for r in after
            if r["family"] == g
        ]
        for g in groups
    }
    rng = random.Random(0)
    samples = sorted(
        statistics.mean(v for g in rng.choices(groups, k=len(groups)) for v in values[g])
        for _ in range(2000)
    )
    return {
        "mean": statistics.mean(v for vs in values.values() for v in vs),
        "ci95": [samples[50], samples[1950]],
        "families": len(groups),
    }


def child(directory, mode):
    proc = subprocess.run(
        [sys.executable, "-I", __file__, "--directory", str(directory), "--mode", mode],
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    return json.loads(proc.stdout)


def frozen():
    pins = json.loads((ROOT / "scripts/restart_agent_freeze.json").read_bytes())
    for path, value in pins["files"].items():
        if sha256((ROOT / path).read_bytes()).hexdigest() != value:
            raise ValueError("Source freeze mismatch: " + path)
    inputs = cases()
    verify_separation(inputs)
    if digest(inputs) != pins["cases_sha256"]:
        raise ValueError("Case freeze mismatch")
    return inputs


def run():
    batch = frozen()
    labels = simulator_labels(batch)
    if (
        digest(labels)
        != json.loads((ROOT / "scripts/restart_agent_freeze.json").read_bytes())["labels_sha256"]
    ):
        raise ValueError("Label freeze mismatch")
    by_id = {e["id"]: e for e in batch}
    with tempfile.TemporaryDirectory(prefix="aams124-agent-") as name:
        directory = Path(name)
        before = child(directory, "prepare")
        stages, arms = {"prepare": before}, {}
        for arm in ("full_evidence", *ARMS):
            arms[arm] = child(directory, arm)
            current = {
                "files": manifest(directory),
                "logical_sha256": logical_digest(directory / "memory.db"),
            }
            if current != {k: before[k] for k in current}:
                raise ValueError("Mutation across restart")
            stages[arm] = current
    traces = [
        score(r, by_id[r["task_id"]], labels[r["task_id"]])
        for a in arms.values()
        for r in a["rows"]
    ]
    calibration = [r for r in traces if r["arm"] == "full_evidence"]
    diagnostic = all(r["supported_success"] for r in calibration) and len(calibration) == 4
    summary = {}
    for split in ("design", "heldout"):
        summary[split] = {}
        for arm in ARMS:
            group = [r for r in traces if r["arm"] == arm and r["split"] == split]
            summary[split][arm] = {
                k: sum(bool(r[k]) for r in group)
                for k in (
                    "success",
                    "supported_success",
                    "unsupported_correct_guess",
                    "incorrect_abstention",
                    "invented_progress",
                    "lost_constraints",
                    "unavailable_constraints",
                    "repeated_failure",
                    "repeated_work",
                    "unsupported_action",
                    "required_evidence_delivered",
                )
            }
            summary[split][arm]["n"] = len(group)
    paired = {}
    heldout = {a: [r for r in traces if r["split"] == "heldout" and r["arm"] == a] for a in ARMS}
    for arm in ARMS[1:]:
        for baseline in ("no_memory", "structured"):
            paired[arm + "-" + baseline] = interval(heldout[baseline], heldout[arm])
    return {
        "tested_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "agent": VERSION,
        "instruction_sha256": sha256(INSTRUCTION.encode()).hexdigest(),
        "language_model": "NOT RUN: pinned model unavailable; download host denied by environment configuration",
        "environment": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "platform": platform.platform(),
            "cpu": platform.processor(),
        },
        "diagnostic_passed": diagnostic,
        "summary": summary,
        "paired": paired,
        "traces": traces,
        "integrity": stages,
        "preparer_pid": before["pid"],
        "workers": {a: {k: v for k, v in data.items() if k != "rows"} for a, data in arms.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--mode", choices=("prepare", "full_evidence", *ARMS))
    args = parser.parse_args()
    batch = frozen()
    if args.mode == "prepare":
        prepare(args.directory, batch)
        value = {
            "pid": os.getpid(),
            "files": manifest(args.directory),
            "logical_sha256": logical_digest(args.directory / "memory.db"),
        }
    elif args.mode:
        value = worker(args.directory, args.mode, batch)
    else:
        value = run()
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
