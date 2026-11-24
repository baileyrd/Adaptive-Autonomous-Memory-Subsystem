"""E1: Laya as an offline relevance judge over BM25 with guarded routing. Eval-only.

Pre-registered in the Laya scoping doc (2026-11-24). Two steps run here; the judge step runs
wherever the Unsloth Decision API is (``laya_judge.py``):

    prepare  SQuAD held-out sample + SciFact + v0.6 fixture -> tasks.json and pairs.jsonl
    ceiling  tasks.json -> the same report for a perfect judge (gold first), no API needed
    score    tasks.json + judgments.jsonl -> gate report

``prepare`` takes the top 10 of ``bm25_guarded`` recall per task, checks that its top 3 equals
the arm the v0.8 benchmark measures, and writes one pair per unique (query, passage). Gold
labels stay in tasks.json; pairs.jsonl carries none. ``score`` reorders each top 10 by the
judge's yes probability (ties keep BM25 order) and compares the top 3 with the baseline.
"""

import argparse
import json
import statistics
import sys
import tarfile
import tempfile
from collections.abc import Iterator
from hashlib import sha256
from math import ceil, log2
from pathlib import Path
from random import Random

from evaluate_retrieval import SQUAD_SHA256, grouped_interval, squad_groups
from evaluate_scifact import CLAIM_FILES, SCIFACT_SHA256, read_jsonl, scifact_groups
from evaluate_semantic import seed, timestamp
from laya_judge import INSTRUCTIONS, MODEL
from offline_experiment import load_groups

from aams.ranking import LexicalRanking
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.representations import DeterministicFixtureProvider
from aams.retrieval_routing import RetrievalMode
from aams.storage import AccessContext, SQLiteMemoryStore
from aams.vector_index import RepresentationIndex

DEPTH = 10
TOP_K = 3
SAMPLE_SEED = 20261124
PASSAGE_CHARS = 1500
GATES = {"min_delta": 0.05, "min_auc": 0.85, "max_ece": 0.05}
PROMPT_SHA256 = sha256(f"{MODEL}\n{INSTRUCTIONS}".encode()).hexdigest()


def pair_key(query: str, passage: str) -> str:
    return sha256(json.dumps([query, passage]).encode()).hexdigest()


def _cited(packet: dict) -> list[str]:
    ids = (c["evidence_id"] for item in packet["items"] for c in item["citations"])
    return list(dict.fromkeys(ids))


def _recall(memory, access, task, provider, depth: int) -> list[str]:
    need = CognitiveNeed(
        query=task["query"], max_items=depth, recorded_as_of=timestamp(task["day"])
    )
    hybrid = task["opt_in"]
    return _cited(
        memory.recall(
            access,
            need,
            provider=provider if hybrid else None,
            requested_mode=RetrievalMode.HYBRID if hybrid else RetrievalMode.LEXICAL,
        )
    )


def prepare_groups(workload: str, groups: list[dict], keep: set[tuple[str, int]] | None) -> list:
    """Candidate lists for the chosen (scope, ordinal) tasks, or every task when keep is None.

    Raises if the top-3 recall differs from the top-10 prefix: then the baseline would not be
    the arm v0.8 measured, and the comparison would be invalid.
    """
    tasks = []
    with tempfile.TemporaryDirectory(prefix="aams-laya-") as directory:
        store = SQLiteMemoryStore(Path(directory) / "e1.db")
        provider = DeterministicFixtureProvider()
        index = RepresentationIndex(store)
        memory = CognitiveMemory(store, lexical_ranking=LexicalRanking.BM25)
        for group in groups:
            scope = group["domain"]
            chosen = [
                (i, t) for i, t in enumerate(group["tasks"]) if keep is None or (scope, i) in keep
            ]
            if not chosen:
                continue
            for identifier, record_scope, day, text, origin in group["records"]:
                seed(store, identifier, record_scope, day, text, origin=origin)
            index.rebuild(AccessContext("fixture", scope, True), provider)
            access = AccessContext("fixture", scope)
            texts = {row[0]: row[3] for row in group["records"]}
            visible = {row[0]: row[2] for row in group["records"] if row[1] == scope}
            for ordinal, task in chosen:
                candidates = _recall(memory, access, task, provider, DEPTH)
                baseline = _recall(memory, access, task, provider, TOP_K)
                if candidates[: len(baseline)] != baseline:
                    raise RuntimeError(f"{scope}/{ordinal}: top-3 is not the top-10 prefix")
                leaks = [i for i in candidates if visible.get(i, task["day"] + 1) > task["day"]]
                if leaks:
                    raise RuntimeError(f"{scope}/{ordinal}: recall exposed {leaks}")
                passages = {i: texts[i][:PASSAGE_CHARS] for i in candidates}
                tasks.append(
                    {
                        "workload": workload,
                        "group": scope,
                        "task": ordinal,
                        "query": task["query"],
                        "relevant": task["relevant"],
                        "required": task["required"],
                        "contradiction": task["contradiction"],
                        "candidates": candidates,
                        "keys": [pair_key(task["query"], passages[i]) for i in candidates],
                        "truncated": [len(texts[i]) > PASSAGE_CHARS for i in candidates],
                        "passages": passages,
                    }
                )
    return tasks


