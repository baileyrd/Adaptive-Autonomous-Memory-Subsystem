"""Bounded, evaluation-only encoder resource measurements in separate processes.

`--static` measures the stdlib static encoder serving through the BM25 rerank arm against the
same guarded comparator and gates as the v0.9 ONNX profiles.
"""

import argparse
import json
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
from math import ceil
from pathlib import Path
from time import perf_counter_ns, process_time_ns

from evaluate_retrieval import squad_groups
from evaluate_semantic import timestamp
from fusion import fusion_arm, rerank_arm
from memory_probe import build
from onnx_encoder import CPU_PROFILES, OnnxSentenceEncoder, Variant, file_sha256
from static_encoder import StaticEmbeddingEncoder

from aams.recall import CognitiveMemory, CognitiveNeed
from aams.representations import DeterministicFixtureProvider
from aams.retrieval_routing import RetrievalMode
from aams.storage import AccessContext, SQLiteMemoryStore

DATASET_PINS = {
    "dev": "95aa6a52d5d6a735563366753ca50492a658031da74f301ac5238b03966972c9",
    "train": "3527663986b8295af4f7fcdff1ba1ff3f72d07d61a20f487cb238a6ef92fd955",
}
PARITY_TOLERANCE = 1e-5
STATIC_ARM = "static_rerank"
STATIC_FUSION_ARM = "static_fusion"
STATIC_ARMS = {STATIC_ARM: rerank_arm, STATIC_FUSION_ARM: fusion_arm}


def percentile(samples):
    ordered = sorted(samples)
    return [
        round(statistics.median(ordered) / 1e6, 3),
        round(ordered[ceil(0.95 * len(samples)) - 1] / 1e6, 3),
    ]


def groups_for(path, partition):
    if file_sha256(path) != DATASET_PINS[partition]:
        raise ValueError("Dataset checksum mismatch")
    data = json.loads(path.read_text())
    data["data"] = data["data"][:3]
    for article in data["data"]:
        article["paragraphs"] = article["paragraphs"][:8]
    return squad_groups(data, 1)[0]


