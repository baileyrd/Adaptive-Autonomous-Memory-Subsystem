"""#119 historical reproduction and preregistered source-held-out selection experiment."""

import argparse
import json
import os
import resource
import statistics
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cognitive_task_agent import INSTRUCTION, decide  # noqa: E402
from cognitive_task_cases import cases as original_cases, digest  # noqa: E402
from copy_context_cases import RECIPE, cases  # noqa: E402
from copy_context_selector import copy_key, select_context  # noqa: E402
from evaluate_cognitive_tasks import (  # noqa: E402
    context_for,
    database_digest,
    interval,
    prepare,
    score,
    summarize,
    validate_context,
    verify_registration,
)
from evaluate_semantic import timestamp  # noqa: E402
from aams.recall import CognitiveMemory, CognitiveNeed  # noqa: E402
from aams.storage import AccessContext, SQLiteMemoryStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = Path(__file__).with_name("copy_context_preregistration.json")
EXECUTION = Path(__file__).with_name("copy_context_execution.json")
ARMS = ("raw_search", "structured", "copy_diverse")


def checked_inputs():
    verify_registration(ROOT / "scripts/cognitive_task_recipe.json")
    registration = json.loads(REGISTRATION.read_text())
    execution = json.loads(EXECUTION.read_text())
    for name, expected in execution["source_sha256"].items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Preregistered execution source checksum mismatch")
    if sha256(RECIPE.read_bytes()).hexdigest() != registration["recipe_sha256"]:
        raise ValueError("Fresh recipe checksum mismatch")
    if (
        sha256((ROOT / "scripts/copy_context_cases.py").read_bytes()).hexdigest()
        != registration["generator_sha256"]
    ):
        raise ValueError("Fresh generator checksum mismatch")
    recipe = json.loads(RECIPE.read_text())
    episodes = cases(recipe)
    if digest(episodes) != registration["cases_sha256"]:
        raise ValueError("Fresh cases checksum mismatch")
    trace = ROOT / "docs/audit/cognitive-task-pilot-decisions.jsonl"
    if sha256(trace.read_bytes()).hexdigest() != registration["historical_trace_sha256"]:
        raise ValueError("Historical trace checksum mismatch")
    original = original_cases(json.loads((ROOT / "scripts/cognitive_task_recipe.json").read_text()))
    buckets = [[e for e in episodes if e["split"] == split] for split in ("design", "heldout")]
    buckets.append(original)
    for field in ("id", "scope", "source"):
        sets = [{r[field] for e in bucket for r in e["observations"]} for bucket in buckets]
        if any(sets[a] & sets[b] for a in range(3) for b in range(a + 1, 3)):
            raise ValueError("Source split leakage")
    return recipe, episodes


def candidate_pool(memory, task, recipe):
    need = CognitiveNeed(
        task["topic"],
        max_items=recipe["candidate_citations"],
        max_bytes=recipe["candidate_bytes"],
        recorded_as_of=timestamp(task["as_of"]),
        effective_at=timestamp(task["day"]),
    )
    packet = memory.recall(AccessContext("pilot", task["scope"]), need)
    rows, ids = [], set()
    for item in packet["items"]:
        for row in item["citations"]:
            if row["evidence_id"] not in ids:
                rows.append(row)
                ids.add(row["evidence_id"])
    truncated = packet["truncated"] or len(rows) > recipe["candidate_citations"]
    rows = rows[: recipe["candidate_citations"]]
    validate_context(memory.store, task, rows)
    return rows, truncated


def obtain_context(memory, task, arm, recipe):
    if arm != "copy_diverse":
        context = context_for(memory, task, arm, recipe)
        return context, {"candidate_window_truncated": None, "inspected_candidates": None}
    pool, truncated = candidate_pool(memory, task, recipe)
    context = select_context(
        pool, max_citations=recipe["max_citations"], max_bytes=recipe["context_bytes"]
    )
    return context, {
        "candidate_window_truncated": truncated,
        "inspected_candidates": len(pool),
        "declared_copy_groups": len({copy_key(row) for row in pool}),
        "dropped_exact_copy_instances": len(pool) - len({copy_key(row) for row in pool}),
    }


