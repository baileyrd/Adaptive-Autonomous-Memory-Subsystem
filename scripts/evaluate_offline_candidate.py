"""Score the fixed staged artifact on two independent held-out partitions."""

import argparse
import json
import resource
import statistics
import tempfile
from dataclasses import asdict
from pathlib import Path

from offline_experiment import (
    BASELINES,
    RISK_BUDGET,
    load_groups,
    measured_comparison,
    replay,
    summarize,
)
from train_offline_candidate import fit


def assess(rows):
    profiles = {name: summarize(rows, name) for name in (*BASELINES, "candidate")}
    lexical, guarded, candidate = (profiles[name] for name in ("lexical", "guarded", "candidate"))
    contradiction_regressions = sum(
        row["contradiction"]
        and row["measurements"]["lexical"]["satisfied"]
        and not row["measurements"]["candidate"]["satisfied"]
        for row in rows
    )
    losses = sum(
        row["measurements"]["lexical"]["satisfied"]
        and not row["measurements"]["candidate"]["satisfied"]
        for row in rows
    )
    comparison = measured_comparison(rows, "candidate")
    mean_latency = statistics.mean(
        statistics.median(row["measurements"]["candidate"]["latency_ms"]) for row in rows
    )
    limits = {
        "task_gain_over_lexical": candidate["satisfied"] > lexical["satisfied"],
        "no_task_loss_vs_guarded": candidate["satisfied"] >= guarded["satisfied"],
        "no_ndcg_loss_vs_lexical": candidate["ndcg_at_3"] >= lexical["ndcg_at_3"],
        "scope_and_time": candidate["scope_leaks"] == candidate["time_leaks"] == 0,
        "contradiction_retention": contradiction_regressions == 0,
        "risk_budget": mean_latency <= RISK_BUDGET.max_latency_ms
        and 1 - candidate["satisfied"] / len(rows) <= RISK_BUDGET.max_unsatisfied_fraction,
    }
    return {
        "profiles": profiles,
        "gates": limits,
        "passes_partition": all(limits.values()),
        "beats_guarded_on_tasks": candidate["satisfied"] > guarded["satisfied"],
        "lexical_counterexamples": losses,
        "contradiction_regressions": contradiction_regressions,
        "distinct_mode_pairs": asdict(comparison) if comparison else None,
        "mean_candidate_task_median_ms": round(mean_latency, 4),
    }


def calibration(rows, artifact):
    buckets: dict[float, list[bool]] = {}
    for row in rows:
        lexical, hybrid = (row["measurements"][name] for name in ("lexical", "hybrid"))
        if not row["features"]["opt_in"] or hybrid["mode"] != "hybrid":
            continue
        feature = row["features"]["short_query"]
        prediction = next(
            bucket.probability_of_gain for bucket in artifact.bins if bucket.short_query == feature
        )
        buckets.setdefault(prediction, []).append(hybrid["satisfied"] and not lexical["satisfied"])
    errors = [(prediction - won) ** 2 for prediction, wins in buckets.items() for won in wins]
    return {
        "paired_opt_in_tasks": len(errors),
        "brier_gain": round(statistics.mean(errors), 4) if errors else None,
        "reliability": [
            {
                "predicted_gain": prediction,
                "observed_gain": sum(wins) / len(wins),
                "count": len(wins),
            }
            for prediction, wins in sorted(buckets.items())
        ],
    }


def evaluate(repetitions):
    artifact = fit(repetitions)
    groups = load_groups()
    results, held = {}, []
    with tempfile.TemporaryDirectory(prefix="aams-offline-heldout-") as directory:
        for partition in ("test_a", "test_b"):
            selected = [group for group in groups if group["split"] == partition]
            normal = replay(
                Path(directory) / f"{partition}.db", selected, repetitions, artifact.suggests_hybrid
            )
            outage = replay(
                Path(directory) / f"{partition}-outage.db",
                selected,
                1,
                artifact.suggests_hybrid,
                candidate_outage=True,
            )
            held.extend(normal)
            result = assess(normal)
            result["outage"] = {
                "lexical_tasks": sum(
                    row["measurements"]["candidate"]["mode"] == "lexical" for row in outage
                ),
                "reported_provider_fallbacks": sum(
                    row["measurements"]["candidate"]["status"] == "provider_unavailable"
                    for row in outage
                ),
                "matches_lexical_quality": all(
                    all(
                        row["measurements"]["candidate"][metric]
                        == row["measurements"]["lexical"][metric]
                        for metric in ("satisfied", "ndcg", "recall", "scope_leaks", "time_leaks")
                    )
                    for row in outage
                ),
            }
            results[partition] = result
    return {
        "training_checksum": artifact.training_checksum,
        "partitions": results,
        "calibration": calibration(held, artifact),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "passes_fixture_research_gate": all(row["passes_partition"] for row in results.values()),
        "beats_guarded_across_partitions": all(
            row["beats_guarded_on_tasks"] for row in results.values()
        ),
        "runtime_activation": "disabled",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 100:
        parser.error("Use 1 to 100 repetitions")
    print(json.dumps(evaluate(args.repetitions), indent=2))


if __name__ == "__main__":
    main()