def measure(args):
    groups = json.loads(args.groups.read_text())
    start = perf_counter_ns()
    if args.arm == "guarded":
        provider = DeterministicFixtureProvider()
    elif args.arm in STATIC_ARMS:
        provider = StaticEmbeddingEncoder(args.model, record_phases=True)
    else:
        provider = OnnxSentenceEncoder(
            args.model,
            cpu_profile=args.arm,
            record_phases=True,
            variant=Variant(**json.loads(args.variant.read_text())) if args.variant else None,
        )
    fields = {
        "load_ms": round((perf_counter_ns() - start) / 1e6, 3),
        "load_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    with tempfile.TemporaryDirectory(prefix="aams-onnx-arm-") as directory:
        store = SQLiteMemoryStore(Path(directory) / "memory.db")
        build(store, groups, provider)
        memory = CognitiveMemory(store)

        def serve(access, need):
            if args.arm in STATIC_ARMS:
                return STATIC_ARMS[args.arm](memory, provider, access, need, 3)
            return memory.recall(
                access, need, provider=provider, requested_mode=RetrievalMode.HYBRID
            )

        workload = [
            (
                AccessContext("fixture", group["domain"]),
                CognitiveNeed(task["query"], max_items=3, recorded_as_of=timestamp(task["day"])),
            )
            for group in groups
            for task in group["tasks"]
        ]
        if args.arm != "guarded":
            provider.phase_timings_ns.clear()
            cold = perf_counter_ns()
            vectors = [provider.encode(need.query) for _, need in workload]
            fields["first_query_pass_ms"] = round((perf_counter_ns() - cold) / 1e6, 3)
        rankings = []
        for access, need in workload:
            packet = serve(access, need)
            rankings.append(
                [item.get("id") or item["citations"][0]["evidence_id"] for item in packet["items"]]
            )
        if args.arm != "guarded":
            args.vectors.write_text(json.dumps({"vectors": vectors, "rankings": rankings}))
        if args.arm != "guarded":
            provider.phase_timings_ns.clear()
        wall, cpu = [], []
        for _ in range(args.repetitions):
            for access, need in workload:
                start, cpu_start = perf_counter_ns(), process_time_ns()
                serve(access, need)
                cpu.append(process_time_ns() - cpu_start)
                wall.append(perf_counter_ns() - start)
        fields.update(
            requests=len(wall),
            wall_ms=percentile(wall),
            cpu_ms=percentile(cpu),
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        )
        if args.arm != "guarded":
            if args.arm not in STATIC_ARMS and len(provider.phase_timings_ns) != len(wall):
                raise RuntimeError("A timed request did not execute the encoder")
            fields["phase_ms"] = {
                name: percentile([getattr(t, name + "_ns") for t in provider.phase_timings_ns])
                for name in ("tokenize", "prepare", "inference", "normalize", "total")
            }
    return fields


def run(args):
    rows = {}
    with tempfile.TemporaryDirectory(prefix="aams-onnx-cpu-") as directory:
        groups = Path(directory) / "groups.json"
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--model",
                str(args.model),
                "--data",
                str(args.data),
                "--partition",
                args.partition,
                "--prepare",
                "--groups",
                str(groups),
            ],
            check=True,
            timeout=90,
        )
        if args.static:
            candidates = tuple(STATIC_ARMS)
        else:
            candidates = ("baseline", "threads2") if args.variant else CPU_PROFILES
        for arm in ("guarded", *candidates):
            vectors = Path(directory) / f"{arm}.json"
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--model",
                str(args.model),
                "--data",
                str(args.data),
                "--partition",
                args.partition,
                "--arm",
                arm,
                "--groups",
                str(groups),
                "--vectors",
                str(vectors),
                "--repetitions",
                str(args.repetitions),
            ]
            if args.variant:
                command += ["--variant", str(args.variant)]
            completed = subprocess.run(
                command, check=True, stdout=subprocess.PIPE, text=True, timeout=180
            )
            rows[arm] = json.loads(completed.stdout)
            if arm == "guarded":
                continue
            actual = json.loads(vectors.read_text())
            if arm == candidates[0] or args.static:  # Serving modes differ in ranking.
                reference = actual
            error = max(
                abs(a - b)
                for left, right in zip(reference["vectors"], actual["vectors"], strict=True)
                for a, b in zip(left, right, strict=True)
            )
            added = rows[arm]["wall_ms"][1] - rows["guarded"]["wall_ms"][1]
            ratio = rows[arm]["peak_rss_kib"] / rows["guarded"]["peak_rss_kib"]
            same_rankings = actual["rankings"] == reference["rankings"]
            rows[arm].update(
                max_vector_delta=error,
                ranking_parity=same_rankings,
                added_p95_ms=round(added, 3),
                rss_ratio=round(ratio, 3),
                qualifies=error <= PARITY_TOLERANCE and same_rankings and added <= 5 and ratio <= 2,
            )
    return {
        "partition": args.partition,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": Path("/proc/cpuinfo")
        .read_text()
        .split("model name", 1)[-1]
        .splitlines()[0]
        .strip(),
        "arms": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--partition", choices=tuple(DATASET_PINS), required=True)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--variant", type=Path)
    parser.add_argument("--static", action="store_true", help="Static encoder, rerank serving")
    parser.add_argument(
        "--arm", choices=("guarded", *STATIC_ARMS, *CPU_PROFILES), help=argparse.SUPPRESS
    )
    parser.add_argument("--prepare", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--groups", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--vectors", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error("Use 1 to 20 repetitions")
    if args.static and args.variant:
        parser.error("--static and --variant name different encoders")
    if args.prepare:
        args.groups.write_text(json.dumps(groups_for(args.data, args.partition)))
    else:
        print(json.dumps(measure(args) if args.arm else run(args)))


if __name__ == "__main__":
    main()
