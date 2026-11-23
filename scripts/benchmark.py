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


def measure(path, records, samples, warmup, scope_count, belief_count):
    store = SQLiteMemoryStore(path)
    memory = CognitiveMemory(store)
    scopes = [AccessContext("fixture", f"domain-{number}", True) for number in range(scope_count)]
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
    for index in range(belief_count):
        scope = scopes[index % scope_count]
        support = f"e{index % scope_count}"
        refute = f"e{index % scope_count + scope_count}"
        identifier = f"weather-{index}"
        first = store.revise(
            scope,
            identifier,
            None,
            BeliefProposal(
                "Rain expected", EpistemicState.INFERRED, "Fixture", TIME, support_ids=(support,)
            ),
        )
        store.revise(
            scope,
            identifier,
            first.revision_id,
            BeliefProposal(
                "Rain contested",
                EpistemicState.CONTESTED,
                "Conflicting sample",
                TIME,
                support_ids=(support,),
                refute_ids=(refute,),
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
            "scopes": scope_count,
            "belief_revisions": 2 * belief_count,
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
    parser.add_argument("--scopes", type=int, default=4)
    parser.add_argument("--beliefs", type=int, default=1)
    args = parser.parse_args()
    if args.records < 8 or args.samples < 1 or args.warmup < 1:
        parser.error("Use at least eight records, one sample and one warmup")
    if args.scopes < 1 or args.beliefs < 0 or args.records + args.warmup < 2 * args.scopes:
        parser.error("Use positive scopes and at least two formations per scope")
    with tempfile.TemporaryDirectory(prefix="aams-bench-") as directory:
        result = measure(
            Path(directory) / "bench.sqlite3",
            args.records,
            args.samples,
            args.warmup,
            args.scopes,
            args.beliefs,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
