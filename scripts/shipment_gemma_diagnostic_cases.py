"""Fresh diagnostic histories with hand-checked current row IDs."""


def cases():
    return [
        (
            "d01",
            [
                (2, "blocked", "berth-old"),
                (5, "clear", "berth-a"),
                (5, "clear", None),
                (5, "clear", "berth-b"),
            ],
            (2, 3, 4),
        ),
        (
            "d02",
            [
                (4, "clear", "pad-a"),
                (6, "blocked", None),
                (4, "clear", "pad-b"),
                (6, "blocked", "pad-c"),
            ],
            (2, 4),
        ),
        (
            "d03",
            [
                (7, "clear", "lane-a"),
                (7, "blocked", "lane-b"),
                (7, "clear", None),
                (3, "clear", "lane-old"),
            ],
            (1, 2, 3),
        ),
        (
            "d04",
            [
                (8, "clear", "rack-a"),
                (8, "clear", "rack-a"),
                (8, "clear", "rack-b"),
                (6, "blocked", "rack-old"),
            ],
            (1, 2, 3),
        ),
        (
            "d05",
            [
                (7, "clear", "line-a"),
                (7, "clear", "line-b"),
                (9, "blocked", "line-c"),
                (7, "clear", None),
            ],
            (3,),
        ),
        (
            "d06",
            [
                (1, "blocked", "row-old"),
                (8, "blocked", None),
                (8, "clear", "row-a"),
                (8, "clear", "row-b"),
            ],
            (2, 3, 4),
        ),
    ]
