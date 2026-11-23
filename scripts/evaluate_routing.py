"""Measure held-out lexical, hybrid, and host-routed recall on a fixed workload."""

import argparse
import json
import resource
import statistics
import tempfile
from math import ceil, log2
from pathlib import Path
from time import perf_counter_ns

from evaluate_semantic import K, SpacyTok2Vec, seed, timestamp

from aams.ranking import LexicalRanking
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.representations import DeterministicFixtureProvider
from aams.retrieval_routing import RetrievalMode
from aams.storage import AccessContext, SQLiteMemoryStore
from aams.vector_index import RepresentationIndex

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/retrieval_routing.json"


def ids(packet):
    return [edge["evidence_id"] for item in packet["items"] for edge in item["citations"]]


def ndcg(relevant, found):
    def gain(grades):
        return sum((2**grade - 1) / log2(rank + 2) for rank, grade in enumerate(grades))

    ideal = gain(sorted(relevant.values(), reverse=True)[:K])
    return gain([relevant.get(item, 0) for item in found]) / ideal if ideal else 0.0


def evaluate(path, strategy, encoder, repetitions):
    data = json.loads(FIXTURE.read_text())
    store = SQLiteMemoryStore(path)
    for row in data["records"]:
        seed(store, *row, origin=data["duplicate_origins"].get(row[0]))
    provider = None
    if strategy != "lexical":
        provider = SpacyTok2Vec() if encoder == "neural" else DeterministicFixtureProvider()
        for scope in ("lab", "archive", "private"):
            RepresentationIndex(store).rebuild(AccessContext("host", scope, True), provider)
    seed(store, *data["after_index"])
    scopes = {row[0]: row[1] for row in [*data["records"], data["after_index"]]}
    # Historical baselines keep the legacy ranker so published audits stay reproducible.
    memory = CognitiveMemory(store, lexical_ranking=LexicalRanking.OVERLAP)

    def request(case, selected):
        access = AccessContext("host", case["scope"])
        need = CognitiveNeed(
            query=case["text"],
            max_items=K,
            recorded_as_of=timestamp(case["day"]) if "day" in case else None,
        )
        if selected == "lexical":
            return memory.recall(access, need)
        available = provider if case.get("fallback") != "provider_unavailable" else None
        if selected == "hybrid" and available is not None:
            return memory.recall(access, need, provider=available)
        requested = RetrievalMode.HYBRID
        if selected == "routed" and not case["opt_in"]:
            requested = RetrievalMode.LEXICAL
        return memory.recall(access, need, provider=available, requested_mode=requested)

    queries = data["queries"]
    reference = [request(case, strategy) for case in queries]
    timings = []
    for _ in range(repetitions):
        for case, expected in zip(queries, reference, strict=True):
            start = perf_counter_ns()
            actual = request(case, strategy)
            timings.append((perf_counter_ns() - start) / 1e6)
            if actual != expected:
                raise RuntimeError("Non-reproducible result packet")

    recalls, grades, outcomes = [], [], []
    unsafe = regressed = hybrid_calls = scope_leaks = future_leaks = 0
    completed = tasks = contradictions = retained = 0
    for case, result in zip(queries, reference, strict=True):
        chosen = result.get("retrieval", {})
        actual = chosen.get("mode", "lexical")
        found = ids(result)
        relevant = case["relevant"]
        quality = ndcg(relevant, found)
        scope_leaks += sum(scopes[item] != case["scope"] for item in found)
        future_leaks += len(set(found) & set(case.get("future", [])))
        if relevant:
            recalls.append(len(set(found) & relevant.keys()) / len(relevant))
            grades.append(quality)
        if actual == "hybrid":
            hybrid_calls += 1
            unsafe += not case["opt_in"] or bool(case.get("fallback"))
            regressed += quality + 1e-12 < ndcg(relevant, ids(request(case, "lexical")))
        required = set(case["required"])
        if required:
            tasks += 1
            completed += required <= set(found)
        if case.get("contradiction"):
            contradictions += 1
            retained += required <= set(found)
        outcomes.append(
            {"query": case["text"], "mode": actual, "status": chosen.get("status"), "ids": found}
        )

    return {
        "strategy": strategy,
        "encoder": repr(provider.spec) if provider else None,
        "corpus_records": len(scopes),
        "timed_queries": len(timings),
        "recall_at_3": round(statistics.mean(recalls), 4),
        "ndcg_at_3": round(statistics.mean(grades), 4),
        "task_coverage": [completed, tasks],
        "contradictions": [retained, contradictions],
        "scope_leaks": scope_leaks,
        "future_leaks": future_leaks,
        "hybrid_queries": hybrid_calls,
        "false_hybrid_routes": unsafe,
        "regressed_hybrid_queries": regressed,
        "false_routing_rate": unsafe / len(queries),
        "median_ms": round(statistics.median(timings), 3),
        "p95_ms": round(sorted(timings)[ceil(0.95 * len(timings)) - 1], 3),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "outcomes": outcomes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("strategy", choices=("lexical", "hybrid", "routed"))
    parser.add_argument("--encoder", choices=("fixture", "neural"), default="fixture")
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("Use at least one repetition")
    with tempfile.TemporaryDirectory(prefix="aams-routing-") as directory:
        result = evaluate(
            Path(directory) / "memory.db", args.strategy, args.encoder, args.repetitions
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
