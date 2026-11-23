"""Article-grouped retrieval benchmark with oracle and uncertainty diagnostics (v0.8 I1).

Every SQuAD v1.1 development article becomes one scope, so all paragraphs compete. A
deterministic article hash assigns each scope to the `design` or `heldout` partition.
Quality is deterministic; timing uses one warmup and `--repetitions` timed calls.
Only temporary SQLite state is used.
"""

import argparse
import json
import resource
import statistics
import tempfile
from hashlib import sha256
from pathlib import Path
from random import Random

from offline_experiment import replay, summarize
from train_offline_candidate import fit

from aams.ranking import LexicalRanking

SQUAD_SHA256 = "95aa6a52d5d6a735563366753ca50492a658031da74f301ac5238b03966972c9"
PREVIEW_BYTES = 512  # Mirrors aams.recall._PREVIEW_BYTES, the lexically matched window.
SPLITS = ("design", "heldout")
DAY = 15


def article_split(title: str) -> str:
    """Stable, content-independent partition so no article informs both splits."""
    return SPLITS[int(sha256(title.encode()).hexdigest(), 16) % 2]


def squad_groups(data: dict, per_paragraph: int) -> tuple[list[dict], list[dict]]:
    """Return replay groups and aligned per-task diagnostics."""
    groups, details = [], []
    for index, article in enumerate(data["data"]):
        scope, records, tasks = f"article-{index}", [], []
        for ordinal, paragraph in enumerate(article["paragraphs"]):
            source = f"a{index}p{ordinal}"
            context = paragraph["context"]
            records.append([source, scope, DAY, context, source])
            for question in paragraph["qas"][:per_paragraph]:
                answer = question["answers"][0]
                offset = len(context[: answer["answer_start"]].encode())
                tasks.append(
                    {
                        "query": question["question"],
                        "day": DAY,
                        "opt_in": True,
                        "relevant": [source],
                        "required": [source],
                        "contradiction": False,
                    }
                )
                details.append(
                    {
                        "article": scope,
                        "split": article_split(article["title"]),
                        "answer_beyond_preview": offset >= PREVIEW_BYTES,
                    }
                )
        if not tasks:
            continue
        decoy = tasks[0]["query"]
        records.extend(
            [
                [f"private-{index}", f"private-{scope}", DAY, decoy, f"private-{index}"],
                [f"future-{index}", scope, DAY + 1, decoy, f"future-{index}"],
            ]
        )
        groups.append(
            {
                "domain": scope,
                "split": article_split(article["title"]),
                "days": [DAY, DAY + 1],
                "records": records,
                "tasks": tasks,
            }
        )
    return groups, details


def grouped_interval(deltas_by_group: dict[str, list[int]], seed: int = 202607) -> list[float]:
    """Percentile 95% interval of the task-weighted mean delta, resampling whole groups."""
    groups = sorted(deltas_by_group.values())
    if not groups:
        raise ValueError("Expected at least one group")
    rng = Random(seed)
    means = []
    for _ in range(2000):
        sample = rng.choices(groups, k=len(groups))
        means.append(sum(map(sum, sample)) / sum(map(len, sample)))
    means.sort()
    return [round(means[49], 4), round(means[1949], 4)]


def paired(rows: list[dict], details: list[dict], strategy: str, baseline: str) -> dict:
    """Paired task-satisfaction comparison with an article-grouped bootstrap interval."""
    by_group: dict[str, list[int]] = {}
    for row, detail in zip(rows, details, strict=True):
        after = row["measurements"][strategy]["satisfied"]
        before = row["measurements"][baseline]["satisfied"]
        by_group.setdefault(detail["article"], []).append(int(after) - int(before))
    flat = [delta for group in by_group.values() for delta in group]
    return {
        "wins": flat.count(1),
        "losses": flat.count(-1),
        "ties": flat.count(0),
        "mean_delta": round(statistics.mean(flat), 4),
        "ci95": grouped_interval(by_group),
    }


def oracle(rows: list[dict], keys: tuple[str, str] = ("lexical", "hybrid")) -> dict:
    """Best of two arms per task: the ceiling for any router choosing between them."""
    arms = [[row["measurements"][key] for key in keys] for row in rows]
    return {
        "satisfied": sum(any(arm["satisfied"] for arm in pair) for pair in arms),
        "ndcg_at_3": round(statistics.mean(max(arm["ndcg"] for arm in pair) for pair in arms), 4),
    }


