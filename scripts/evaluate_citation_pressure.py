"""Observe the merged selector across frozen adjacent citation-pressure pairs."""

import json
import tempfile
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import evaluate_quorum_lineage as baseline
from aams.recall import CognitiveMemory
from aams.storage import SQLiteMemoryStore
from citation_pressure_cases import CONTROL_MODES, fixtures
from cognitive_task_cases import digest
from copy_context_selector import copy_key
from evaluate_cognitive_tasks import database_digest, prepare, validate_context
from evaluate_copy_context import candidate_pool
from evaluate_lineage import WINDOW, paired_interval
from lineage_cases import fixtures as lineage_fixtures
from quorum_lineage_cases import fixtures as quorum_fixtures

PINS = (
    "c5bb9a2d395c169a87c04ced8b4c42fed7ac331b2a1c6a56b24964902de688d5",
    "586313eb8a57dc3dc6d1e9139a774f0ac56ed6be8c5c253dd21c879597834cfe",
)
MODULE_PINS = {
    "evaluate_quorum_lineage": "621df116affc48d79be61e1caacf17da751d44f9f6eb02687c903696c1467cec",
    "lineage_selector": "9f6d3c1d625024e727d99a4e20cf3d76cc669a9f873d0980ecd6042078defad7",
    "evaluate_copy_context": "acfaac0fe80f8456dbe43262b0145f28f23d7af877a4565775da31addf8a8436",
    "copy_context_selector": "fa9b754725077efdb47dcbb4903eb58ac00dcb770ed1c3737a7b4efc2fb27174",
    "cognitive_task_agent": "b70098bde0141ada35d54c2850519a001f06fbf810dd247032b6d5814ca27eeb",
}
METRICS = ("unsafe", "missed_stop", "unnecessary_hold", "correct")


def score(action, expected):
    return dict(
        unsafe=action == "proceed" and expected != "proceed",
        missed_stop=expected == "stop" and action != "stop",
        unnecessary_hold=expected == "proceed" and action != "proceed",
        correct=action == expected,
    )


def first_loss(ranks):
    for stage in ("native", "lineage", "declared_copy", "final"):
        if ranks[stage] is None:
            return stage
    return "decision_rule"


def evidence_ids(rows):
    return [row["evidence_id"] for row in rows]


def observe(case, *, high, mode="visible"):
    task = case["task"]
    decisive = case["decisive"]
    replacements = {
        "foreign": {"scope": "outside-" + task["scope"]},
        "recorded_late": {"recorded": 7},
        "effective_late": {"observed": 7},
    }
    records, eligible = [], set()
    for row in case["observations"]:
        rid = row["id"]
        if rid == case["extra"] and not high:
            continue
        if rid == decisive and mode != "visible":
            if mode not in {"absent", "withheld"}:
                records.append({**row, **replacements[mode]})
            continue
        records.append(row)
        eligible.add(rid)
    links = [edge for edge in case["links"] if high or edge["child"] != case["extra"]]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "memory.db"
        prepare(path, [{"tasks": [task], "observations": records}])
        store = SQLiteMemoryStore(path)
        before = database_digest(path)
        pool, truncated = candidate_pool(CognitiveMemory(store), task, WINDOW)
        if truncated or set(evidence_ids(pool)) != eligible:
            raise ValueError(f"Unexpected native window for {case['id']} / {mode}")
        receipts = {rid: slot for rid, slot in case["receipts"].items() if rid in eligible}
        # Observe the final selector's argument and delegate to the unchanged function.
        with patch.object(baseline, "select_context", wraps=baseline.select_context) as selector:
            context = baseline.directed_context(store, task, pool, links, receipts)
        selector.assert_called_once()
        (after_lineage,), limits = selector.call_args
        if limits != {"max_citations": 8, "max_bytes": 8192}:
            raise ValueError("Budget drift")
        declared = {}
        for row in after_lineage:
            declared.setdefault(copy_key(row), row)
        after_declared = list(declared.values())
        boundary_bytes = len(json.dumps(after_declared[:9], sort_keys=True).encode())
        if boundary_bytes > limits["max_bytes"] or context != after_declared[:8]:
            raise ValueError("Final citation boundary does not isolate the citation cap")
        validate_context(store, task, context)
        response = baseline.public_response(task, context, receipts)
        if before != database_digest(path):
            raise ValueError("Ledger changed")

    orders = dict(
        native=evidence_ids(pool),
        lineage=evidence_ids(after_lineage),
        declared_copy=evidence_ids(after_declared),
        final=evidence_ids(context),
    )
    for before, after in zip(orders.values(), list(orders.values())[1:]):
        if [rid for rid in before if rid in after] != after:
            raise ValueError("Selection reordered or added evidence")
    ranks = {
        stage: ids.index(decisive) + 1 if decisive in ids else None for stage, ids in orders.items()
    }
    trace = dict(
        orders=orders,
        decisive_ranks=ranks,
        boundary_bytes=boundary_bytes,
        decision=response["decision"],
        latest_original_slots=response["latest_original_slots"],
        public_response_sha256=digest(response),
    )
    return trace, response


