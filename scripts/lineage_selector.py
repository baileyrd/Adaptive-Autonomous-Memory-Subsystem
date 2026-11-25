"""Disposable projection on an already authorized and validated native candidate window."""

from aams.storage import AccessContext
from cognitive_task_agent import INSTRUCTION, decide
from copy_context_selector import copy_key, select_context
from evaluate_semantic import timestamp


def components(store, task: dict, pool: list, links: list, withheld: set) -> dict:
    """Union only edges whose relation and both endpoint grants are current for this request."""
    if not task["allowed"]:
        return {}
    access = AccessContext("pilot", task["scope"])
    ids = {r["evidence_id"] for r in pool}
    parents = {}

    def visible(rid: str) -> bool:
        if rid not in ids or rid in withheld:
            return False
        ev = store.get_evidence(access, rid)
        return (
            ev is not None
            and ev.scope == task["scope"]
            and ev.recorded_at <= timestamp(task["as_of"])
            and ev.observed_at <= timestamp(task["day"])
        )

    def root(rid: str) -> str:
        while rid != parents[rid]:
            rid = parents[rid]
        return rid

    for edge in links:
        if (
            edge["granted"] is not True
            or edge["principal"] != access.principal
            or edge["scope"] != task["scope"]
            or edge["recorded"] > task["as_of"]
            or edge["effective"] > task["day"]
        ):
            continue
        child, parent = edge["child"], edge["parent"]
        if visible(child) and visible(parent):
            parents.setdefault(child, child)
            parents.setdefault(parent, parent)
            parents[root(child)] = root(parent)
    return {rid: root(rid) for rid in parents}


def respond(pool: list, task: dict, groups: dict) -> dict:
    """Preserve order and differing assertions; run the original selector and decision rule."""
    seen = set()
    ordered = []
    for row in pool:
        rid = row["evidence_id"]
        if rid in groups:
            assertion = (groups[rid], row["digest"], row["observed_at"])
            if assertion in seen:
                continue
            seen.add(assertion)
        ordered.append(row)
    context = select_context(ordered, max_citations=8, max_bytes=8192)
    request = dict(topic=task["topic"], checks=task["checks"], instruction=INSTRUCTION)
    decision = decide(request, context)
    counts = {
        ("linked", groups[r["evidence_id"]])
        if r["evidence_id"] in groups
        else ("declared", copy_key(r))
        for r in context
    }
    return dict(
        context=context,
        decision=decision,
        source_groups=len(counts),
        independent_pairs=[],
        independence="unverified",
    )
