"""Fresh full-evidence cases for the unchanged shipment qualification rule."""


def qualification():
    return [
        ("g01", "stop", [(3, "clear", "bay-a"), (3, "clear", "bay-b"), (5, "blocked", None)]),
        ("g02", "proceed", [(5, "clear", "pier-a"), (5, "clear", None), (5, "clear", "pier-b")]),
        ("g03", "abstain", [(4, "clear", None), (4, "blocked", "dock-b"), (2, "clear", "dock-a")]),
        ("g04", "proceed", [(2, "blocked", None), (6, "clear", "yard-a"), (6, "clear", "yard-b")]),
        ("g05", "abstain", [(7, "blocked", None), (7, "clear", "gate-a"), (7, "clear", "gate-b")]),
        ("g06", "stop", [(6, "blocked", "ramp-a"), (4, "clear", "ramp-b"), (6, "blocked", None)]),
    ]
