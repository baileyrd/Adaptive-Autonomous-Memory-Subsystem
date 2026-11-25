"""Disposable shipment-release histories, relationship sidecars and separate simulator keys."""

import json
from hashlib import sha256

from cognitive_task_cases import digest

# Expected actions predate retrieval. A conflict at the current time requires abstention.
KEY = {
    "alias": "stop",
    "chain": "stop",
    "independent": "proceed",
    "unknown": "proceed",
    "dispute": "abstain",
    "partial": "stop",
    "missing": "stop",
    "revoked": "abstain",
}
# Matched overlays on each missing-family history; never additional primary samples.
CONTROLS = (
    "visible",
    "absent",
    "private",
    "foreign",
    "late",
    "premature",
    "via_foreign",
    "via_late",
    "via_premature",
    "via_revoked",
    "via_missing",
)
DEFAULT = "primary"


def fixtures() -> tuple[list, dict]:
    """Generate histories and hidden origins; selection receives neither the key nor the family."""
    episodes, labels = [], {}
    for family, action in KEY.items():
        for replica in range(4):
            key = sha256(f"freight-125/{family}/{replica}".encode()).hexdigest()[:14]
            scope, topic = "dock" + key, "load" + key
            task = dict(
                id=key,
                topic=topic,
                scope=scope,
                checks=["seal"],
                day=6,
                as_of=6,
                allowed=family != "revoked",
            )
            records, origins, edges = [], {}, []

            def record(slot, state, observed, recorded, origin, *, foreign=False):
                rid = key + "-" + slot
                payload = json.dumps(dict(topic=topic, check="seal", state=state), sort_keys=True)
                records.append(
                    dict(
                        id=rid,
                        scope=("outer" + scope if foreign else scope),
                        observed=observed,
                        recorded=recorded,
                        source=rid,
                        text=payload,
                    )
                )
                origins[rid] = origin
                return rid

            def edge(child, parent):
                return dict(
                    child=child,
                    parent=parent,
                    scope=scope,
                    principal="pilot",
                    granted=True,
                    recorded=4,
                    effective=3,
                )

            shared = key + "/inspection"
            ids = []
            n = 3 + replica if family in {"independent", "dispute"} else 10 + replica
            for i in range(n):
                origin = f"{key}/independent/{i}" if family == "independent" else shared
                if family == "unknown":
                    origin = None
                rid = record(f"a{i:02}", "clear", 2, 2, origin)
                if i and family not in {"unknown", "independent"}:
                    if family != "partial" or i < 3:
                        edges.append(edge(rid, ids[-1] if family == "chain" else ids[0]))
                ids.append(rid)
            if family not in {"independent", "unknown"}:
                dispute = family == "dispute"
                blocked = record(
                    "z",
                    "blocked",
                    2 if dispute else 5,
                    5,
                    shared if dispute else key + "/new-inspection",
                )
                if dispute:
                    edges.append(edge(blocked, ids[0]))
            hidden = dict(
                via_foreign=record("x0", "clear", 2, 2, shared, foreign=True),
                via_late=record("x1", "clear", 2, 8, shared),
                via_premature=record("x2", "clear", 8, 2, shared),
                via_revoked=record("x3", "clear", 2, 2, shared, foreign=True),
                via_missing=key + "-nonexistent",
            )
            # Distinct in-scope withheld endpoint. The common host candidate gate excludes it.
            records[-1]["scope"] = scope
            withheld = [hidden["via_revoked"]]
            overlays = {DEFAULT: edges}
            if family == "missing":
                overlays = {DEFAULT: [], "visible": edges, "absent": []}
                for name, change in (
                    ("private", dict(granted=False)),
                    ("foreign", dict(scope="outer" + scope)),
                    ("late", dict(recorded=8)),
                    ("premature", dict(effective=8)),
                ):
                    overlays[name] = [{**e, **change} for e in edges]
                for name, hub in hidden.items():
                    overlays[name] = [edge(child, hub) for child in ids]
            episodes.append(
                dict(
                    id=key,
                    family=family,
                    tasks=[task],
                    observations=records,
                    links=overlays,
                    withheld=withheld,
                )
            )
            labels[key] = dict(expected=action, origins=origins)
    return episodes, labels


if __name__ == "__main__":
    print(*(digest(x) for x in fixtures()), sep="\n")
