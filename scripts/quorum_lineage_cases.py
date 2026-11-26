"""Fresh synthetic histories and separately scored outcome labels for #125."""

import json
from hashlib import sha256

EXPECTED = {
    "dual": "proceed",
    "nested": "proceed",
    "overlap": "proceed",
    "single": "abstain",
    "conflict": "abstain",
    "missing": "abstain",
    "partial": "abstain",
    "unknown": "abstain",
}


def fixtures():
    cases, labels = [], {}
    for family, expected in EXPECTED.items():
        for replica in range(4):
            key = sha256(f"freight-125-quorum/{family}/{replica}".encode()).hexdigest()[:14]
            scope, topic = "quorum-dock-" + key, "quorum-load-" + key
            task = dict(id=key, scope=scope, topic=topic, checks=["seal"], day=6, as_of=6, allowed=True)
            records, receipts, links = [], {}, []

            def record(order, *, slot=None, state="clear"):
                rid = f"{key}-{order}"
                records.append(
                    dict(
                        id=rid,
                        scope=scope,
                        source=rid,
                        observed=2,
                        recorded=2,
                        text=json.dumps(dict(topic=topic, check="seal", state=state), sort_keys=True),
                    )
                )
                if slot is not None:
                    receipts[rid] = slot
                return rid

            def link(child, parent):
                links.append(
                    dict(
                        child=child, parent=parent, scope=scope, principal="pilot",
                        granted=True, recorded=4, effective=3,
                    )
                )

            a = record("10", slot="first") if family != "unknown" else record("10")
            b = record("20", slot="second" if family in {"dual", "nested", "overlap", "conflict"} else None)
            report = record("05" if replica % 2 else "30")
            if family in {"dual", "nested", "overlap", "conflict", "partial"}:
                link(report, a)
                link(report, b if family != "partial" else key + "-missing")
            if family == "nested":
                parent = report
                for index in range(2 + replica):
                    child = record(f"4{index}")
                    link(child, parent)
                    parent = child
            if family == "overlap":
                c = record("25", slot="third")
                sibling = record("06")
                link(sibling, b)
                link(sibling, c)
            if family == "single":
                link(b, a)
                link(report, a)
                for index in range(8 + replica):
                    link(record(f"4{index}"), a)
            if family == "conflict":
                link(record("60", state="blocked"), a)
            if family == "missing":
                # Multiple true copies of the first inspection with no visible lineage.
                for index in range(replica):
                    record(f"4{index}")

            cases.append(dict(id=key, family=family, tasks=[task], observations=records,
                              receipts=receipts, links=links))
            labels[key] = dict(expected=expected, originals=sorted(receipts))
    return cases, labels


def overlays(case):
    """Expose the same two links under matched authorization/cutoff changes."""
    links = case["links"]
    return {
        "visible": links,
        "absent": [],
        "restricted": [{**edge, "granted": False} for edge in links],
        "other_reader": [{**edge, "principal": "other"} for edge in links],
        "other_scope": [{**edge, "scope": "other"} for edge in links],
        "future_recording": [{**edge, "recorded": 7} for edge in links],
        "future_effective": [{**edge, "effective": 7} for edge in links],
        "missing_endpoint": [{**edge, "parent": case["id"] + "-missing"} for edge in links],
    }
