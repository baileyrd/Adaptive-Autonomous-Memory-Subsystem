"""Replay guarded recall and a staged shadow rule on authorized public or synthetic data."""

import argparse
import json
import resource
import statistics
import tempfile
from hashlib import sha256
from pathlib import Path
from random import Random

from evaluate_semantic import timestamp
from offline_experiment import load_groups, replay, summarize
from train_offline_candidate import fit

from aams.offline_policy import EvidenceBasis, OfflineOutcome, OutcomeLabel
from aams.retrieval_routing import ROUTING_POLICY_VERSION, RetrievalMode
from aams.shadow_pairs import PairStatus, ShadowArm, ShadowPair, ShadowPairLedger
from aams.storage import AccessContext

SQUAD_SHA256 = "95aa6a52d5d6a735563366753ca50492a658031da74f301ac5238b03966972c9"
PUBLIC_TOPICS = ("Apollo_program", "Oxygen", "Packet_switching", "Warsaw")


def public_groups(path):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != SQUAD_SHA256:
        raise ValueError("Expected exact SQuAD v1.1 public dev dataset")
    data = {article["title"]: article for article in json.loads(raw)["data"]}
    groups = []
    for index, topic in enumerate(PUBLIC_TOPICS):
        scope, day = f"public-{index}", 15 + index * 2
        records, tasks = [], []
        for ordinal, paragraph in enumerate(data[topic]["paragraphs"][:3]):
            source = f"q{index}-{ordinal}"
            records.append([source, scope, day, paragraph["context"], source])
            for question in paragraph["qas"][:2]:
                tasks.append(
                    {
                        "query": question["question"],
                        "day": day,
                        "opt_in": True,
                        "relevant": [source],
                        "required": [source],
                        "contradiction": False,
                    }
                )
        records.extend(
            [
                [f"other-{index}", f"private-{scope}", day, tasks[0]["query"], f"other-{index}"],
                [f"future-{index}", scope, day + 1, tasks[0]["query"], f"future-{index}"],
            ]
        )
        groups.append(
            {
                "domain": scope,
                "split": "public",
                "days": [day, day + 1],
                "records": records,
                "tasks": tasks,
            }
        )
    return groups


def pair_task(row, group, task):
    scope = group["domain"]
    cutoff = timestamp(task["day"])

    def arm(key):
        item = row["measurements"][key]
        return ShadowArm(
            cutoff,
            OfflineOutcome(
                row["task"],
                row["group"],
                RetrievalMode(item["mode"]),
                OutcomeLabel.SATISFIED if item["satisfied"] else OutcomeLabel.UNSATISFIED,
                float(statistics.median(item["latency_ms"])),
                ROUTING_POLICY_VERSION,
                EvidenceBasis.CONTROLLED_REPLAY,
            ),
        )

    access = AccessContext("fixture", scope, shadow_observe=True)
    return ShadowPair(
        row["task"],
        row["group"],
        timestamp(min(group["days"])),
        timestamp(max(group["days"]) + 1),
        arm("guarded"),
        arm("candidate"),
    ), access


def interval(group_deltas):
    rng = Random(202607)
    bootstrap = sorted(
        statistics.mean(rng.choices(group_deltas, k=len(group_deltas))) for _ in range(2000)
    )
    return [round(bootstrap[49], 4), round(bootstrap[1949], 4)]


