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
import sys
import tempfile
from hashlib import sha256
from math import ceil
from pathlib import Path
from random import Random

from fusion import ONNX_ARMS, InvalidRun, check_validity
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


def versus_baseline(rows: list[dict], details: list[dict], key: str, profiles: dict) -> dict:
    """The pre-registered gate block: paired task delta, nDCG delta and added p95 (D5)."""
    base = profiles["bm25_guarded"]
    return {
        **paired(rows, details, key, "bm25_guarded"),
        "ndcg_delta": round(profiles[key]["ndcg_at_3"] - base["ndcg_at_3"], 4),
        "added_p95_ms": round(profiles[key]["p95_ms"] - base["p95_ms"], 3),
    }


def _p95(values: list[float]) -> float | None:
    ordered = sorted(values)
    return round(ordered[ceil(0.95 * len(ordered)) - 1], 3) if ordered else None


def _quantiles(values: list[float]) -> list[float] | None:
    if len(values) < 2:
        return None
    return [round(q, 4) for q in statistics.quantiles(values, n=4)]


def onnx_diagnostics(rows: list[dict], details: list[dict], arm: str) -> dict:
    """Status counts, encode cost, cosine separation and gold coverage. Never gated."""
    measured = [row["measurements"][arm] for row in rows]
    statuses: dict[str, int] = {}
    for item in measured:
        label = f"{item['mode']}/{item['status']}"
        statuses[label] = statuses.get(label, 0) + 1
    report = {
        "mode_status": dict(sorted(statuses.items())),
        "encode_p95_ms": _p95([ms for item in measured for ms in item["encode_ms"]]),
    }
    tops = [item["top_cosine"] for item in measured if "top_cosine" in item]
    if tops:
        report["top_cosine_quartiles"] = {
            label: _quantiles([top[label] for top in tops if top[label] is not None])
            for label in ("relevant", "other")
        }
    coverage = {}
    for label in ("gold_vectorless", "gold_beyond_tokens"):
        subset = [m for m, d in zip(measured, details, strict=True) if d.get(label)]
        coverage[label] = {"tasks": len(subset), "satisfied": sum(m["satisfied"] for m in subset)}
    report["gold_coverage"] = coverage
    return report


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
    if "bm25_guarded" in strategies:
        report["versus_bm25_guarded"] = {
            key: versus_baseline(rows, details, key, report["profiles"])
            for key in strategies
            if key != "bm25_guarded"
        }
    for arm in (key for key in ONNX_ARMS if key in strategies):
        report.setdefault("onnx_diagnostics", {})[arm] = onnx_diagnostics(rows, details, arm)
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
    data: dict,
    per_paragraph: int,
    repetitions: int,
    rankings: tuple[LexicalRanking, ...] = (),
    *,
    encoder=None,
) -> dict:
    groups, details = squad_groups(data, per_paragraph)
    return evaluate_groups(groups, details, repetitions, rankings, encoder=encoder)


def mark_gold_coverage(groups: list[dict], details: list[dict], encoder) -> None:
    """Flag tasks whose required evidence has no vector (>4,096 bytes, empty, non-UTF-8)
    or extends beyond the encoder's token window."""
    texts = {row[0]: row[3] for group in groups for row in group["records"]}
    tasks = [task for group in groups for task in group["tasks"]]
    for task, detail in zip(tasks, details, strict=True):
        gold = [texts[identifier] for identifier in task["required"]]
        detail["gold_vectorless"] = any(not 1 <= len(text.encode()) <= 4096 for text in gold)
        detail["gold_beyond_tokens"] = any(encoder.truncated(text) for text in gold)


def evaluate_groups(
    groups: list[dict],
    details: list[dict],
    repetitions: int,
    rankings: tuple[LexicalRanking, ...] = (),
    *,
    encoder=None,
) -> dict:
    """Replay prepared groups; `details` align with tasks (article, split, answer position).

    With an ``encoder``, adds the ONNX arms and raises ``InvalidRun`` if any arm's status is
    outside the route-aware allow-list.
    """
    build_ms: list[float] = []
    if encoder is not None:
        mark_gold_coverage(groups, details, encoder)
    staged = fit(1)
    records = [row for group in groups for row in group["records"] if row[1] == group["domain"]]
    with tempfile.TemporaryDirectory(prefix="aams-retrieval-") as directory:
        rows = replay(
            Path(directory) / "bench.db",
            groups,
            repetitions,
            staged.suggests_hybrid,
            rankings=rankings,
            encoder=encoder,
            build_ms=build_ms,
        )
    if encoder is not None and (problems := check_validity(rows)):
        raise InvalidRun(f"{len(problems)} invalid ONNX measurements, first: {problems[0]}")
    for row in rows:
        row["measurements"]["staged"] = row["measurements"].pop("candidate")
    result = {
        "records_beyond_preview": round(
            statistics.mean(len(row[3].encode()) > PREVIEW_BYTES for row in records), 4
        ),
        "staged_training_checksum": staged.training_checksum,
    }
    if encoder is not None:
        result["onnx_spec"] = repr(encoder.spec)
        result["onnx_index_build_ms"] = {
            "total": round(sum(build_ms), 1),
            "p95_per_scope": _p95(build_ms),
        }
    for split in SPLITS:
        chosen = [i for i, detail in enumerate(details) if detail["split"] == split]
        if chosen:
            result[split] = split_report([rows[i] for i in chosen], [details[i] for i in chosen])
    return result


def load_encoder(
    parser: argparse.ArgumentParser, directory: Path | None, rankings
) -> object | None:
    """Load and probe the pinned encoder, or return None. ONNX needs the BM25 baseline arm."""
    if directory is None:
        return None
    if LexicalRanking.BM25 not in rankings:
        parser.error("--encoder-dir requires --ranking bm25")
    from onnx_encoder import OnnxSentenceEncoder, probe

    encoder = OnnxSentenceEncoder(directory)
    probe(encoder)
    return encoder


def run_valid(evaluation) -> dict:
    """Run an evaluation; an invalid run prints its reason and exits 3, never a result."""
    try:
        return evaluation()
    except InvalidRun as error:
        print(json.dumps({"valid": False, "reason": str(error)}))
        sys.exit(3)


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
    parser.add_argument("--encoder-dir", type=Path, help="Pinned ONNX encoder (adds ONNX arms)")
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20 or not 1 <= args.questions_per_paragraph <= 10:
        parser.error("Use 1 to 20 repetitions and 1 to 10 questions per paragraph")
    if args.max_articles is not None and args.max_articles < 1:
        parser.error("Use at least one article")
    raw = args.squad.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != args.expected_sha256:
        parser.error("Dataset checksum mismatch")
    rankings = tuple(LexicalRanking(value) for value in dict.fromkeys(args.ranking))
    encoder = load_encoder(parser, args.encoder_dir, rankings)
    data = json.loads(raw)
    data["data"] = data["data"][: args.max_articles]
    result = {
        "workload": "squad_v1.1_article_grouped",
        "dataset_sha256": digest,
        "articles": len(data["data"]),
        "questions_per_paragraph": args.questions_per_paragraph,
        "repetitions": args.repetitions,
        **run_valid(
            lambda: evaluate(
                data,
                args.questions_per_paragraph,
                args.repetitions,
                rankings,
                encoder=encoder,
            )
        ),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
