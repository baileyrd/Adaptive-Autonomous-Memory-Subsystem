"""Fresh matched histories for literal yes/no inspection recognition."""


def pairs():
    # Row numbers are one-based; the bool runs the clear variant first.
    return [
        ("l01", [(3, "clear", "depot-old"), (7, "blocked", "depot-a")], (2,), 2, False, "AB"),
        ("l02", [(8, "blocked", None), (4, "blocked", "pier-old")], (1,), 1, True, "BA"),
        (
            "l03",
            [(4, "blocked", "yard-a"), (4, "blocked", None), (2, "clear", "yard-old")],
            (1, 2),
            2,
            False,
            "BA",
        ),
        (
            "l04",
            [
                (5, "blocked", "dock-a"),
                (5, "blocked", "dock-a"),
                (3, "clear", "dock-old"),
                (5, "blocked", "dock-b"),
            ],
            (1, 2, 4),
            4,
            True,
            "AB",
        ),
    ]
