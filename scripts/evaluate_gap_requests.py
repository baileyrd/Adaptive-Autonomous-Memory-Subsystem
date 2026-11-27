"""Offline paired knowledge-gap request experiment under #128."""

import json
import tempfile
from collections import Counter
from hashlib import sha256
from pathlib import Path

from aams.recall import CognitiveMemory, CognitiveNeed
from aams.storage import AccessContext, SQLiteMemoryStore
from cognitive_task_cases import digest
from evaluate_cognitive_tasks import database_digest
from evaluate_learning import seed
from gap_request_cases import fixtures

PINS = (
    "6f98ac17738f0baf33f03d003166ec1fcd70b712ff6872af81e3502ab56f82e3",
    "8536fb0e0da3ba5d36dc6ca6dce9a9b3b9d17f18b3f92e23cf0dc44f2281f113",
)
ACTIONS = {"pass": "enable", "fail": "withhold"}
BUDGET = dict(max_items=2, max_bytes=4096)


def reading_matches(task, reading):
    payload = reading["payload"]
    return (
        reading["id"] == task["observation_id"]
        and reading["scope"] == task["scope"]
        and reading["producer"] == "meter"
        and payload.get("kind") == "accuracy_reading"
        and payload.get("instrument") == task["instrument"]
        and payload.get("round") == task["round"]
        and payload.get("status") in ACTIONS
    )


def decision(task, readings):
    for reading in readings:
        if reading_matches(task, reading):
            return dict(
                action=ACTIONS[reading["payload"]["status"]],
                citations=[{"id": reading["id"], "digest": reading["digest"]}],
            )
    return dict(action="abstain", citations=[])


def request_for(task, manifest):
    payload = manifest["payload"]
    if (
        manifest["scope"] != task["scope"]
        or manifest["producer"] != "bench-clerk"
        or payload
        != dict(
            kind="verification_task",
            query=task["query"],
            instrument=task["instrument"],
            round=task["round"],
            observation_id=task["observation_id"],
        )
    ):
        return None
    return dict(
        observation=dict(
            id=task["observation_id"],
            kind="accuracy_reading",
            instrument=task["instrument"],
            round=task["round"],
        ),
        basis=dict(id=manifest["id"], digest=manifest["digest"]),
        uncertainty="The current accuracy reading is unavailable in the decision packet.",
        could_change=dict(from_action="abstain", pass_to="enable", fail_to="withhold"),
    )


def canonical(row):
    return dict(
        id=row.evidence_id,
        scope=row.scope,
        producer=row.producer,
        payload=json.loads(row.payload),
        digest=row.digest,
    )


def review_ticket(store, access, task, request, inbox):
    work = Counter(tickets=1, manifest_checks=1)
    if access.scope != task["scope"]:
        return "rejected_request", None, work
    basis = store.get_evidence(access, request["basis"]["id"])
    if basis is None or request_for(task, canonical(basis)) != request:
        return "rejected_request", None, work
    work["observation_lookups"] += 1
    row = store.get_evidence(access, request["observation"]["id"])
    if row is not None:
        entry = canonical(row)
        if reading_matches(task, entry):
            return "recovered", entry, work

    work["inbox_checks"] += 1
    if inbox is None:
        return "no_receipt", None, work
    if not reading_matches(task, inbox):
        return "ineligible_receipt", None, work
    payload = json.dumps(inbox["payload"], sort_keys=True).encode()
    return "supplied", {**inbox, "digest": "sha256:" + sha256(payload).hexdigest()}, work


def run_case(case, path, foreign=False):
    task = case["task"]
    store = SQLiteMemoryStore(path)
    rows = list(case["rows"])
    if foreign:
        rows.append(case["foreign_shadow"])
    seed(store, {"evidence": rows})
    access = AccessContext("fixture-reader", task["scope"])
    before = database_digest(path)
    if foreign:
        foreign_scope = case["foreign_shadow"][1]
        if (
            store.get_evidence(access, task["observation_id"]) is not None
            or store.get_evidence(
                AccessContext("fixture-reader", foreign_scope), task["observation_id"]
            )
            is None
        ):
            raise ValueError("Foreign fixture failed its scope control")
    recalled = CognitiveMemory(store).recall(access, CognitiveNeed(query=task["query"], **BUDGET))
    if recalled["truncated"]:
        raise ValueError("Unexpected fixture truncation")
    packet = [
        dict(
            id=citation["evidence_id"],
            scope=access.scope,
            producer=citation["producer"],
            payload=json.loads(citation["preview"]),
            digest=citation["digest"],
        )
        for item in recalled["items"]
        for citation in item["citations"]
    ]
    initial = decision(task, packet)
    queue = []
    if initial["action"] == "abstain":
        request = next((request for row in packet if (request := request_for(task, row))), None)
        if request is not None:
            queue.append(request)

    a = dict(initial={**initial, "request": None}, final={**initial, "request": None})
    b_initial = {**initial, "request": queue[0] if queue else None}
    b_final = b_initial
    route, handoff, work = "no_request", None, {}
    for request in queue:
        route, handoff, work = review_ticket(store, access, task, request, case["inbox"])
        b_final = {**decision(task, [handoff] if handoff is not None else []), "request": request}
    if before != database_digest(path):
        raise ValueError("Review mutated canonical memory")
    return dict(
        packet=packet,
        public=dict(A=a, B={"initial": b_initial, "final": b_final}),
        route=route,
        handoff=handoff,
        work=work,
    )


