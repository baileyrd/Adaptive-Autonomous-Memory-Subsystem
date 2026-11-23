"""Measure AAMS native ingest and recall on a repeatable synthetic corpus."""

import argparse
import json
import math
import platform
import random
import sqlite3
import statistics
import tempfile
import tracemalloc
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from time import perf_counter_ns

from aams.contracts import (
    BeliefProposal,
    EpistemicState,
    Evidence,
    EvidenceStatus,
    MemoryFormation,
    MemoryKind,
)
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.storage import AccessContext, SQLiteMemoryStore

TIME = "2026-01-01T00:00:00Z"
SEED = 1081


def summary(samples):
    ordered = sorted(samples)
    return {
        "median_ms": round(statistics.median(ordered) / 1e6, 3),
        "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1] / 1e6, 3),
    }


def measure(path, records, samples, warmup):
    store = SQLiteMemoryStore(path)
    memory = CognitiveMemory(store)
    scopes = [AccessContext("fixture", f"domain-{number}", True) for number in range(4)]
    rng = random.Random(SEED)
    observations = ("rain storm", "heavy rain", "overdue calibration", "clear weather")
    ingests = []
    for index in range(records + warmup):
        scope = scopes[index % len(scopes)]
        text = rng.choice(observations).encode()
        digest = "sha256:" + sha256(text).hexdigest()
        evidence = Evidence(
            f"e{index}",
            scope.scope,
            "station",
            f"fixture:{index}",
            scope.principal,
            TIME,
            TIME,
            EvidenceStatus.RECORDED,
            text,
            digest,
        )
        formation = MemoryFormation(
            f"f{index}",
            scope.scope,
            MemoryKind.EXPERIENCE,
            (evidence.evidence_id,),
            scope.principal,
            TIME,
            EpistemicState.OBSERVED,
        )
        start = perf_counter_ns()
        store.ingest(scope, f"request-{index}", formation, (evidence,))
        if index >= warmup:
            ingests.append(perf_counter_ns() - start)
    access = scopes[0]
    first = store.revise(
        access,
        "weather",
        None,
        BeliefProposal(
            "Rain expected", EpistemicState.INFERRED, "Fixture", TIME, support_ids=("e0",)
        ),
    )
    store.revise(
        access,
        "weather",
        first.revision_id,
        BeliefProposal(
            "Rain contested",
            EpistemicState.CONTESTED,
            "Conflicting sample",
            TIME,
            support_ids=("e0",),
            refute_ids=("e4",),
        ),
    )
    exact = CognitiveNeed(entity="formation", identifier="f0")
    ranked = CognitiveNeed(query="rain storm", max_items=5)
    stats = {}
    for name, need in (("exact", exact), ("contextual", ranked)):
        timings = []
        for index in range(samples + warmup):
            start = perf_counter_ns()
            result = memory.recall(access, need)
            if index >= warmup:
                timings.append(perf_counter_ns() - start)
        if not result["items"]:
            raise RuntimeError("Fixture returned no results")
        stats[name] = summary(timings)
    tracemalloc.start()
    memory.recall(access, ranked)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "mcp_sdk": version("mcp"),
        },
        "fixture": {
            "seed": SEED,
            "formations": records + warmup,
            "scopes": 4,
            "belief_revisions": 2,
        },
        "samples": {"ingest": records, "each_recall": samples, "warmup": warmup},
        "ingest": {
            **summary(ingests),
            "records_per_second": round(records * 1e9 / sum(ingests), 1),
        },
        **stats,
        "sqlite_bytes": path.stat().st_size,
        "contextual_peak_traced_python_bytes": peak,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=256)
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--warmup", type=int, default=8)
    args = parser.parse_args()
    if args.records < 8 or args.samples < 1 or args.warmup < 1:
        parser.error("Use at least eight records, one sample and one warmup")
    with tempfile.TemporaryDirectory(prefix="aams-bench-") as directory:
        result = measure(Path(directory) / "bench.sqlite3", args.records, args.samples, args.warmup)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
