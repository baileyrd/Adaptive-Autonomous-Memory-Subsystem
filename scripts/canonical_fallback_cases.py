"""Frozen disposable episode inputs and simulator labels for the #124 fallback comparison."""

import json
from copy import deepcopy

from checkpoint_recovery_cases import RECIPE, cases, day, digest, oracle

FAMILIES = (
    "ready",
    "expired",
    "superseded",
    "revoked_checkpoint",
    "changed_constraints",
    "fabricated_progress",
    "cross_scope_ref",
    "missing_candidate",
    "foreign_candidate",
    "revoked_access",
    "revoked_between",
    "contradictory_state",
    "head_after_cutoff",
    "reader_without_owner",
)
ARMS = ("checkpoint", "fallback", "canonical")


def episodes() -> list[dict]:
    """Generate matched inputs using new seed-derived identities and a second host snapshot."""
    recipe = json.loads(RECIPE.read_text())
    recipe.update(
        seed=2026112402, families=FAMILIES, episodes_per_family={"design": 2, "heldout": 4}
    )
    batch = cases(recipe)
    for e in batch:
        host, cp, family = e["authority"], e["checkpoint"], e["family"]
        host["owner"] = host["principal"]
        entry = host["registry"][cp["checkpoint_id"]]
        entry["registered_at"] = day(3)
        if family in ("revoked_between", "reader_without_owner"):
            cp["expires_at"] = day(5)
        if family == "reader_without_owner":
            host["owner"] = "owner-" + e["id"]
        if family == "foreign_candidate":
            cp["scope"] = "private124-" + e["id"]
        if family == "head_after_cutoff":
            host["as_of"] = day(2)
        entry["digest"] = digest(cp)
        e["fresh"] = deepcopy(host)
        if family == "revoked_between":
            e["fresh"]["allowed"] = False
        e["expected"] = oracle({**e, "authority": e["fresh"]})
    return batch


def identities(batch: list[dict]) -> set[str]:
    """Collect source, task, scope, evidence and checkpoint identities for overlap checks."""
    ids = set()
    for e in batch:
        ids.update((e["authority"]["task_id"], e["checkpoint"]["checkpoint_id"]))
        for row in e["records"]:
            ids.update(row[k] for k in ("id", "scope", "source_actor", "source_locator"))
    return ids


def check_separation(batch: list[dict]) -> None:
    """Compare design and held-out inputs, and both against the complete #130 generator."""
    design = identities([e for e in batch if e["split"] == "design"])
    heldout = identities([e for e in batch if e["split"] == "heldout"])
    previous = identities(cases(json.loads(RECIPE.read_text())))
    if design & heldout or (design | heldout) & previous:
        raise ValueError("Overlapping fixture identities")