def squad_sample(groups: list[dict], size: int) -> set[tuple[str, int]]:
    """Seeded uniform sample of held-out SQuAD tasks; design articles are never touched."""
    population = [
        (group["domain"], i)
        for group in groups
        if group["split"] == "heldout"
        for i in range(len(group["tasks"]))
    ]
    return set(Random(SAMPLE_SEED).sample(population, min(size, len(population))))


def rerank(candidates: list[str], keys: list[str], p_yes: dict[str, float]) -> list[str]:
    """Order by descending yes probability; ties keep the incoming (BM25) order."""
    order = sorted(range(len(candidates)), key=lambda i: (-p_yes[keys[i]], i))
    return [candidates[i] for i in order]


def _ndcg(found: list[str], relevant: set[str]) -> float:
    ideal = sum(1 / log2(rank + 2) for rank in range(min(TOP_K, len(relevant))))
    gain = sum(1 / log2(rank + 2) for rank, i in enumerate(found[:TOP_K]) if i in relevant)
    return gain / ideal


def auc(scores: list[float], labels: list[bool]) -> float | None:
    """Mann-Whitney AUC with ties counted as half; None without both classes."""
    positives = [s for s, y in zip(scores, labels, strict=True) if y]
    negatives = [s for s, y in zip(scores, labels, strict=True) if not y]
    if not positives or not negatives:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def ece(scores: list[float], labels: list[bool], bins: int = 10) -> float | None:
    """Expected calibration error over equal-width probability bins."""
    if not scores:
        return None
    total = 0.0
    for b in range(bins):
        members = [
            (s, y)
            for s, y in zip(scores, labels, strict=True)
            if b / bins <= s < (b + 1) / bins or (b == bins - 1 and s == 1.0)
        ]
        if members:
            gap = statistics.fmean(s for s, _ in members) - statistics.fmean(y for _, y in members)
            total += len(members) * abs(gap)
    return total / len(scores)


def _labels(tasks: list[dict], p_yes: dict[str, float]) -> Iterator[tuple[float, bool]]:
    for task in tasks:
        relevant = set(task["relevant"])
        for identifier, key in zip(task["candidates"], task["keys"], strict=True):
            yield p_yes[key], identifier in relevant


def score(tasks: list[dict], p_yes: dict[str, float]) -> dict:
    """Per-workload paired comparison of the top 3, plus judge label quality."""
    report = {}
    for workload in sorted({t["workload"] for t in tasks}):
        chosen = [t for t in tasks if t["workload"] == workload]
        by_group: dict[str, list[int]] = {}
        base_sat = arm_sat = regressions = 0
        base_ndcg, arm_ndcg = [], []
        for task in chosen:
            base = task["candidates"][:TOP_K]
            arm = rerank(task["candidates"], task["keys"], p_yes)[:TOP_K]
            required, relevant = set(task["required"]), set(task["relevant"])
            before, after = required <= set(base), required <= set(arm)
            base_sat += before
            arm_sat += after
            regressions += task["contradiction"] and before and not after
            base_ndcg.append(_ndcg(base, relevant))
            arm_ndcg.append(_ndcg(arm, relevant))
            by_group.setdefault(task["group"], []).append(int(after) - int(before))
        flat = [d for deltas in by_group.values() for d in deltas]
        pairs = list(_labels(chosen, p_yes))
        report[workload] = {
            "tasks": len(chosen),
            "satisfied": {"bm25_guarded": base_sat, "bm25_guarded_laya": arm_sat},
            "ndcg_at_3": {
                "bm25_guarded": round(statistics.fmean(base_ndcg), 4),
                "bm25_guarded_laya": round(statistics.fmean(arm_ndcg), 4),
            },
            "wins": flat.count(1),
            "losses": flat.count(-1),
            "mean_delta": round(statistics.fmean(flat), 4),
            "ci95": grouped_interval(by_group) if len(by_group) > 1 else None,
            "contradiction_regressions": regressions,
            "auc": _round(auc(*_unzip(pairs))),
            "ece": _round(ece(*_unzip(pairs))),
            "passages_truncated": round(
                statistics.fmean(x for t in chosen for x in t["truncated"]), 4
            ),
        }
    public = [t for t in tasks if t["workload"] != "fixture_v06"]
    scores, labels = _unzip(list(_labels(public, p_yes)))
    report["pooled_public"] = {
        "auc": _round(auc(scores, labels)),
        "ece": _round(ece(scores, labels)),
    }
    return report


