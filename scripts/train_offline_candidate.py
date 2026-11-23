"""Export an inert policy artifact from the checked-in training partition."""

import argparse
import json
import statistics
import tempfile
from dataclasses import asdict
from pathlib import Path

from offline_experiment import load_groups, replay

from aams.offline_candidate import TrainingPair, train_candidate
from aams.offline_policy import EvidenceBasis, OfflineOutcome, OutcomeLabel
from aams.retrieval_routing import ROUTING_POLICY_VERSION, RetrievalMode


def pairs_from_rows(rows):
    pairs = []
    for row in rows:
        observations = []
        for key in ("lexical", "hybrid"):
            item = row["measurements"][key]
            observations.append(
                OfflineOutcome(
                    row["task"],
                    row["group"],
                    RetrievalMode(item["mode"]),
                    OutcomeLabel.SATISFIED if item["satisfied"] else OutcomeLabel.UNSATISFIED,
                    float(statistics.median(item["latency_ms"])),
                    ROUTING_POLICY_VERSION,
                    EvidenceBasis.CONTROLLED_REPLAY,
                )
            )
        if observations[1].mode is RetrievalMode.HYBRID:
            pairs.append(
                TrainingPair(
                    row["features"]["short_query"], row["features"]["opt_in"], *observations
                )
            )
    return tuple(pairs)


def fit(repetitions):
    groups = [group for group in load_groups() if group["split"] == "train"]
    with tempfile.TemporaryDirectory(prefix="aams-offline-train-") as directory:
        rows = replay(Path(directory) / "train.sqlite3", groups, repetitions)
    return train_candidate(pairs_from_rows(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 100:
        parser.error("Use 1 to 100 repetitions")
    print(json.dumps({"disposition": "staged", **asdict(fit(args.repetitions))}, indent=2))


if __name__ == "__main__":
    main()
