"""Held-out paired shipment histories and separate scoring keys."""

import json
from hashlib import sha256

KEY = {
    "newer_block": "stop",
    "concurrent_conflict": "abstain",
    "clear_quorum": "proceed",
    "superseded_block": "proceed",
    "stale_receipt": "abstain",
    "early_block": "stop",
}
CONTROLS = ("absent", "withheld", "foreign", "recorded_late", "effective_late")


def fixtures():
    cases, labels = [], {}
    for family, expected in KEY.items():
        for repeat in range(4):
            for pressure in ("low", "high"):
                case_id = sha256(f"witness-125/{family}/{repeat}/{pressure}".encode()).hexdigest()[
                    :14
                ]
                scope, topic = f"witness-dock-{case_id}", f"witness-load-{case_id}"
                task = dict(
                    id=case_id,
                    topic=topic,
                    scope=scope,
                    checks=["seal"],
                    day=6,
                    as_of=6,
                    allowed=True,
                )
                records, receipts, links = [], {}, []

                def add(order, day, state, slot=None):
                    rid = f"{case_id}-{order:02}"
                    records.append(
                        dict(
                            id=rid,
                            scope=scope,
                            source=rid,
                            observed=day,
                            recorded=day,
                            text=json.dumps(
                                dict(topic=topic, check="seal", state=state), sort_keys=True
                            ),
                        )
                    )
                    if slot is not None:
                        receipts[rid] = slot
                    return rid

                first_state = "blocked" if family == "superseded_block" else "clear"
                first = add(0, 2, first_state, "west")
                if family in {"newer_block", "concurrent_conflict", "early_block", "stale_receipt"}:
                    add(1, 2, "clear", "east")
                if family == "superseded_block":
                    add(80, 4, "clear", "north")
                if family in {"clear_quorum", "superseded_block", "stale_receipt"}:
                    decisive = add(90, 2 if family == "clear_quorum" else 4, "clear", "south")
                else:
                    decisive = add(
                        3 if family == "early_block" else 90,
                        2 if family == "concurrent_conflict" else 4,
                        "blocked",
                        "north" if repeat % 2 == 0 else None,
                    )
                for i in range(2 + repeat % 2 if pressure == "low" else 9 + repeat):
                    child = add(10 + i, 2, first_state)
                    if i == 0 and repeat % 2 == 0:
                        links.append(
                            dict(
                                child=child,
                                parent=first,
                                scope=scope,
                                principal="pilot",
                                granted=True,
                                recorded=3,
                                effective=3,
                            )
                        )
                cases.append(
                    dict(
                        id=case_id,
                        family=family,
                        pressure=pressure,
                        task=task,
                        observations=records,
                        receipts=receipts,
                        links=links,
                        decisive=decisive,
                    )
                )
                labels[case_id] = expected
    return cases, labels
