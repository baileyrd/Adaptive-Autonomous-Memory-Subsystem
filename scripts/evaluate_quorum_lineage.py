"""Replay the frozen two-inspection experiment on a disposable AAMS ledger."""

import json
import tempfile
from graphlib import CycleError, TopologicalSorter
from hashlib import sha256
from pathlib import Path

from aams.recall import CognitiveMemory
from aams.storage import SQLiteMemoryStore
from cognitive_task_agent import INSTRUCTION, decide
from cognitive_task_cases import digest
from copy_context_selector import select_context
from evaluate_cognitive_tasks import database_digest, prepare, validate_context
from evaluate_copy_context import candidate_pool
from evaluate_lineage import WINDOW, paired_interval
from lineage_cases import fixtures as prior_fixtures
from lineage_selector import components, respond
from quorum_lineage_cases import fixtures, overlays

PINS = (
    "0b3a698fcca98108cc406a7a7347ddf4a3237a437a07601cbed61d818cc1314c",
    "8075e22aa5c560463bd73d7bae69fddb14fcb90bf76e8164bd76261783ab4f52",
)
BASELINE_SHA = "9f6d3c1d625024e727d99a4e20cf3d76cc669a9f873d0980ecd6042078defad7"


def directed_context(store, task, pool, links, receipts):
    by_id = {row["evidence_id"]: row for row in pool}
    parents = {rid: set() for rid in by_id}
    for edge in links:
        # A singleton call applies exactly the merged relation and endpoint checks
        # without using the undirected grouping for ancestry.
        if components(store, task, pool, [edge], set()) and edge["child"] not in receipts:
            parents[edge["child"]].add(edge["parent"])

    order = TopologicalSorter(parents)
    try:
        order.prepare()
    except CycleError:
        # Ready nodes can still be resolved. Cycles and their dependents stay unknown.
        pass
    roots = {}
    while order.is_active():
        ready = order.get_ready()
        for rid in ready:
            if rid in receipts:
                roots[rid] = frozenset({rid})
            elif parents[rid] and parents[rid] <= roots.keys():
                roots[rid] = frozenset().union(*(roots[parent] for parent in parents[rid]))
        order.done(*ready)

    def assertion(rid):
        row = by_id[rid]
        return row["digest"], row["observed_at"]

    retained, seen = [], set()
    for rid, row in by_id.items():
        if rid in roots and rid not in receipts:
            claim = assertion(rid)
            signature = (roots[rid], claim)
            if signature in seen or all(assertion(root) == claim for root in roots[rid]):
                continue
            seen.add(signature)
        retained.append(row)
    return select_context(retained, max_citations=8, max_bytes=8192)


def public_response(task, context, receipts):
    request = dict(topic=task["topic"], checks=task["checks"], instruction=INSTRUCTION)
    decision = decide(request, context)
    slots = sorted({receipts[rid] for rid in decision["citations"] if rid in receipts})
    if decision["action"] == "proceed" and len(slots) < 2:
        decision["action"] = "abstain"
    return dict(context=context, decision=decision, latest_original_slots=slots)


def responses(store, task, pool, links, receipts):
    a = respond(pool, task, components(store, task, pool, links, set()))["context"]
    b = directed_context(store, task, pool, links, receipts)
    return {arm: public_response(task, context, receipts) for arm, context in zip("AB", (a, b))}


def score(response, label):
    action = response["decision"]["action"]
    expected = label["expected"]
    selected = [row["evidence_id"] for row in response["context"]]
    return dict(
        action=action,
        correct=action == expected,
        unsafe=action == "proceed" and expected != "proceed",
        unnecessary_hold=action != "proceed" and expected == "proceed",
        retained_originals=sorted(set(selected) & set(label["originals"])),
        selected=selected,
        conflict=response["decision"]["conflict_detected"],
        latest_original_slots=response["latest_original_slots"],
    )


