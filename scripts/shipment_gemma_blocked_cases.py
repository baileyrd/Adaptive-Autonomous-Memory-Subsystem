"""Fresh paired predicate/action cases with checked latest observation IDs."""


def cases():
    return [
        (
            "u01",
            False,
            "PA",
            [(3, "clear", "moor-a"), (8, "blocked", "moor-b"), (8, "blocked", None)],
            (2, 3),
        ),
        (
            "u02",
            False,
            "AP",
            [(3, "blocked", "mill-old"), (7, "clear", "mill-a"), (7, "clear", "mill-b")],
            (2, 3),
        ),
        ("u03", True, "AP", [(5, "clear", "port-a"), (9, "blocked", None)], (2,)),
        (
            "u04",
            True,
            "PA",
            [(4, "blocked", "rail-a"), (4, "clear", "rail-b"), (1, "clear", "rail-old")],
            (1, 2),
        ),
        (
            "u05",
            False,
            "AP",
            [(6, "blocked", "paddock-a"), (6, "blocked", "paddock-a"), (2, "clear", "paddock-old")],
            (1, 2),
        ),
        (
            "u06",
            True,
            "PA",
            [
                (6, "clear", "span-a"),
                (6, "clear", "span-a"),
                (6, "clear", "span-b"),
                (4, "blocked", None),
            ],
            (1, 2, 3),
        ),
        (
            "u07",
            True,
            "PA",
            [
                (7, "blocked", None),
                (7, "blocked", "lock-a"),
                (4, "clear", "lock-old"),
                (7, "blocked", "lock-b"),
            ],
            (1, 2, 4),
        ),
        (
            "u08",
            False,
            "AP",
            [
                (3, "blocked", None),
                (8, "clear", "silo-a"),
                (8, "clear", "silo-b"),
                (8, "blocked", "silo-c"),
            ],
            (2, 3, 4),
        ),
    ]
