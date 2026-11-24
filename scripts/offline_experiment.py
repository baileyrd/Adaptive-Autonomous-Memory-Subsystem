"""Controlled synthetic replay. This CLI opens only a temporary database."""

import argparse
import json
import resource
import statistics
import sys
import tempfile
import unicodedata
from dataclasses import asdict
from functools import partial
from hashlib import sha256
from math import ceil, log2
from pathlib import Path
from time import perf_counter_ns, sleep

from evaluate_semantic import seed, timestamp
from fusion import (
    ONNX_ARMS,
    InvalidRun,
    check_validity,
    dense_arm,
    fusion_arm,
    open_encoder,
    rerank_arm,
    rrf_arm,
)

from aams.offline_policy import EvidenceBasis, OfflineOutcome, OfflineRiskBudget, OutcomeLabel
from aams.offline_policy import compare_controlled
from aams.ranking import LexicalRanking
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.representations import DeterministicFixtureProvider
from aams.retrieval_routing import ROUTING_POLICY_VERSION, RetrievalMode
from aams.shadow import ShadowConfig, ShadowMode
from aams.shadow_observer import ShadowObserver
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


def replay(
    path,
    groups,
    repetitions,
    candidate=None,
    *,
    candidate_outage=False,
    shadow_artifact=None,
    rankings=(),
    encoder=None,
    build_ms=None,
):
    """Replay every strategy per task. Each ranking adds lexical, hybrid and guarded arms.

    An ``encoder`` adds the eval-only ``bm25_guarded_onnx``, ``onnx``, ``rrf_onnx``,
    ``bm25_rerank`` and ``bm25_fusion`` arms
    beside the unchanged fixture-provider arms. Its per-scope index build times are appended
    to ``build_ms`` when given.
    """
    if encoder is not None and LexicalRanking.BM25 not in rankings:
        raise ValueError("ONNX arms compare against bm25_guarded; add the BM25 ranking")
    store = SQLiteMemoryStore(path)
    provider = DeterministicFixtureProvider()
    index = RepresentationIndex(store)
    # Historical baselines keep the legacy ranker so published audits stay reproducible.
    memory = CognitiveMemory(store, lexical_ranking=LexicalRanking.OVERLAP)
    ranked = {ranking: CognitiveMemory(store, lexical_ranking=ranking) for ranking in rankings}
    for group in groups:
        for identifier, scope, day, text, origin in group["records"]:
            seed(store, identifier, scope, day, text, origin=origin)
        index.rebuild(AccessContext("fixture", group["domain"], True), provider)
        if encoder is not None:
            start = perf_counter_ns()
            try:
                built = index.rebuild(AccessContext("fixture", group["domain"], True), encoder)
            except Exception as error:
                raise InvalidRun(f"ONNX index rebuild failed: {error}") from error
            if built.status != "fresh":
                raise InvalidRun(f"ONNX index rebuild returned {built.status}")
            if build_ms is not None:
                build_ms.append((perf_counter_ns() - start) / 1e6)

    measurements = []
    for group in groups:
        scope = group["domain"]
        access = AccessContext("fixture", scope, shadow_observe=shadow_artifact is not None)
        observer = observed_memory = None
        if shadow_artifact is not None:
            cap = len(group["tasks"]) * (repetitions + 1)
            observer = ShadowObserver(
                access, ShadowConfig(ShadowMode.OBSERVE_ONLY, cap), shadow_artifact
            )
            observed_memory = CognitiveMemory(
                store, shadow=observer, lexical_ranking=LexicalRanking.OVERLAP
            )
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
            if observed_memory is not None:
                modes["guarded_observed"] = task["opt_in"]
            if candidate is not None:
                modes["candidate"] = candidate(**features)
            engines = {"guarded_observed": observed_memory}
            for ranking in rankings:
                arms = {"": False, "_hybrid": True, "_guarded": task["opt_in"]}
                for suffix, hybrid in arms.items():
                    modes[ranking.value + suffix] = hybrid
                    engines[ranking.value + suffix] = ranked[ranking]
            calls = {}
            for strategy, hybrid in modes.items():
                mode = RetrievalMode.HYBRID if hybrid else RetrievalMode.LEXICAL
                available = hybrid and not (strategy == "candidate" and candidate_outage)
                kwargs = {"provider": provider if available else None, "requested_mode": mode}
                engine = engines.get(strategy) or memory
                calls[strategy] = partial(engine.recall, access, need, **kwargs)
            if encoder is not None:
                bm25 = ranked[LexicalRanking.BM25]
                mode = RetrievalMode.HYBRID if task["opt_in"] else RetrievalMode.LEXICAL
                calls["bm25_guarded_onnx"] = partial(
                    bm25.recall,
                    access,
                    need,
                    provider=encoder if task["opt_in"] else None,
                    requested_mode=mode,
                )
                calls["onnx"] = partial(dense_arm, bm25, encoder, access, need, TOP_K)
                calls["rrf_onnx"] = partial(rrf_arm, bm25, encoder, access, need, TOP_K)
                calls["bm25_rerank"] = partial(rerank_arm, bm25, encoder, access, need, TOP_K)
                calls["bm25_fusion"] = partial(fusion_arm, bm25, encoder, access, need, TOP_K)
            for strategy, call in calls.items():
                first_call = len(encoder.encode_ns) if encoder is not None else 0
                expected = call()
                timed_from = len(encoder.encode_ns) if encoder is not None else 0
                latency = []
                for _ in range(repetitions):
                    start = perf_counter_ns()
                    packet = call()
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
                    "status": expected["retrieval"]["status"],
                    "packet_digest": opaque(json.dumps(expected, sort_keys=True)),
                    "visible": bool(expected["items"]),
                    "satisfied": set(task["required"]) <= set(found),
                    "recall": len(set(found) & relevant) / len(relevant),
                    "ndcg": gain / ideal,
                    "scope_leaks": sum(name not in visible for name in found),
                    "time_leaks": sum(visible.get(name, 0) > task["day"] for name in found),
                    "latency_ms": latency,
                }
                if strategy in ONNX_ARMS:
                    measured = row["measurements"][strategy]
                    measured["encoder_calls"] = timed_from - first_call
                    measured["encode_ms"] = [ns / 1e6 for ns in encoder.encode_ns[timed_from:]]
                    if "cosines" in expected:
                        tops = {True: None, False: None}
                        for source, score in expected["cosines"]:
                            key = source in relevant
                            tops[key] = score if tops[key] is None else tops[key]
                        measured["top_cosine"] = {"relevant": tops[True], "other": tops[False]}
            measurements.append(row)
        if observer is not None:
            sleep(0.03)  # Offline accounting, outside serving timing.
            observations = observer.observations(access)
            measurements[-1]["observer"] = {
                "completed": len(observations),
                "failed": sum(not observation.success for observation in observations),
            }
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


