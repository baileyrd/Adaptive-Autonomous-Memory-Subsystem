"""Replay the frozen #121 selection factorial. Run with the repository installed."""

import itertools
import json
import random
import signal
import statistics
import tempfile
from collections import Counter
from pathlib import Path
from time import perf_counter

from aams.recall import CognitiveMemory
from aams.storage import SQLiteMemoryStore
from cognitive_task_agent import INSTRUCTION, decide
from cognitive_task_cases import digest
from copy_context_selector import copy_key, select_context
from evaluate_cognitive_tasks import database_digest, prepare, score, validate_context
from evaluate_copy_context import candidate_pool, checked_inputs, obtain_context
from selection_factorial_cases import cases

HERE = Path(__file__).parent
BUDGET = dict(max_citations=8, context_bytes=8192)
CONTRASTS = {
    "B-A": (-1, 1, 0, 0),
    "C-A": (-1, 0, 1, 0),
    "D-B": (0, -1, 0, 1),
    "D-C": (0, 0, -1, 1),
    "D-A": (-1, 0, 0, 1),
    "interaction": (1, -1, -1, 1),
}


def selection(pool, filtering):
    if filtering:
        return select_context(pool, max_citations=8, max_bytes=8192)
    context = []
    for row in pool[:8]:
        trial = [*context, row]
        if len(json.dumps(trial, sort_keys=True).encode()) > 8192:
            break
        context = trial
    return context


def audit(episode, task, pool, context, result):
    records = episode["observations"]
    visible = [
        r
        for r in records
        if r["scope"] == task["scope"]
        and r["recorded"] <= task["as_of"]
        and r["observed"] <= task["day"]
    ]
    # Independent semantic annotations for this generator, including natural-language positives.
    reports = []
    for r in visible:
        try:
            state = json.loads(r["text"])["state"]
        except json.JSONDecodeError:
            state = "clear"
        reports.append((r["id"], r["observed"], state))
    latest = max(day for _, day, _ in reports)
    current = {i: state for i, day, state in reports if day == latest}
    states = set(current.values())
    negative = {i for i, state in current.items() if state == "blocked"}
    retrieved = [r["evidence_id"] for r in pool]
    delivered = [r["evidence_id"] for r in context]
    used = result["decision"]["citations"]
    conflict = len(states) > 1
    wanted = "blocked" if result["expected"] == "stop" else "clear"
    eligible = {i for i, state in current.items() if state == wanted}
    complete = bool(eligible) and (wanted == "blocked" or task["checks"] == ["seal"])
    justified = complete and not conflict and bool(eligible.intersection(used))
    category = None
    if result["success"] and not justified:
        category = "correct_without_justification"
    elif not result["success"]:
        if not complete:
            category = "missing_evidence"
        elif not eligible.intersection(retrieved):
            category = "not_retrieved"
        elif not eligible.intersection(delivered):
            category = "excluded_from_context"
        elif conflict and result["decision"]["conflict_detected"] and result["abstained"]:
            category = "prudent_conflict_abstention"
        else:
            category = "presented_incorrectly_interpreted"
    origins = {r["id"]: r["origin"] for r in visible}
    return dict(
        pool=retrieved,
        context=delivered,
        cited=used,
        category=category,
        historical_unavailable=episode["family"] == "delayed_failure"
        and task["day"] >= 3
        and task["as_of"] < 5,
        negative_eligible=bool(negative),
        negative_surfaced=bool(negative.intersection(delivered)),
        conflict=conflict,
        handled=conflict and result["conflict_handled"],
        declared_groups=len({copy_key(r) for r in context}),
        actual_origins=len({origins[i] for i in delivered}),
    )


