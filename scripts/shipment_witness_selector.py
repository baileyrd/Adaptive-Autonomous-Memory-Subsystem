"""Offline final citation selection for the single-seal shipment rule."""

import json

from copy_context_selector import select_context


def select_witnesses(rows, *, task, receipts, max_citations, max_bytes):
    claims = {}
    for row in rows:
        try:
            fact = json.loads(row["preview"])
        except (ValueError, TypeError):
            continue
        if (
            isinstance(fact, dict)
            and set(fact) == {"topic", "check", "state"}
            and (fact["topic"], fact["check"]) == (task["topic"], "seal")
            and fact["state"] in ("clear", "blocked")
        ):
            claims[row["evidence_id"]] = (row, fact["state"])

    witnesses = []
    if claims:
        newest = max(row["observed_at"] for row, _ in claims.values())
        states, slots = {}, {}
        for rid, (row, state) in claims.items():
            if row["observed_at"] == newest:
                states.setdefault(state, rid)
                if state == "clear" and rid in receipts:
                    slots.setdefault(receipts[rid], rid)
        witnesses = (
            list(slots.values())[:2]
            if set(states) == {"clear"} and slots
            else list(states.values())
        )

    priority = set(witnesses)
    ordered = [row for row in rows if row["evidence_id"] in priority]
    ordered.extend(row for row in rows if row["evidence_id"] not in priority)
    included = {
        row["evidence_id"]
        for row in select_context(ordered, max_citations=max_citations, max_bytes=max_bytes)
    }
    return [row for row in rows if row["evidence_id"] in included]
