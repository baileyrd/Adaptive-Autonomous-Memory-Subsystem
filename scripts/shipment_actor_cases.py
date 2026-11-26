"""Separate qualification and held-out shipment inputs for the offline actor."""

import json
from hashlib import sha256


def qualification():
    return [
        ("q01", "proceed", [(2, "clear", "north"), (2, "clear", "west")]),
        ("q02", "stop", [(1, "clear", "east"), (1, "clear", "west"), (2, "blocked", None)]),
        ("q03", "abstain", [(4, "clear", "east"), (4, "blocked", None), (4, "clear", "west")]),
        ("q04", "stop", [(5, "blocked", "north"), (3, "clear", "south")]),
        ("q05", "abstain", [(2, "blocked", "west"), (2, "clear", "north")]),
        ("q06", "proceed", [(2, "blocked", "west"), (3, "clear", "north"), (3, "clear", "south")]),
    ]


EXPECTED = {
    "buried_block": "stop",
    "buried_conflict": "abstain",
    "buried_receipt": "proceed",
    "in_budget_block": "stop",
    "linked_release": "proceed",
    "sparse_conflict": "abstain",
}


def held_out():
    cases, expected = [], {}
    for family, gold in EXPECTED.items():
        for i in range(4):
            case_id = sha256(f"actor-125-fresh/{family}/{i}".encode()).hexdigest()[:14]
            topic, scope = "actor-load-" + case_id, "actor-dock-" + case_id
            task = dict(
                id=case_id, topic=topic, scope=scope, checks=["seal"], day=7, as_of=8, allowed=True
            )
            records, receipts, links = [], {}, []

            def add(order, timestamp, state, slot=None):
                rid = f"{case_id}-{order:02}"
                records.append(
                    dict(
                        id=rid,
                        scope=scope,
                        source=rid,
                        observed=timestamp,
                        recorded=timestamp + 1,
                        text=json.dumps(
                            dict(topic=topic, check="seal", state=state), sort_keys=True
                        ),
                    )
                )
                if slot:
                    receipts[rid] = slot
                return rid

            first = add(0, 3, "clear", "west")
            release = family in {"buried_receipt", "linked_release"}
            if not release:
                add(1, 3, "clear", "east")
            if release:
                decisive = add(90, 3, "clear", "south")
            else:
                concurrent = family in {"buried_conflict", "sparse_conflict"}
                decisive = add(
                    4 if family == "in_budget_block" else 90,
                    3 if concurrent else 5,
                    "blocked",
                    "north" if i % 2 else None,
                )
            for c in range(i % 2 if family == "sparse_conflict" else 9 + i):
                child = add(10 + c, 3, "clear")
                if family == "linked_release" or (c == 0 and i % 2 == 0):
                    links.append(
                        dict(
                            child=child,
                            parent=first,
                            scope=scope,
                            principal="pilot",
                            granted=True,
                            recorded=5,
                            effective=4,
                        )
                    )
            cases.append(
                dict(
                    id=case_id,
                    family=family,
                    task=task,
                    observations=records,
                    receipts=receipts,
                    links=links,
                    decisive=decisive,
                )
            )
            expected[case_id] = gold
    return cases, expected
