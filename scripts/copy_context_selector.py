"""Eval-only declared-copy diversity. No oracle, adverse labels or serving integration."""

import json


def copy_key(row):
    # This is an exact declared-origin/content/time group, NOT proof of independence.
    return tuple(row[name] for name in ("source_actor", "source_locator", "digest", "observed_at"))


def select_context(candidates, *, max_citations, max_bytes):
    """Input must already pass canonical scope/time/provenance validation; retain BM25 order."""
    selected, groups = [], set()
    for row in candidates:
        key = copy_key(row)
        if key in groups:
            continue
        trial = [*selected, row]
        if (
            len(trial) > max_citations
            or len(json.dumps(trial, sort_keys=True).encode()) > max_bytes
        ):
            break
        selected = trial
        groups.add(key)
    return selected
