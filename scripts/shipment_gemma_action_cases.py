"""Fresh paired action-only versus action-and-citation histories."""


def cases():
    return [
        (
            "p01",
            0,
            [
                (1, "blocked", "arch-old"),
                (4, "clear", "arch-a"),
                (4, "clear", None),
                (4, "clear", "arch-b"),
            ],
            (2, 3, 4),
        ),
        (
            "p02",
            2,
            [(2, "clear", "gate-old"), (7, "blocked", "gate-a"), (7, "blocked", None)],
            (2, 3),
        ),
        (
            "p03",
            1,
            [(6, "blocked", None), (6, "clear", "shed-a"), (3, "clear", "shed-old")],
            (1, 2),
        ),
        (
            "p04",
            1,
            [
                (8, "clear", "ramp-a"),
                (8, "clear", "ramp-a"),
                (8, "clear", "ramp-b"),
                (7, "blocked", None),
            ],
            (1, 2, 3),
        ),
        (
            "p05",
            0,
            [(4, "clear", "field-a"), (4, "clear", "field-b"), (9, "blocked", "field-c")],
            (3,),
        ),
        (
            "p06",
            2,
            [
                (2, "blocked", "bay-old"),
                (8, "clear", "bay-a"),
                (8, "blocked", "bay-b"),
                (8, "clear", "bay-c"),
            ],
            (2, 3, 4),
        ),
    ]
