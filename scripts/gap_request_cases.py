"""Frozen source records, independent reviewer inbox, and outside-memory scoring keys."""

import hashlib
import json

FAMILIES = ("balance", "photometer", "timer", "caliper")
MECHANISMS = (
    "visible",
    "missing_delivered",
    "overlooked",
    "missing_unavailable",
    "invalid_receipt",
)


def fixtures():
    cases, labels = [], {}
    for i, family in enumerate(FAMILIES):
        for j, mechanism in enumerate(MECHANISMS):
            key = hashlib.sha256(f"gap128/{family}/{j}".encode()).hexdigest()[:14]
            task = dict(
                id=key,
                scope="bench-" + key,
                query="ticket" + key,
                instrument="unit-" + key,
                round=6,
                observation_id="reading-" + key,
            )
            status = "pass" if (i + j) % 2 == 0 else "fail"
            manifest = {
                "kind": "verification_task",
                "query": task["query"],
                "instrument": task["instrument"],
                "round": task["round"],
                "observation_id": task["observation_id"],
            }
            reading = {
                "kind": "accuracy_reading",
                "instrument": task["instrument"],
                "round": task["round"],
                "status": status,
            }
            rows = [
                (
                    key + "-manifest",
                    task["scope"],
                    "bench-clerk",
                    "bench-register",
                    "fixture:manifest",
                    json.dumps(manifest, sort_keys=True),
                )
            ]
            if mechanism in {"visible", "overlooked"}:
                payload = {**reading, "query": task["query"]} if mechanism == "visible" else reading
                rows.append(
                    (
                        task["observation_id"],
                        task["scope"],
                        "meter",
                        "accuracy-meter",
                        "fixture:meter",
                        json.dumps(payload, sort_keys=True),
                    )
                )
            inbox = None
            if mechanism in {"missing_delivered", "invalid_receipt"}:
                inbox = dict(
                    id=task["observation_id"],
                    scope=task["scope"],
                    producer="meter",
                    payload=reading,
                )
                if mechanism == "invalid_receipt":
                    inbox = {**inbox, "payload": {**reading, "round": 5}}
            foreign_row = (
                task["observation_id"],
                "sealed-" + key,
                "meter",
                "accuracy-meter",
                "fixture:meter",
                json.dumps({**reading, "query": task["query"]}, sort_keys=True),
            )
            shadow = mechanism in {"missing_delivered", "missing_unavailable"}
            cases.append(
                dict(
                    task=task,
                    rows=rows,
                    inbox=inbox,
                    foreign_shadow=foreign_row if shadow else None,
                )
            )
            labels[key] = dict(
                family=family,
                mechanism=mechanism,
                expected="enable" if status == "pass" else "withhold",
                initial="enable"
                if mechanism == "visible" and status == "pass"
                else "withhold"
                if mechanism == "visible"
                else "abstain",
            )
    return cases, labels