def contradictions(rows, baseline="bm25_guarded"):
    """Contradiction tasks each arm satisfies, and regressions against ``baseline``."""
    tasks = [row for row in rows if row["contradiction"]]
    report = {
        strategy: {"retained": sum(row["measurements"][strategy]["satisfied"] for row in tasks)}
        for strategy in rows[0]["measurements"]
    }
    if baseline in report:
        for strategy, counts in report.items():
            counts["regressions"] = sum(
                row["measurements"][baseline]["satisfied"]
                and not row["measurements"][strategy]["satisfied"]
                for row in tasks
            )
    return {"tasks": len(tasks), "arms": report}


def split_result(groups, repetitions, rankings, encoder):
    with tempfile.TemporaryDirectory(prefix="aams-offline-") as directory:
        rows = replay(
            Path(directory) / "fixture.sqlite3",
            groups,
            repetitions,
            rankings=rankings,
            encoder=encoder,
        )
    strategies = BASELINES + tuple(s for s in rows[0]["measurements"] if s not in BASELINES)
    result = {strategy: summarize(rows, strategy) for strategy in strategies}
    comparison = measured_comparison(rows, "guarded")
    result["guarded_distinct_mode_pairs"] = asdict(comparison) if comparison else None
    if rankings:
        result["contradictions"] = contradictions(rows)
    if encoder is not None:
        result["invalid"] = check_validity(rows)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=(*SPLITS, "all"), default="test_a")
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--ranking", action="append", default=[], choices=["bm25"])
    parser.add_argument("--encoder-dir", type=Path, help="Pinned ONNX encoder (adds ONNX arms)")
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 100:
        parser.error("Use 1 to 100 repetitions")
    rankings = tuple(LexicalRanking(value) for value in dict.fromkeys(args.ranking))
    if args.encoder_dir is not None and LexicalRanking.BM25 not in rankings:
        parser.error("--encoder-dir requires --ranking bm25")
    splits = SPLITS if args.split == "all" else (args.split,)
    groups = load_groups()
    encoder = None
    try:
        if args.encoder_dir is not None:
            encoder = open_encoder(args.encoder_dir)
        results = {
            split: split_result(
                [group for group in groups if group["split"] == split],
                args.repetitions,
                rankings,
                encoder,
            )
            for split in splits
        }
    except InvalidRun as error:
        print(json.dumps({"valid": False, "reason": str(error)}))
        sys.exit(3)
    result = results[args.split] if args.split != "all" else {"splits": results}
    result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result["observational_counterfactual"] = "NOT ESTABLISHED"
    if encoder is not None:
        problems = [p for split in results.values() for p in split["invalid"]]
        result["valid"] = not problems
    print(json.dumps(result, indent=2))
    if encoder is not None and not result["valid"]:
        sys.exit(3)


if __name__ == "__main__":
    main()
