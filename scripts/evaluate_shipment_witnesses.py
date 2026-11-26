"""Paired offline evaluation of final shipment citation selection only."""

import json
import tempfile
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import evaluate_quorum_lineage as baseline
from aams.recall import CognitiveMemory
from aams.storage import SQLiteMemoryStore
from citation_pressure_cases import fixtures as prior_fixtures
from cognitive_task_cases import digest
from evaluate_citation_pressure import score, summarize
from evaluate_cognitive_tasks import database_digest, prepare, validate_context
from evaluate_copy_context import candidate_pool
from evaluate_lineage import WINDOW
from shipment_witness_cases import CONTROLS, fixtures
from shipment_witness_selector import select_witnesses

PINS = (
    "d539785566abc5a73781048e47942bebb607988deaef11401e576a8fefa235d2",
    "baf9330bfa29339f0084d799af8adb21002db7e7de2e9b20930033165ad98bf4",
)
MODULE_PINS = {
    "shipment_witness_selector": "8488de5cd53485302f11f011837defad2556c5596cd97b0162465167e32cfa85",
    "evaluate_citation_pressure": "04478b0883a8afe274753943b54679f1240f425e1c2b1cdee23644dd7910ec16",
    "evaluate_quorum_lineage": "621df116affc48d79be61e1caacf17da751d44f9f6eb02687c903696c1467cec",
}
LIMITS = dict(max_citations=8, max_bytes=8192)


def compare(case, mode="visible"):
    task = case["task"]
    decisive = case["decisive"]
    replacements = {
        "foreign": dict(scope="outside-" + task["scope"]),
        "recorded_late": dict(recorded=task["as_of"] + 1),
        "effective_late": dict(observed=task["day"] + 1),
    }
    records = []
    eligible = set()
    for row in case["observations"]:
        rid = row["id"]
        if rid == decisive and mode != "visible":
            if mode in replacements:
                records.append({**row, **replacements[mode]})
        else:
            records.append(row)
            eligible.add(rid)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "memory.db"
        prepare(path, [{"tasks": [task], "observations": records}])
        store = SQLiteMemoryStore(path)
        before = database_digest(path)
        pool, truncated = candidate_pool(CognitiveMemory(store), task, WINDOW)
        native_ids = [row["evidence_id"] for row in pool]
        if truncated or set(native_ids) != eligible:
            raise ValueError("Native window differs from authorized fixture")
        receipts = {rid: slot for rid, slot in case["receipts"].items() if rid in eligible}
        with patch.object(baseline, "select_context", wraps=baseline.select_context) as call:
            a = baseline.directed_context(store, task, pool, case["links"], receipts)
        call.assert_called_once()
        (shared,), limits = call.call_args
        if limits != LIMITS:
            raise ValueError("Baseline budget drift")
        before_input = digest((shared, receipts, task))
        b = select_witnesses(shared, task=task, receipts=receipts, **limits)
        if before_input != digest((shared, receipts, task)):
            raise ValueError("Candidate mutated shared inputs")
        post_lineage = [row["evidence_id"] for row in shared]
        outputs = {}
        for arm, context in zip("AB", (a, b)):
            validate_context(store, task, context)
            ordered = [row["evidence_id"] for row in context]
            if (
                ordered != [rid for rid in post_lineage if rid in ordered]
                or len(ordered) > limits["max_citations"]
                or len(json.dumps(context, sort_keys=True).encode()) > limits["max_bytes"]
            ):
                raise ValueError("Selected context violated order or budget")
            outputs[arm] = baseline.public_response(task, context, receipts)
        if before != database_digest(path):
            raise ValueError("Ledger changed")
    return native_ids, post_lineage, outputs


def replay():
    cases, labels = fixtures()
    if tuple(map(digest, (cases, labels))) != PINS:
        raise ValueError("Fixture drift")
    for name, pin in MODULE_PINS.items():
        if sha256(Path(__file__).with_name(name + ".py").read_bytes()).hexdigest() != pin:
            raise ValueError(f"Source drift: {name}")
    old_cases = prior_fixtures()[0]
    for field in ("id", "scope", "source"):
        old = {row[field] for case in old_cases for row in case["observations"]}
        if any(row[field] in old for case in cases for row in case["observations"]):
            raise ValueError(f"Reused source field: {field}")

    results, controls = [], []
    for case in cases:
        native, lineage, responses = compare(case)
        expected = labels[case["id"]]
        scores, arms = {}, {}
        for arm, response in responses.items():
            action = response["decision"]["action"]
            scores[arm] = score(action, expected)
            arms[arm] = dict(
                decision=response["decision"],
                latest_original_slots=response["latest_original_slots"],
                selection=[row["evidence_id"] for row in response["context"]],
                bytes=len(json.dumps(response["context"], sort_keys=True).encode()),
            )
        changed = None
        if arms["A"]["decision"]["action"] != arms["B"]["decision"]["action"]:
            changed = {}
            for name, arm, other in (("entered", "B", "A"), ("left", "A", "B")):
                changed[name] = [
                    dict(
                        id=row["evidence_id"],
                        assertion=json.loads(row["preview"]),
                        observed_at=row["observed_at"],
                        original_slot=case["receipts"].get(row["evidence_id"]),
                    )
                    for row in responses[arm]["context"]
                    if row["evidence_id"] not in arms[other]["selection"]
                ]
        results.append(
            dict(
                id=case["id"],
                family=case["family"],
                pressure=case["pressure"],
                decisive=case["decisive"],
                expected=expected,
                native=native,
                lineage=lineage,
                shared_receipts=case["receipts"],
                arms=arms,
                scores=scores,
                changed=changed,
            )
        )
        if case["pressure"] == "high" and case["family"] in {
            "newer_block",
            "clear_quorum",
            "concurrent_conflict",
        }:
            absent = compare(case, "absent")[2]
            for mode in CONTROLS:
                output = absent if mode == "absent" else compare(case, mode)[2]
                controls.append(
                    dict(
                        case=case["id"],
                        mode=mode,
                        equal={arm: output[arm] == absent[arm] for arm in "AB"},
                        public_hash={arm: digest(output[arm]) for arm in "AB"},
                    )
                )

    summary = summarize(results)
    transitions = summary["transitions"]
    lost = sum(r["scores"]["A"]["correct"] and not r["scores"]["B"]["correct"] for r in results)
    privacy = all(all(row["equal"].values()) for row in controls)
    passed = (
        transitions["unsafe"]["corrected"] > 0
        and transitions["unsafe"]["introduced"] == lost == 0
        and all(
            summary["totals"]["B"][metric] < summary["totals"]["A"][metric]
            for metric in ("missed_stop", "unnecessary_hold")
        )
        and summary["paired"]["correct"][1] > 0
        and privacy
    )
    return dict(
        pins=PINS,
        module_pins=MODULE_PINS,
        summary=summary,
        correct_lost=lost,
        pressure={
            p: summarize([r for r in results if r["pressure"] == p]) for p in ("low", "high")
        },
        gate_passed=passed,
        privacy_passed=privacy,
        rows=results,
        controls=controls,
    )


if __name__ == "__main__":
    print(json.dumps(replay(), sort_keys=True, separators=(",", ":")))
