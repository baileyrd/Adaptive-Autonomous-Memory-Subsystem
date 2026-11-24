"""Optional Linux process footprints for pinned-model load, index build and reopened serving.

Uses the v0.9 bounded SQuAD workload. No downloads or quality evaluation. Each arm/stage
runs with -I in a new process; a serving process reopens its own arm's built database.
"""

import argparse
import json
import os
import platform
import resource
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter_ns

sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_onnx_cpu import DATASET_PINS, percentile  # noqa: E402
from evaluate_semantic import timestamp  # noqa: E402
from memory_probe import build  # noqa: E402
from onnx_encoder import OnnxSentenceEncoder, Variant, file_sha256  # noqa: E402
from profile_neural_memory import resident_kib  # noqa: E402

from aams.recall import CognitiveMemory, CognitiveNeed  # noqa: E402
from aams.representations import DeterministicFixtureProvider  # noqa: E402
from aams.retrieval_routing import RetrievalMode  # noqa: E402
from aams.storage import AccessContext, SQLiteMemoryStore  # noqa: E402

STAGES = ("model", "build", "serve")
ARMS = ("guarded", "onnx")


def snapshot():
    return {
        "current_rss_kib": resident_kib(),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def recall_pass(memory, groups, provider):
    """Same scoped, time-filtered HYBRID requests as the v0.9 cost benchmark."""
    elapsed = []
    for group in groups:
        access = AccessContext("fixture", group["domain"])
        for task in group["tasks"]:
            need = CognitiveNeed(task["query"], max_items=3, recorded_as_of=timestamp(task["day"]))
            start = perf_counter_ns()
            memory.recall(access, need, provider=provider, requested_mode=RetrievalMode.HYBRID)
            elapsed.append(perf_counter_ns() - start)
    if not elapsed:
        raise ValueError("Empty serving workload")
    return elapsed


def measure(args):
    # Hash with bounded buffers; never parse the full dataset in a measured child.
    started = perf_counter_ns()
    if file_sha256(args.data) != DATASET_PINS[args.partition]:
        raise ValueError("Dataset checksum mismatch")
    if file_sha256(args.groups) != args.groups_sha256:
        raise ValueError("Prepared workload checksum mismatch")
    groups = json.loads(args.groups.read_text())
    points = {"workload_loaded": snapshot()}
    load_start = perf_counter_ns()
    provider = (
        DeterministicFixtureProvider()
        if args.arm == "guarded"
        else OnnxSentenceEncoder(
            args.model, variant=Variant(**json.loads(args.variant.read_text()))
        )
    )
    load_ms = (perf_counter_ns() - load_start) / 1e6
    points["provider_loaded"] = snapshot()
    result = {
        "arm": args.arm,
        "stage": args.stage,
        "pid": os.getpid(),
        "load_ms": round(load_ms, 3),
        "groups": len(groups),
        "records": sum(len(group["records"]) for group in groups),
        "tasks": sum(len(group["tasks"]) for group in groups),
        "snapshots": points,
    }
    if args.stage != "model":
        if (args.stage == "build") == args.db.exists():
            raise ValueError("Build requires new database; serve requires built database")
        store = SQLiteMemoryStore(args.db)
        if args.stage == "build":
            build_start = perf_counter_ns()
            build(store, groups, provider)
            result["build_ms"] = round((perf_counter_ns() - build_start) / 1e6, 3)
            points["index_built"] = snapshot()
            result["database_bytes"] = args.db.stat().st_size
        else:
            memory = CognitiveMemory(store)
            cold = recall_pass(memory, groups, provider)
            result["cold_pass_ms"] = percentile(cold)
            result["cold_first_request_ms"] = round(cold[0] / 1e6, 3)
            result["startup_through_cold_pass_ms"] = round((perf_counter_ns() - started) / 1e6, 3)
            points["cold_served"] = snapshot()
            warm = []
            for _ in range(args.repetitions):
                warm.extend(recall_pass(memory, groups, provider))
            result["warm_ms"] = percentile(warm)
            result["requests"] = len(warm)
            points["warm_served"] = snapshot()
    result["elapsed_ms"] = round((perf_counter_ns() - started) / 1e6, 3)
    return result


def run(args):
    if sys.platform != "linux":
        raise ValueError("RSS protocol requires Linux (ru_maxrss is KiB)")
    if file_sha256(args.data) != DATASET_PINS[args.partition]:
        raise ValueError("Dataset checksum mismatch")
    variant = Variant(**json.loads(args.variant.read_text()))
    rows = {}
    with tempfile.TemporaryDirectory(prefix="aams-memory-") as directory:
        groups = Path(directory) / "groups.json"
        # Full SQuAD parsing must not inflate the parent or measured-child RSS floor.
        subprocess.run(
            [
                sys.executable,
                "-I",
                str(Path(__file__).resolve()),
                "--model",
                str(args.model.resolve()),
                "--variant",
                str(args.variant.resolve()),
                "--data",
                str(args.data.resolve()),
                "--partition",
                args.partition,
                "--prepare",
                "--groups",
                str(groups),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        groups_digest = file_sha256(groups)
        for arm in ARMS:
            db = Path(directory) / f"{arm}.db"
            rows[arm] = {}
            for stage in STAGES:
                command = [
                    sys.executable,
                    "-I",
                    str(Path(__file__).resolve()),
                    "--model",
                    str(args.model.resolve()),
                    "--variant",
                    str(args.variant.resolve()),
                    "--data",
                    str(args.data.resolve()),
                    "--partition",
                    args.partition,
                    "--repetitions",
                    str(args.repetitions),
                    "--groups",
                    str(groups),
                    "--groups-sha256",
                    groups_digest,
                    "--arm",
                    arm,
                    "--stage",
                    stage,
                    "--db",
                    str(db),
                ]
                wall_start = perf_counter_ns()
                completed = subprocess.run(
                    command, check=True, capture_output=True, text=True, timeout=300
                )
                row = json.loads(completed.stdout)
                if row["arm"] != arm or row["stage"] != stage:
                    raise ValueError("Child identity mismatch")
                row["spawn_to_exit_ms"] = round((perf_counter_ns() - wall_start) / 1e6, 3)
                rows[arm][stage] = row
    added = rows["onnx"]["serve"]["warm_ms"][1] - rows["guarded"]["serve"]["warm_ms"][1]
    peaks = {
        arm: max(
            point["peak_rss_kib"] for row in stages.values() for point in row["snapshots"].values()
        )
        for arm, stages in rows.items()
    }
    ratio = peaks["onnx"] / peaks["guarded"]
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor(),
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            "unknown",
        ),
        "cpuinfo_sha256": file_sha256(Path("/proc/cpuinfo")),
        "dataset_sha256": DATASET_PINS[args.partition],
        "partition": args.partition,
        "prepared_workload_sha256": groups_digest,
        "variant": json.loads(args.variant.read_text()),
        "model_files_verified_by_encoder": variant.files,
        "arms": rows,
        "resource_screen": {
            "added_warm_p95_ms": round(added, 3),
            "max_process_peak_rss_ratio": round(ratio, 3),
            "passes": added <= 5 and ratio <= 2,
        },
        "limitations": "Sequential single-worker diagnostic; process-cold, OS cache uncontrolled. "
        "Peaks are cumulative per child, not additive allocations. No quality measured; "
        "v0.9 benchmark remains the qualification protocol. No activation.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--variant", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--partition", choices=tuple(DATASET_PINS), required=True)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--arm", choices=ARMS, help=argparse.SUPPRESS)
    parser.add_argument("--stage", choices=STAGES, help=argparse.SUPPRESS)
    parser.add_argument("--db", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--groups", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--groups-sha256", help=argparse.SUPPRESS)
    parser.add_argument("--prepare", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "linux" or not 1 <= args.repetitions <= 20:
        parser.error("Use Linux and 1 to 20 repetitions")
    if any((args.arm, args.stage, args.db)) and not all((args.arm, args.stage, args.db)):
        parser.error("Child arm, stage and db must be supplied together")
    if args.prepare:
        from benchmark_onnx_cpu import groups_for

        args.groups.write_text(json.dumps(groups_for(args.data, args.partition)))
        return
    print(json.dumps(measure(args) if args.arm else run(args), indent=2))


if __name__ == "__main__":
    main()