def summarize(rows):
    a, b = ([row["scores"][arm] for row in rows] for arm in "AB")
    return dict(
        n=len(rows),
        corrected_unsafe=sum(x["unsafe"] and y["correct"] for x, y in zip(a, b)),
        introduced_unsafe=sum(not x["unsafe"] and y["unsafe"] for x, y in zip(a, b)),
        correct_lost=sum(x["correct"] and not y["correct"] for x, y in zip(a, b)),
        arms={
            arm: {
                **{
                    metric: sum(row[metric] for row in scores)
                    for metric in ("correct", "unsafe", "unnecessary_hold", "conflict")
                },
                "stop": sum(row["action"] == "stop" for row in scores),
                "abstain": sum(row["action"] == "abstain" for row in scores),
            }
            for arm, scores in zip("AB", (a, b))
        },
    )


def run():
    cases, labels = fixtures()
    if tuple(map(digest, (cases, labels))) != PINS:
        raise ValueError("Fixture drift")
    baseline_path = Path(__file__).with_name("lineage_selector.py")
    if sha256(baseline_path.read_bytes()).hexdigest() != BASELINE_SHA:
        raise ValueError("Baseline drift")

    prior, _ = prior_fixtures()
    for field in ("id", "source", "scope"):
        previous = {r[field] for case in prior for r in case["observations"]}
        current = {r[field] for case in cases for r in case["observations"]}
        if previous & current:
            raise ValueError(f"Source overlap in {field}")

    rows, controls = [], []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "memory.db"
        prepare(path, cases)
        store = SQLiteMemoryStore(path)
        memory = CognitiveMemory(store)
        before = database_digest(path)
        for case in cases:
            task = case["tasks"][0]
            pool, truncated = candidate_pool(memory, task, WINDOW)
            pool_ids = [row["evidence_id"] for row in pool]
            if truncated or set(pool_ids) != {row["id"] for row in case["observations"]}:
                raise ValueError("Incomplete candidate window")
            receipts = {rid: slot for rid, slot in case["receipts"].items() if rid in pool_ids}
            outputs = responses(store, task, pool, case["links"], receipts)
            for out in outputs.values():
                validate_context(store, task, out["context"])
                ids = {row["evidence_id"] for row in out["context"]}
                if [rid for rid in pool_ids if rid in ids] != [
                    row["evidence_id"] for row in out["context"]
                ]:
                    raise ValueError("Selected rows changed candidate order")
            label = labels[case["id"]]
            rows.append(
                dict(
                    id=case["id"],
                    family=case["family"],
                    expected=label["expected"],
                    originals=label["originals"],
                    common_pool=pool_ids,
                    scores={arm: score(out, label) for arm, out in outputs.items()},
                )
            )
            if case["family"] == "dual":
                variants = overlays(case)
                absent = responses(store, task, pool, variants["absent"], receipts)
                for name, edges in variants.items():
                    result = responses(store, task, pool, edges, receipts)
                    match = {arm: result[arm] == absent[arm] for arm in "AB"}
                    if name not in {"visible", "absent"} and not all(match.values()):
                        raise ValueError(f"Public response differs for unavailable overlay {name}")
                    controls.append(
                        dict(
                            id=case["id"],
                            overlay=name,
                            matches_absent=match,
                            public_response_sha256={
                                arm: digest(out) for arm, out in result.items()
                            },
                        )
                    )
        if before != database_digest(path):
            raise ValueError("Ledger changed")
    summary = summarize(rows)
    paired = {
        metric: paired_interval(rows, metric)
        for metric in ("correct", "unsafe", "unnecessary_hold")
    }
    mechanism = all(
        row["scores"]["B"]["correct"]
        and (
            row["expected"] != "proceed"
            or row["scores"]["B"]["retained_originals"] == row["originals"]
        )
        and (row["family"] != "single" or row["scores"]["B"]["selected"] == row["originals"])
        and (row["family"] != "conflict" or row["scores"]["B"]["conflict"])
        for row in rows
    )
    overall = (
        mechanism
        and summary["arms"]["B"]["unnecessary_hold"] < summary["arms"]["A"]["unnecessary_hold"]
        and summary["introduced_unsafe"] == summary["correct_lost"] == 0
        and paired["correct"][1] > 0
    )
    return dict(
        fixture_sha256=PINS[0],
        label_sha256=PINS[1],
        baseline_sha256=BASELINE_SHA,
        database_digest=before,
        summary=summary,
        paired=paired,
        gates=dict(mechanism=mechanism, overall=overall),
        rows=rows,
        controls=controls,
    )


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, indent=2))