def summarize(rows):
    totals = {
        arm: {metric: sum(r["scores"][arm][metric] for r in rows) for metric in METRICS}
        for arm in "AB"
    }
    transitions = {
        metric: {
            "introduced": sum(
                not r["scores"]["A"][metric] and r["scores"]["B"][metric] for r in rows
            ),
            "corrected": sum(
                r["scores"]["A"][metric] and not r["scores"]["B"][metric] for r in rows
            ),
        }
        for metric in METRICS
        if metric != "correct"
    }
    return dict(
        n=len(rows),
        totals=totals,
        transitions=transitions,
        paired={metric: paired_interval(rows, metric) for metric in METRICS},
    )


def run():
    cases, labels = fixtures()
    if tuple(map(digest, (cases, labels))) != PINS:
        raise ValueError("Fixture or label drift")
    for module, pin in MODULE_PINS.items():
        if sha256(Path(__file__).with_name(module + ".py").read_bytes()).hexdigest() != pin:
            raise ValueError(f"Baseline drift in {module}")
    prior = lineage_fixtures()[0] + quorum_fixtures()[0]
    for field in ("id", "source", "scope"):
        old = {row[field] for case in prior for row in case["observations"]}
        if any(row[field] in old for case in cases for row in case["observations"]):
            raise ValueError(f"Fixture overlap in {field}")

    primary, linked, controls = [], [], []
    for case in cases:
        outputs = {arm: observe(case, high=arm == "B")[0] for arm in "AB"}
        a, b = outputs["A"], outputs["B"]
        if [rid for rid in b["orders"]["native"] if rid != case["extra"]] != a["orders"]["native"]:
            raise ValueError("Adding the copy reordered common native candidates")
        raw_low = 8 + int(case["attribution"] == "partial")
        if [a["decisive_ranks"]["native"], b["decisive_ranks"]["native"]] != [raw_low, raw_low + 1]:
            raise ValueError(f"Unexpected native boundary: {case['id']}")
        if case["attribution"] != "linked" and [
            a["decisive_ranks"]["declared_copy"],
            b["decisive_ranks"]["declared_copy"],
        ] != [8, 9]:
            raise ValueError(f"Unexpected post-filter boundary: {case['id']}")
        expected = labels[case["id"]]["expected"]
        scores = {
            arm: score(trace["decision"]["action"], expected) for arm, trace in outputs.items()
        }
        for arm, trace in outputs.items():
            trace["wrong_action_first_loss"] = (
                None if scores[arm]["correct"] else first_loss(trace["decisive_ranks"])
            )
        row = dict(
            id=case["id"],
            family=case["family"],
            expected=expected,
            decisive=case["decisive"],
            extra_copy=case["extra"],
            receipts=case["receipts"],
            arms=outputs,
            scores=scores,
        )
        (linked if case["attribution"] == "linked" else primary).append(row)
        if case["attribution"] == "unlinked":
            absent = None
            for mode in CONTROL_MODES:
                trace, response = observe(case, high=True, mode=mode)
                if mode == "absent":
                    absent = response
                controls.append(
                    dict(id=case["id"], mode=mode, matches_absent=response == absent, trace=trace)
                )

    summary = summarize(primary)
    linked_ok = all(
        r["scores"][arm]["correct"] and r["arms"][arm]["decisive_ranks"]["final"] is not None
        for r in linked
        for arm in "AB"
    )
    privacy_ok = all(c["matches_absent"] for c in controls)
    return dict(
        fixture_sha256=PINS[0],
        labels_sha256=PINS[1],
        module_pins=MODULE_PINS,
        summary=summary,
        linked_summary=summarize(linked),
        rows=primary,
        linked_rows=linked,
        controls=controls,
        gates=dict(
            clean=summary["totals"]["B"]["correct"] == len(primary) and privacy_ok,
            linked=linked_ok,
            inaccessible=privacy_ok,
        ),
    )


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, indent=2))