def split_report(rows: list[dict], details: list[dict]) -> dict:
    strategies = tuple(rows[0]["measurements"])
    report = {
        "tasks": len(rows),
        "articles": len({detail["article"] for detail in details}),
        "profiles": {key: summarize(rows, key) for key in strategies},
        "oracle_router": oracle(rows),
        "versus_guarded": {
            key: paired(rows, details, key, "guarded") for key in strategies if key != "guarded"
        },
        "short_query_fraction": round(
            statistics.mean(row["features"]["short_query"] for row in rows), 4
        ),
    }
    report["oracle_router"]["versus_guarded"] = round(
        (report["oracle_router"]["satisfied"] - report["profiles"]["guarded"]["satisfied"])
        / len(rows),
        4,
    )
    for ranking in (key for key in strategies if f"{key}_hybrid" in strategies):
        report[f"oracle_{ranking}_router"] = oracle(rows, (ranking, f"{ranking}_hybrid"))
    lexical = [row["measurements"]["lexical"] for row in rows]
    hybrid = [row["measurements"]["hybrid"] for row in rows]
    report["hybrid_vs_lexical_ndcg"] = {
        "better": sum(h["ndcg"] > x["ndcg"] for x, h in zip(lexical, hybrid, strict=True)),
        "worse": sum(h["ndcg"] < x["ndcg"] for x, h in zip(lexical, hybrid, strict=True)),
    }
    report["lexical_by_answer_position"] = {
        label: round(statistics.mean(item["satisfied"] for item in subset), 4) if subset else None
        for label, subset in (
            (
                "within_preview",
                [
                    x
                    for x, d in zip(lexical, details, strict=True)
                    if not d["answer_beyond_preview"]
                ],
            ),
            (
                "beyond_preview",
                [x for x, d in zip(lexical, details, strict=True) if d["answer_beyond_preview"]],
            ),
        )
    }
    return report


def evaluate(
    data: dict, per_paragraph: int, repetitions: int, rankings: tuple[LexicalRanking, ...] = ()
) -> dict:
    groups, details = squad_groups(data, per_paragraph)
    staged = fit(1)
    records = [row for group in groups for row in group["records"] if row[1] == group["domain"]]
    with tempfile.TemporaryDirectory(prefix="aams-retrieval-") as directory:
        rows = replay(
            Path(directory) / "bench.db",
            groups,
            repetitions,
            staged.suggests_hybrid,
            rankings=rankings,
        )
    for row in rows:
        row["measurements"]["staged"] = row["measurements"].pop("candidate")
    result = {
        "records_beyond_preview": round(
            statistics.mean(len(row[3].encode()) > PREVIEW_BYTES for row in records), 4
        ),
        "staged_training_checksum": staged.training_checksum,
    }
    for split in SPLITS:
        chosen = [i for i, detail in enumerate(details) if detail["split"] == split]
        if chosen:
            result[split] = split_report([rows[i] for i in chosen], [details[i] for i in chosen])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--squad", type=Path, required=True)
    parser.add_argument("--expected-sha256", default=SQUAD_SHA256)
    parser.add_argument("--questions-per-paragraph", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--max-articles", type=int, help="Use only the first N articles")
    parser.add_argument(
        "--ranking",
        action="append",
        default=[],
        choices=[
            ranking.value for ranking in LexicalRanking if ranking is not LexicalRanking.OVERLAP
        ],
        help="Add a candidate lexical ranking arm and its hybrid variant",
    )
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20 or not 1 <= args.questions_per_paragraph <= 10:
        parser.error("Use 1 to 20 repetitions and 1 to 10 questions per paragraph")
    if args.max_articles is not None and args.max_articles < 1:
        parser.error("Use at least one article")
    raw = args.squad.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != args.expected_sha256:
        parser.error("Dataset checksum mismatch")
    data = json.loads(raw)
    data["data"] = data["data"][: args.max_articles]
    result = {
        "workload": "squad_v1.1_article_grouped",
        "dataset_sha256": digest,
        "articles": len(data["data"]),
        "questions_per_paragraph": args.questions_per_paragraph,
        "repetitions": args.repetitions,
        **evaluate(
            data,
            args.questions_per_paragraph,
            args.repetitions,
            tuple(LexicalRanking(value) for value in dict.fromkeys(args.ranking)),
        ),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