def validate_support(task, result, readings):
    action = result["action"]
    if action == "abstain":
        return
    supported = [
        {"id": row["id"], "digest": row["digest"]}
        for row in readings
        if reading_matches(task, row) and ACTIONS[row["payload"]["status"]] == action
    ]
    citations = result["citations"]
    if not citations or any(citation not in supported for citation in citations):
        raise ValueError("Unsupported substantive action")


def validate_case_support(task, outcome):
    packet = outcome["packet"]
    for arm, result in outcome["public"].items():
        validate_support(task, result["initial"], packet)
        available = packet
        if (
            arm == "B"
            and outcome["route"] in {"recovered", "supplied"}
            and outcome["handoff"] is not None
        ):
            available = [*packet, outcome["handoff"]]
        validate_support(task, result["final"], available)


def summarize(rows):
    correct = {arm: sum(r["scores"][arm]["correct"] for r in rows) for arm in "AB"}
    incomplete = {arm: sum(r["scores"][arm]["incomplete"] for r in rows) for arm in "AB"}
    wrong = {arm: sum(r["scores"][arm]["wrong"] for r in rows) for arm in "AB"}
    routes = Counter(r["route"] for r in rows)
    work = Counter()
    for row in rows:
        work.update(row["work"])
    return dict(
        cases=len(rows),
        correct=correct,
        incomplete=incomplete,
        wrong=wrong,
        improved=sum(not r["scores"]["A"]["correct"] and r["scores"]["B"]["correct"] for r in rows),
        worsened=sum(r["scores"]["A"]["correct"] and not r["scores"]["B"]["correct"] for r in rows),
        actions_unchanged=sum(
            r["public"]["A"]["final"]["action"] == r["public"]["B"]["final"]["action"] for r in rows
        ),
        unnecessary_requests=routes["recovered"],
        uncertainty_resolved=routes["recovered"] + routes["supplied"],
        routes=routes,
        reviewer_work=work,
    )


def replay():
    cases, labels = fixtures()
    if tuple(map(digest, (cases, labels))) != PINS:
        raise ValueError("Fixture drift")
    rows, shadows = [], []
    with tempfile.TemporaryDirectory(prefix="gap128-") as directory:
        root = Path(directory)
        for case in cases:
            task = case["task"]
            outcome = run_case(case, root / (task["id"] + ".db"))
            validate_case_support(task, outcome)
            label = labels[task["id"]]
            scores = {}
            for arm, result in outcome["public"].items():
                if result["initial"]["action"] != label["initial"]:
                    raise ValueError("Frozen initial eligibility mismatch")
                final = result["final"]
                action = final["action"]
                scores[arm] = dict(
                    correct=action == label["expected"],
                    incomplete=action == "abstain",
                    wrong=action not in {"abstain", label["expected"]},
                )
            rows.append(dict(task=task, **label, **outcome, scores=scores))
            if case["foreign_shadow"] is not None:
                comparison = run_case(case, root / (task["id"] + "-shadow.db"), foreign=True)
                validate_case_support(task, comparison)
                if any(
                    comparison[field] != outcome[field]
                    for field in ("public", "packet", "work", "route")
                ):
                    raise ValueError("Foreign-only evidence changed observed response")
                shadows.append(
                    dict(
                        id=task["id"],
                        absent_public=outcome["public"],
                        foreign_public=comparison["public"],
                        packet_sha256=digest(comparison["packet"]),
                        work=comparison["work"],
                    )
                )
    return dict(pins=PINS, budget=BUDGET, summary=summarize(rows), rows=rows, shadows=shadows)


if __name__ == "__main__":
    print(json.dumps(replay(), sort_keys=True, separators=(",", ":")))