def _unzip(pairs: list[tuple[float, bool]]) -> tuple[list[float], list[bool]]:
    return [s for s, _ in pairs], [y for _, y in pairs]


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def gates(report: dict) -> dict:
    """The pre-registered pass conditions; every one must hold."""
    checks = {}
    for workload in ("squad_heldout", "scifact"):
        block = report.get(workload)
        checks[f"{workload}_delta"] = bool(
            block
            and block["mean_delta"] >= GATES["min_delta"]
            and block["ci95"] is not None
            and block["ci95"][0] > 0
        )
    pooled = report["pooled_public"]
    checks["label_auc"] = pooled["auc"] is not None and pooled["auc"] >= GATES["min_auc"]
    checks["label_ece"] = pooled["ece"] is not None and pooled["ece"] <= GATES["max_ece"]
    fixture = report.get("fixture_v06")
    checks["fixture_no_regression"] = bool(
        fixture
        and fixture["satisfied"]["bm25_guarded_laya"] >= fixture["satisfied"]["bm25_guarded"]
        and all(b["contradiction_regressions"] == 0 for k, b in report.items() if "tasks" in b)
    )
    checks["passed"] = all(checks.values())
    return checks


def _verified(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise SystemExit(f"Checksum mismatch: {path}")
    return raw


def prepare(args: argparse.Namespace) -> None:
    data = json.loads(_verified(args.squad, SQUAD_SHA256))
    squad, _ = squad_groups(data, args.questions_per_paragraph)
    _verified(args.scifact, SCIFACT_SHA256)
    with tarfile.open(args.scifact) as archive:
        corpus = read_jsonl(archive, "data/corpus.jsonl")
        claims = [c for name in CLAIM_FILES for c in read_jsonl(archive, name)]
    scifact, _, _ = scifact_groups(corpus, claims, args.shards)
    tasks = [
        *prepare_groups("squad_heldout", squad, squad_sample(squad, args.squad_tasks)),
        *prepare_groups("scifact", scifact, None),
        *prepare_groups("fixture_v06", load_groups(), None),
    ]
    pairs = {}
    for task in tasks:
        passages = task.pop("passages")
        for identifier, key in zip(task["candidates"], task["keys"], strict=True):
            pairs[key] = {"key": key, "query": task["query"], "passage": passages[identifier]}
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "prompt_sha256": PROMPT_SHA256,
        "model": MODEL,
        "sample_seed": SAMPLE_SEED,
        "squad_tasks": args.squad_tasks,
        "tasks": tasks,
    }
    (args.out / "tasks.json").write_text(json.dumps(manifest))
    with (args.out / "pairs.jsonl").open("w", encoding="utf-8") as sink:
        for pair in pairs.values():
            sink.write(json.dumps(pair) + "\n")
    counts = {w: sum(t["workload"] == w for t in tasks) for w in {t["workload"] for t in tasks}}
    print(json.dumps({"tasks": counts, "pairs": len(pairs), "prompt_sha256": PROMPT_SHA256}))


def oracle_judgments(tasks: list[dict]) -> dict[str, float]:
    """A perfect judge: 1 for any pair whose passage is gold for its query, else 0."""
    p_yes: dict[str, float] = {}
    for task in tasks:
        relevant = set(task["relevant"])
        for identifier, key in zip(task["candidates"], task["keys"], strict=True):
            p_yes[key] = max(p_yes.get(key, 0.0), float(identifier in relevant))
    return p_yes


def ceiling_command(args: argparse.Namespace) -> None:
    tasks = json.loads(args.tasks.read_text())["tasks"]
    report = score(tasks, oracle_judgments(tasks))
    print(json.dumps({"judge": "oracle", **report, "gates": gates(report)}, indent=2))


def score_command(args: argparse.Namespace) -> None:
    manifest = json.loads(args.tasks.read_text())
    if manifest["prompt_sha256"] != PROMPT_SHA256:
        raise SystemExit("Prompt changed since prepare; the pre-registration no longer holds")
    judgments = [json.loads(line) for line in args.judgments.read_text().splitlines() if line]
    p_yes = {j["key"]: j["p_yes"] for j in judgments}
    missing = {k for t in manifest["tasks"] for k in t["keys"]} - p_yes.keys()
    if missing:
        raise SystemExit(f"{len(missing)} pairs are not judged yet; resume laya_judge.py")
    report = score(manifest["tasks"], p_yes)
    elapsed = sorted(j["elapsed_ms"] for j in judgments)
    result = {
        "prompt_sha256": PROMPT_SHA256,
        "served_models": sorted({j["model"] for j in judgments}),
        "judge_ms": {
            "median": statistics.median(elapsed),
            "p95": elapsed[ceil(0.95 * len(elapsed)) - 1],
        },
        **report,
        "gates": gates(report),
    }
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True)
    build = commands.add_parser("prepare")
    build.add_argument("--squad", type=Path, required=True, help="SQuAD dev-v1.1.json")
    build.add_argument("--scifact", type=Path, required=True, help="SciFact data.tar.gz")
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--squad-tasks", type=int, default=300)
    build.add_argument("--questions-per-paragraph", type=int, default=5)
    build.add_argument("--shards", type=int, default=16)
    build.set_defaults(run=prepare)
    top = commands.add_parser("ceiling")
    top.add_argument("tasks", type=Path)
    top.set_defaults(run=ceiling_command)
    rate = commands.add_parser("score")
    rate.add_argument("tasks", type=Path)
    rate.add_argument("judgments", type=Path)
    rate.set_defaults(run=score_command)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    sys.exit(main())