def replay(memory, episodes, arm):
    large = arm in "BD"
    recipe = dict(
        **BUDGET, candidate_citations=100 if large else 8, candidate_bytes=65536 if large else 8192
    )
    rows = []
    for episode in episodes:
        for task in episode["tasks"]:
            start = perf_counter()
            pool, truncated = candidate_pool(memory, task, recipe)
            context = selection(pool, arm in "CD")
            request = dict(topic=task["topic"], checks=task["checks"], instruction=INSTRUCTION)
            decision = decide(request, context)
            elapsed = perf_counter() - start
            validate_context(memory.store, task, context)
            if arm in "AD":
                reference, _ = obtain_context(
                    memory, task, "structured" if arm == "A" else "copy_diverse", recipe
                )
                if reference != context:
                    raise ValueError("Historical comparator mismatch")
            result = score(episode, task, request, context, decision)
            rows.append(
                dict(
                    arm=arm,
                    task=task["id"],
                    family=episode["family"],
                    expected=result["expected"],
                    action=decision["action"],
                    correct=result["success"],
                    unsafe=result["unsafe_proceed"],
                    truncated=truncated,
                    byt5_tokens=result["context_bytes"],
                    elapsed_ms=1000 * elapsed,
                    **audit(episode, task, pool, context, result),
                )
            )
    return rows


def contrasts(arms):
    output = {}
    for metric in ("correct", "unsafe"):
        for name, weights in CONTRASTS.items():
            groups = {}
            for rows in zip(*arms.values(), strict=True):
                if len({r["task"] for r in rows}) != 1:
                    raise ValueError("Unpaired decisions")
                groups.setdefault(rows[0]["family"], []).append(
                    sum(w * r[metric] for w, r in zip(weights, rows, strict=True))
                )
            means = [statistics.mean(group) for group in groups.values()]
            rng = random.Random(0)
            boot = sorted(statistics.mean(rng.choices(means, k=len(means))) for _ in range(2000))
            output[f"{metric}/{name}"] = [statistics.mean(means), boot[50], boot[1950]]
    return output


def run():
    episodes = cases()
    if digest(episodes) != (HERE / "selection_factorial_cases.sha256").read_text().strip():
        raise ValueError("Frozen histories changed")
    _, previous = checked_inputs()
    # #120 verifies its disjointness from #118. Check both old datasets directly.
    from cognitive_task_cases import cases as originals

    previous += originals(json.loads((HERE / "cognitive_task_recipe.json").read_text()))
    for field in ("id", "source", "scope"):

        def values(bucket):
            return {r[field] for e in bucket for r in e["observations"]}

        if values(previous) & values(episodes):
            raise ValueError("Historical source overlap")
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "memory.db"
        prepare(path, episodes)
        memory = CognitiveMemory(SQLiteMemoryStore(path))
        before = database_digest(path)
        arms = {}
        for arm in "ABCD":
            signal.alarm(120)
            try:
                arms[arm] = replay(memory, episodes, arm)
            finally:
                signal.alarm(0)
            if database_digest(path) != before:
                raise ValueError("Mutation during replay")
    summaries = {}
    for arm, rows in arms.items():
        summaries[arm] = {
            k: sum(r[k] for r in rows)
            for k in (
                "correct",
                "unsafe",
                "negative_eligible",
                "negative_surfaced",
                "conflict",
                "handled",
                "byt5_tokens",
                "declared_groups",
                "actual_origins",
                "truncated",
            )
        }
        summaries[arm].update(
            candidates=sum(len(r["pool"]) for r in rows),
            benign_regressions=sum(
                a["correct"] and a["expected"] == "proceed" and not r["correct"]
                for a, r in zip(arms["A"], rows, strict=True)
            ),
            incorrect_abstentions=sum(r["action"] == "abstain" and not r["correct"] for r in rows),
            failures=dict(Counter(r["category"] for r in rows if r["category"])),
            median_ms=statistics.median(r["elapsed_ms"] for r in rows),
        )
    return dict(
        cases_sha256=digest(episodes),
        summary=summaries,
        contrasts=contrasts(arms),
        rows=list(itertools.chain.from_iterable(arms.values())),
    )


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
