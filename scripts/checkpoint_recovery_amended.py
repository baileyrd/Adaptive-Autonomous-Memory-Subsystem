"""Post-review disposable restore contract. The frozen experiment imports its original module."""

import json
from pathlib import Path

from aams.contracts import EvidenceStatus, utc_timestamp
from aams.storage import AccessContext, SQLiteMemoryStore
from checkpoint_recovery_cases import digest
from checkpoint_recovery_contract import (
    MAX_BYTES,
    MAX_REFS,
    authorized,
    canonical_state,
    normalize_state,
    reference,
    result,
    visible,
)


def rejection(status: str, access: AccessContext, authority: dict) -> dict:
    """Only the host-designated task owner may inspect detailed rejection reasons."""
    if access.principal != authority.get("owner"):
        return result("unavailable")
    return result(status)


def restore_path(
    path: Path, store: SQLiteMemoryStore, access: AccessContext, authority: dict
) -> dict:
    """Read one bounded sidecar after checking the current task grant."""
    # No file existence probe or canonical reference lookup before authorization.
    if not authorized(authority, access):
        return result("unavailable")
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return result("unavailable")
        checkpoint = json.loads(raw)
        return restore(checkpoint, store, access, authority)
    except (OSError, ValueError, TypeError, RecursionError):
        return result("unavailable")


def restore(
    checkpoint: object, store: SQLiteMemoryStore, access: AccessContext, authority: dict
) -> dict:
    """Apply the amended visibility and disclosure rules to a disposable claim."""
    if not authorized(authority, access):
        return result("unavailable")
    if (
        not isinstance(checkpoint, dict)
        or set(checkpoint)
        != {
            "schema",
            "checkpoint_id",
            "task_id",
            "scope",
            "producer",
            "generation",
            "supersedes",
            "task_revision",
            "recorded_at",
            "effective_at",
            "expires_at",
            "completed",
            "pending",
            "constraints",
            "evidence_refs",
        }
        or not isinstance(checkpoint.get("checkpoint_id"), str)
        or checkpoint.get("scope") != access.scope
        or checkpoint.get("task_id") != authority["task_id"]
    ):
        return result("unavailable")
    entry = authority["registry"].get(checkpoint.get("checkpoint_id"))
    if (
        entry is None
        or digest(checkpoint) != entry["digest"]
        or entry["revoked"]
        or checkpoint.get("producer") != entry["producer"]
        or type(checkpoint.get("generation")) is not int
        or checkpoint["generation"] != entry["generation"]
        or checkpoint.get("supersedes") != entry["supersedes"]
    ):
        return result("unavailable")
    try:
        registered = utc_timestamp(entry["registered_at"])
        recorded, effective, expires = [
            utc_timestamp(checkpoint[name])
            for name in ("recorded_at", "effective_at", "expires_at")
        ]
    except (KeyError, ValueError, TypeError):
        return result("unavailable")
    if (
        registered > min(authority["as_of"], authority["now"])
        or recorded > registered
        or recorded > authority["as_of"]
        or effective > authority["effective_at"]
        or expires <= recorded
    ):
        return result("unavailable")
    if checkpoint.get("schema") != "checkpoint-eval-v1":
        return result("unavailable")
    refs = checkpoint.get("evidence_refs")
    if not isinstance(refs, list) or not 1 <= len(refs) <= MAX_REFS:
        return result("unavailable")
    identifiers = []
    for ref in refs:
        if not isinstance(ref, dict) or ref.get("scope") != access.scope:
            return result("unavailable")
        identifier = ref.get("evidence_id")
        if not isinstance(identifier, str) or identifier in identifiers:
            return result("unavailable")
        record = store.get_evidence(access, identifier)
        if (
            not visible(record, authority)
            or reference(record) != ref
            or record.status is not EvidenceStatus.RECORDED
            or record.recorded_at > recorded
            or record.observed_at > effective
        ):
            return result("unavailable")
        identifiers.append(identifier)
    if type(checkpoint.get("task_revision")) is not int:
        return result("unavailable")
    if checkpoint["generation"] < authority["active_generation"]:
        return rejection("superseded", access, authority)
    if (
        checkpoint["generation"] != authority["active_generation"]
        or checkpoint["checkpoint_id"] != authority["active_checkpoint"]
    ):
        return result("unavailable")
    if expires <= authority["now"]:
        return rejection("expired", access, authority)
    if checkpoint.get("task_revision") != authority["task_revision"] or set(identifiers) != set(
        authority["head_ids"]
    ):
        return rejection("stale", access, authority)
    canonical = canonical_state(store, access, authority)
    if canonical["status"] != "ready":
        return rejection(canonical["status"], access, authority)
    state = canonical["state"]
    try:
        normalize_state(
            json.dumps(
                {
                    "kind": "task_state",
                    "task_id": checkpoint["task_id"],
                    "task_revision": checkpoint["task_revision"],
                    "completed": checkpoint["completed"],
                    "constraints": checkpoint["constraints"],
                }
            ),
            authority,
        )
    except (ValueError, TypeError):
        return rejection("contradictory", access, authority)
    if any(checkpoint.get(name) != state[name] for name in ("completed", "pending", "constraints")):
        return rejection("contradictory", access, authority)
    return canonical