def evaluate(path, groups, artifact, repetitions):
    rows = replay(path, groups, repetitions, artifact.suggests_hybrid, shadow_artifact=artifact)
    profiles = {key: summarize(rows, key) for key in ("guarded", "guarded_observed", "candidate")}
    reports, deltas, alternate = [], [], []
    start = 0
    for group in groups:
        end = start + len(group["tasks"])
        grouped = rows[start:end]
        start = end
        group_deltas = []
        ledger = None
        for row, task in zip(grouped, group["tasks"], strict=True):
            pair, access = pair_task(row, group, task)
            if ledger is None:
                ledger = ShadowPairLedger(access, limit=len(grouped))
            ledger.record(access, pair)
            before = pair.serving.outcome.label is OutcomeLabel.SATISFIED
            after = pair.shadow.outcome.label is OutcomeLabel.SATISFIED
            delta = int(after) - int(before)
            group_deltas.append(delta)
            if pair.status is PairStatus.CONTROLLED_ALTERNATE:
                alternate.append(delta)
        deltas.append(statistics.mean(group_deltas))
        reports.extend(group_deltas)
    overrun = profiles["guarded_observed"]["p95_ms"] - profiles["guarded"]["p95_ms"]
    totals = [row["observer"] for row in rows if "observer" in row]
    completed = sum(row["completed"] for row in totals)
    failures = sum(row["failed"] for row in totals)
    offered = (repetitions + 1) * sum(row["measurements"]["guarded"]["visible"] for row in rows)
    eligible = [row for row in rows if row["features"]["opt_in"]]
    drift = sum(row["features"]["short_query"] for row in eligible) / len(eligible)
    reliability = {}
    for row in eligible:
        before, after = (row["measurements"][name] for name in ("lexical", "hybrid"))
        if after["mode"] != "hybrid":
            continue
        probability = next(
            bucket.probability_of_gain
            for bucket in artifact.bins
            if bucket.short_query == row["features"]["short_query"]
        )
        reliability.setdefault(probability, []).append(
            after["satisfied"] and not before["satisfied"]
        )
    calibration = [
        {"predicted": chance, "observed": sum(labels) / len(labels), "count": len(labels)}
        for chance, labels in sorted(reliability.items())
    ]
    disparity = [
        (chance - actual) ** 2 for chance, labels in reliability.items() for actual in labels
    ]
    bounds = interval(deltas)
    invariance = all(
        row["measurements"]["guarded"]["packet_digest"]
        == row["measurements"]["guarded_observed"]["packet_digest"]
        for row in rows
    )
    zero_leaks = all(
        profile["scope_leaks"] == profile["time_leaks"] == 0 for profile in profiles.values()
    )
    return {
        "profiles": profiles,
        "groups": len(groups),
        "task_pairs": len(rows),
        "alternate_pairs": len(alternate),
        "mean_paired_utility_delta": statistics.mean(reports),
        "mean_group_delta_95_percent_bootstrap": bounds,
        "paired_losses": reports.count(-1),
        "contradiction_regressions": sum(
            row["contradiction"] and delta < 0 for row, delta in zip(rows, reports, strict=True)
        ),
        "serving_packets_identical": invariance,
        "zero_observed_leaks": zero_leaks,
        "p95_serving_overhead_ms": round(overrun, 3),
        "shadow_completion": {
            "offered": offered,
            "completed": completed,
            "failed": failures,
            "skipped_or_pending": offered - completed,
        },
        "opted_in_short_query_fraction": drift,
        "calibration": calibration,
        "gain_brier": round(statistics.mean(disparity), 4) if disparity else None,
        "meaningful_improvement": statistics.mean(reports) >= 0.05 and bounds[0] > 0,
        "operational_fixture_budget": invariance
        and zero_leaks
        and overrun <= 5.0
        and bool(completed)
        and failures / completed <= 0.10,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--squad", type=Path)
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 40:
        parser.error("Use 1 to 40 repetitions")
    artifact = fit(args.repetitions)
    groups = (
        public_groups(args.squad)
        if args.squad
        else [g for g in load_groups() if g["split"] != "train"]
    )
    with tempfile.TemporaryDirectory(prefix="aams-shadow-replay-") as directory:
        result = evaluate(Path(directory) / "test.db", groups, artifact, args.repetitions)
    result["workload"] = "public_squad_v1.1" if args.squad else "synthetic_held_out"
    result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