def reproduce():
    completed = subprocess.run(
        [sys.executable, "-I", str(ROOT / "scripts/evaluate_cognitive_tasks.py")],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    actual = json.loads(completed.stdout)
    frozen = [
        json.loads(line)
        for line in (ROOT / "docs/audit/cognitive-task-pilot-decisions.jsonl")
        .read_text()
        .splitlines()
    ]
    for arm, result in actual["arms"].items():
        expected = [row for row in frozen if row["arm"] == arm]
        if [(r["task_id"], r["decision"]) for r in result["rows"]] != [
            (r["task_id"], r["decision"]) for r in expected
        ]:
            raise ValueError("Historical decision reproduction failed")
    recipe = json.loads((ROOT / "scripts/cognitive_task_recipe.json").read_text())
    episodes = [e for e in original_cases(recipe) if e["family"] == "copied_report"]
    diagnostics = []
    with tempfile.TemporaryDirectory(prefix="aams-119-original-") as root:
        path = Path(root) / "memory.db"
        prepare(path, episodes)
        memory = CognitiveMemory(SQLiteMemoryStore(path))
        before = database_digest(path)
        for episode in episodes:
            task = episode["tasks"][-1]
            request = {"topic": task["topic"], "checks": task["checks"], "instruction": INSTRUCTION}
            for arm in ("raw_search", "structured"):
                small = context_for(memory, task, arm, recipe)
                full = context_for(
                    memory, task, arm, {**recipe, "max_citations": 100, "context_bytes": 65536}
                )
                validate_context(memory.store, task, small)
                validate_context(memory.store, task, full)
                compact = select_context(small, max_citations=8, max_bytes=8192)
                diagnostics.append(
                    {
                        "episode_id": episode["id"],
                        "arm": arm,
                        "bounded_ids": [r["evidence_id"] for r in small],
                        "full_ids": [r["evidence_id"] for r in full],
                        "chronology": episode["observations"],
                        "bounded_decision": decide(request, small),
                        "dedup_after_truncation_decision": decide(request, compact),
                        "full_visible_decision": decide(request, full),
                        "bounded_contains_failure": any(
                            r["evidence_id"].endswith("-failure") for r in small
                        ),
                        "full_contains_failure": any(
                            r["evidence_id"].endswith("-failure") for r in full
                        ),
                    }
                )
        if before != database_digest(path):
            raise ValueError("Historical diagnosis mutated canonical memory")
    return {
        "matched_frozen_decisions": len(frozen),
        "diagnostics": diagnostics,
        "classification": "Later failures exist but are lost before the context cap. Same agent stops with full context; compacting already-truncated citations cannot recover missing evidence.",
    }


def worker(path, episodes, arm, recipe):
    memory = CognitiveMemory(SQLiteMemoryStore(path))
    before = database_digest(path)
    rows, wall, cpu = [], [], []
    for episode in episodes:
        for task in episode["tasks"]:
            request = {"topic": task["topic"], "checks": task["checks"], "instruction": INSTRUCTION}
            reference = None
            for _ in range(recipe["repetitions"]):
                started, processor = perf_counter_ns(), process_time_ns()
                context, selection = obtain_context(memory, task, arm, recipe)
                decision = decide(request, context)
                wall.append((perf_counter_ns() - started) / 1e6)
                cpu.append((process_time_ns() - processor) / 1e6)
                validate_context(memory.store, task, context)
                if reference is not None and reference != decision:
                    raise ValueError("Nondeterministic decision")
                reference = decision
            row = score(episode, task, request, context, decision)
            visible_later = []
            for identifier in episode["later_ids"]:
                record = memory.store.get_evidence(
                    AccessContext("pilot", task["scope"]), identifier
                )
                if record.observed_at <= timestamp(task["day"]) and record.recorded_at <= timestamp(
                    task["as_of"]
                ):
                    visible_later.append(identifier)
            delivered = {r["evidence_id"] for r in context}
            row.update(selection)
            row.update(
                later_visible_ids=visible_later,
                later_coverage=bool(visible_later) and set(visible_later) <= delivered,
                benign=episode["family"] in ("copy_clean", "independent_clean", "recovery")
                and row["expected"] == "proceed",
                wrong_stop=row["expected"] == "proceed" and decision["action"] == "stop",
                conflict_case=episode["family"] == "same_time_conflict" and bool(visible_later),
                conflict_handled=decision["conflict_detected"] and decision["action"] == "abstain",
            )
            row["context_ids"] = [r["evidence_id"] for r in context]
            row["context_group_keys"] = [copy_key(r) for r in context]
            rows.append(row)
    if before != database_digest(path):
        raise ValueError("Fresh replay mutated canonical memory")
    return {
        "arm": arm,
        "pid": os.getpid(),
        "rows": rows,
        "canonical_unchanged": True,
        "cost": {
            "p50_ms": statistics.median(wall),
            "p95_ms": sorted(wall)[int(0.95 * (len(wall) - 1))],
            "cpu_median_ms": statistics.median(cpu),
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "database_bytes": path.stat().st_size,
        },
    }


def summary(rows):
    result = summarize(rows)
    later = [r for r in rows if r["later_visible_ids"]]
    benign = [r for r in rows if r["benign"]]
    result.update(
        unsafe_proceed_rate=result["unsafe_proceed_count"] / len(rows),
        later_report_tasks=len(later),
        later_report_coverage=sum(r["later_coverage"] for r in later) / len(later)
        if later
        else None,
        benign_tasks=len(benign),
        benign_losses=sum(not r["success"] for r in benign),
        benign_abstentions=sum(r["abstained"] for r in benign),
        wrong_stops=sum(r["wrong_stop"] for r in rows),
        truncated_candidate_windows=sum(r["candidate_window_truncated"] is True for r in rows),
    )
    return result


def run(recipe, episodes):
    history = reproduce()
    arms = {}
    with tempfile.TemporaryDirectory(prefix="aams-119-fresh-") as root:
        for arm in ARMS:
            path = Path(root) / (arm + ".db")
            common = [sys.executable, "-I", str(Path(__file__).resolve()), "--db", str(path)]
            prepared = subprocess.run(
                [*common, "--prepare"], capture_output=True, text=True, check=True, timeout=60
            )
            completed = subprocess.run(
                [*common, "--arm", arm], capture_output=True, text=True, check=True, timeout=120
            )
            arms[arm] = json.loads(completed.stdout)
            arms[arm]["prepare_pid"] = json.loads(prepared.stdout)["pid"]
            arms[arm]["summary"] = {
                split: summary([r for r in arms[arm]["rows"] if r["split"] == split])
                for split in ("design", "heldout")
            }
    paired = {}
    for split in ("design", "heldout"):
        before = [r for r in arms["structured"]["rows"] if r["split"] == split]
        after = [r for r in arms["copy_diverse"]["rows"] if r["split"] == split]
        paired[split] = {}
        for metric in ("success", "unsafe_proceed", "abstained"):
            paired[split][metric] = interval(
                [{**r, "success": r[metric]} for r in before],
                [{**r, "success": r[metric]} for r in after],
                recipe["bootstrap_samples"],
                recipe["bootstrap_seed"],
            )
            paired[split][metric]["limitation"] = (
                "Seven source-held-out mechanism families, not independent real-world reasoning samples; descriptive synthetic pilot."
            )
    return {
        "status": "completed_offline_copy_context_experiment",
        "tested_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "cases_sha256": digest(episodes),
        "registration": json.loads(REGISTRATION.read_text()),
        "execution": json.loads(EXECUTION.read_text()),
        "historical_reproduction": history,
        "arms": arms,
        "paired_control_minus_structured": paired,
        "limits": [
            "Unchanged synthetic rule agent; no model/learning claim.",
            "Declared-copy key does not attest independence or detect relabelled/paraphrased copies.",
            "Control inspects a larger bounded internal candidate pool; agent context ceiling unchanged.",
            "No product serving change, canonical mutation, activation or authority change.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--prepare", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--arm", choices=ARMS, help=argparse.SUPPRESS)
    args = parser.parse_args()
    recipe, episodes = checked_inputs()
    if sys.platform != "linux":
        raise ValueError("Linux required for KiB RSS protocol")
    if args.prepare:
        prepare(args.db, episodes)
        print(json.dumps({"pid": os.getpid()}))
    else:
        print(
            json.dumps(
                worker(args.db, episodes, args.arm, recipe) if args.arm else run(recipe, episodes),
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
