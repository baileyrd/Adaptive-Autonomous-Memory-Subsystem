"""Frozen source-disjoint synthetic histories. Origin labels are evaluator-only."""

import json
from hashlib import sha256

FAMILIES = (
    "exact_failure",
    "alias_failure",
    "paraphrase_failure",
    "derived_failure",
    "independent_clear",
    "same_time_dispute",
    "recovered",
    "long_history",
    "delayed_failure",
    "missing_check",
)


def cases():
    episodes = []
    for family in FAMILIES:
        for replica in range(4):
            identifier = sha256(f"factorial:121:{family}:{replica}".encode()).hexdigest()[:14]
            topic, scope = "unit" + identifier, "lab" + identifier
            rows = []
            initial = "blocked" if family == "recovered" else "clear"

            def add(name, state, day, recorded, source, origin, check="seal", target=scope):
                rows.append(
                    dict(
                        id=f"{identifier}-{name}",
                        scope=target,
                        observed=day,
                        recorded=recorded,
                        source=identifier + source,
                        origin=identifier + origin,
                        text=json.dumps(
                            dict(topic=topic, check=check, state=state), sort_keys=True
                        ),
                    )
                )

            add("initial", initial, 1, 1, "p00", "p00")
            count = (108 if family == "long_history" else 10) + replica
            for i in range(count):
                alias = f"p{i + 1:02}"
                distinct = family in ("alias_failure", "derived_failure", "independent_clear")
                add(
                    f"a{i:03}",
                    initial,
                    1,
                    2,
                    alias if distinct else "p00",
                    alias if family == "independent_clear" else "p00",
                )
                if family == "derived_failure":
                    rows[-1]["text"] += " " * (1 + i % 3)
                if family == "paraphrase_failure":
                    rows[-1]["text"] = (
                        f"{topic} seal inspection passed according to the initial log."
                    )
            changes = family not in ("independent_clear", "missing_check")
            world = [dict(day=1, check="seal", clear=initial == "clear")]
            if changes:
                day = 1 if family == "same_time_dispute" else 3
                state = "clear" if family == "recovered" else "blocked"
                world.append(dict(day=day, check="seal", clear=state == "clear"))
                add("update", state, day, 5 if family == "delayed_failure" else 3, "p99", "p99")
            checks = ["seal"]
            if family == "missing_check":
                checks.append("load")
                world.append(dict(day=1, check="load", clear=False))
            add("foreign", "blocked", 1, 1, "p98", "p98", target="other" + scope)
            add("future", "blocked", 8, 8, "p97", "p97")
            tasks = [
                dict(
                    id=f"{identifier}-{label}",
                    topic=topic,
                    scope=scope,
                    checks=checks,
                    day=day,
                    as_of=cutoff,
                )
                for label, day, cutoff in (("then", 2, 6), ("pending", 4, 4), ("now", 6, 6))
            ]
            episodes.append(
                dict(
                    id=identifier,
                    family=family,
                    split="heldout",
                    tasks=tasks,
                    observations=rows,
                    world=world,
                )
            )
    return episodes
