"""Controlled synthetic replay. This CLI opens only a temporary database."""

import argparse
import json
import resource
import statistics
import tempfile
import unicodedata
from dataclasses import asdict
from hashlib import sha256
from math import ceil, log2
from pathlib import Path
from time import perf_counter_ns

from evaluate_semantic import seed, timestamp

from aams.offline_policy import EvidenceBasis, OfflineOutcome, OfflineRiskBudget, OutcomeLabel
from aams.offline_policy import compare_controlled
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.representations import DeterministicFixtureProvider
from aams.retrieval_routing import ROUTING_POLICY_VERSION, RetrievalMode
from aams.storage import AccessContext, SQLiteMemoryStore
from aams.vector_index import RepresentationIndex

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/offline_policy_v06.json"
SPLITS = ("train", "test_a", "test_b")
BASELINES = ("lexical", "hybrid", "guarded")
RISK_BUDGET = OfflineRiskBudget(15.0, 0.5)
TOP_K = 3


def opaque(value):
    return sha256(value.encode()).hexdigest()[:32]


def load_groups(path=FIXTURE):
    groups = json.loads(path.read_text())["groups"]
    domains, days, origins, identifiers, payloads = set(), set(), set(), set(), set()
    for group in groups:
        domain = group["domain"]
        period = set(group["days"])
        if group["split"] not in SPLITS or domain in domains or days & period:
            raise ValueError("Groups must have disjoint domains and time windows")
        group_origins = {row[4] for row in group["records"]}
        group_ids = {row[0] for row in group["records"]}
        texts = {
            " ".join(unicodedata.normalize("NFKC", row[3]).casefold().split())
            for row in group["records"]
        }
        if origins & group_origins or identifiers & group_ids or payloads & texts:
            raise ValueError("Independent groups cannot share sources, IDs or normalized copies")
        allowed = {row[0]: row[2] for row in group["records"] if row[1] == domain}
        for task in group["tasks"]:
            expected = set(task["relevant"]) | set(task["required"])
            if task["day"] not in period or any(
                i not in allowed or allowed[i] > task["day"] for i in expected
            ):
                raise ValueError("Task labels include unavailable fixture evidence")
        if not all(row[2] in period for row in group["records"]):
            raise ValueError("Evidence falls outside its group's date window")
        domains.add(domain)
        days.update(period)
        origins.update(group_origins)
        identifiers.update(group_ids)
        payloads.update(texts)
    if {group["split"] for group in groups} != set(SPLITS):
        raise ValueError("Expected training and two held-out partitions")
    return groups


def replay(path, groups, repetitions, candidate=None):
    store = SQLiteMemoryStore(path)
    provider = DeterministicFixtureProvider()
    index = RepresentationIndex(store)
    memory = CognitiveMemory(store)
    for group in groups:
        for identifier, scope, day, text, origin in group["records"]:
            seed(store, identifier, scope, day, text, origin=origin)
        index.rebuild(AccessContext("fixture", group["domain"], True), provider)

    measurements = []
    for group in groups:
        scope = group["domain"]
        access = AccessContext("fixture", scope)
        visible = {row[0]: row[2] for row in group["records"] if row[1] == scope}
        for ordinal, task in enumerate(group["tasks"]):
            need = CognitiveNeed(
                query=task["query"], max_items=TOP_K, recorded_as_of=timestamp(task["day"])
            )
            features = {"short_query": len(task["query"].split()) <= 4, "opt_in": task["opt_in"]}
            row = {
                "group": opaque(scope),
                "task": opaque(f"{scope}/{ordinal}"),
                "split": group["split"],
                "features": features,
                "contradiction": task["contradiction"],
                "measurements": {},
            }
            modes = {"lexical": False, "hybrid": True, "guarded": task["opt_in"]}
            if candidate is not None:
                modes["candidate"] = candidate(features)
            for strategy, hybrid in modes.items():
                mode = RetrievalMode.HYBRID if hybrid else RetrievalMode.LEXICAL
                kwargs = {"provider": provider if hybrid else None, "requested_mode": mode}
                expected = memory.recall(access, need, **kwargs)
                latency = []
                for _ in range(repetitions):
                    start = perf_counter_ns()
                    packet = memory.recall(access, need, **kwargs)
                    latency.append((perf_counter_ns() - start) / 1e6)
                    if packet != expected:
                        raise RuntimeError("Controlled replay changed result")
                found = [
                    edge["evidence_id"] for item in expected["items"] for edge in item["citations"]
                ]
                relevant = set(task["relevant"])
                ideal = sum(1 / log2(rank + 2) for rank in range(min(TOP_K, len(relevant))))
                gain = sum(
                    1 / log2(rank + 2) for rank, name in enumerate(found) if name in relevant
                )
                row["measurements"][strategy] = {
                    "mode": expected["retrieval"]["mode"],
                    "satisfied": set(task["required"]) <= set(found),
                    "recall": len(set(found) & relevant) / len(relevant),
                    "ndcg": gain / ideal,
                    "scope_leaks": sum(name not in visible for name in found),
                    "time_leaks": sum(visible.get(name, 0) > task["day"] for name in found),
                    "latency_ms": latency,
                }
            measurements.append(row)
    return measurements


def summarize(rows, strategy):
    measured = [row["measurements"][strategy] for row in rows]
    times = sorted(value for item in measured for value in item["latency_ms"])
    return {
        "tasks": len(rows),
        "satisfied": sum(item["satisfied"] for item in measured),
        "recall_at_3": round(statistics.mean(item["recall"] for item in measured), 4),
        "ndcg_at_3": round(statistics.mean(item["ndcg"] for item in measured), 4),
        "scope_leaks": sum(item["scope_leaks"] for item in measured),
        "time_leaks": sum(item["time_leaks"] for item in measured),
        "median_ms": round(statistics.median(times), 3),
        "p95_ms": round(times[ceil(0.95 * len(times)) - 1], 3),
    }


def measured_comparison(rows, strategy):
    before, after = [], []
    for row in rows:
        pair = [row["measurements"][key] for key in ("lexical", strategy)]
        if pair[0]["mode"] == pair[1]["mode"]:
            continue
        for result, output in zip(pair, (before, after), strict=True):
            output.append(
                OfflineOutcome(
                    row["task"],
                    row["group"],
                    RetrievalMode(result["mode"]),
                    OutcomeLabel.SATISFIED if result["satisfied"] else OutcomeLabel.UNSATISFIED,
                    float(statistics.median(result["latency_ms"])),
                    ROUTING_POLICY_VERSION,
                    EvidenceBasis.CONTROLLED_REPLAY,
                )
            )
    return compare_controlled(tuple(before), tuple(after), RISK_BUDGET) if before else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=SPLITS, default="test_a")
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 100:
        parser.error("Use 1 to 100 repetitions")
    groups = [group for group in load_groups() if group["split"] == args.split]
    with tempfile.TemporaryDirectory(prefix="aams-offline-") as directory:
        rows = replay(Path(directory) / "fixture.sqlite3", groups, args.repetitions)
    result = {strategy: summarize(rows, strategy) for strategy in BASELINES}
    comparison = measured_comparison(rows, "guarded")
    result["guarded_distinct_mode_pairs"] = asdict(comparison) if comparison else None
    result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result["observational_counterfactual"] = "NOT ESTABLISHED"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
