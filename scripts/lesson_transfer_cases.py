"""Frozen training configurations and independently keyed transfer histories."""

FIELDS = ("items", "capacity", "occupied", "drain", "deadline")

# Separate prior work cells. The held-out families are absent from both.
SOURCES = (
    ("prior-a", "archive-reader", (8, 5, 3, 3, 9)),
    ("prior-b", "parcel-feed", (10, 6, 3, 2, 11)),
)

# Each unseen family contributes two unseen overloads, an exact operating-point
# control, a higher-headroom reversal and a smaller-job reversal.
FAMILIES = {
    "microscope-slides": (
        (6, 4, 3, 2, 8),
        (7, 6, 4, 3, 9),
        SOURCES[0][2],
        (8, 6, 2, 4, 9),
        (2, 5, 3, 4, 5),
    ),
    "library-cart-sorting": (
        (9, 5, 2, 2, 11),
        (11, 7, 5, 3, 13),
        SOURCES[1][2],
        (9, 8, 4, 4, 10),
        (3, 7, 4, 5, 6),
    ),
    "plant-tray-counting": (
        (7, 5, 4, 3, 9),
        (10, 8, 5, 2, 12),
        SOURCES[0][2],
        (10, 7, 3, 4, 11),
        (2, 4, 2, 4, 4),
    ),
    "label-printing": (
        (8, 7, 5, 2, 10),
        (6, 6, 3, 3, 8),
        SOURCES[1][2],
        (7, 6, 1, 4, 8),
        (3, 6, 3, 5, 5),
    ),
}
CONDITIONS = ("unseen_overload", "unseen_overload", "exact_overload", "wide_headroom", "short_job")
KEY = ("paced", "paced", "paced", "direct", "direct")

# Written from the two long-batch source cases. Its headroom guard uses the
# nominal burst rate and does not account for a job smaller than that rate.
LESSON = {
    "action": "paced",
    "conditions": [
        ["headroom", "lt", 4],
        ["deadline_slack", "ge", 0],
        ["drain", "ge", 1],
    ],
}


def held_out():
    cases, keys = [], {}
    for family, configurations in FAMILIES.items():
        for index, (values, condition) in enumerate(zip(configurations, CONDITIONS, strict=True)):
            case_id = f"{family}-{index + 1}"
            task = dict(workload=family, configuration=dict(zip(FIELDS, values, strict=True)))
            cases.append(dict(id=case_id, family=family, condition=condition, task=task))
            keys[case_id] = KEY[index]
    return cases, keys
