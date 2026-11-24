"""Proposed #124 contract in disposable evaluation only. Not a product API or persistence layer."""

import json
from pathlib import Path

from aams.contracts import EvidenceStatus, utc_timestamp
from checkpoint_recovery_cases import digest

MAX_BYTES = 8192
MAX_REFS = 8


def result(status, state=None, citations=None):
    return {"status": status, "state": state, "citations": citations or []}


def authorized(authority, access):
    return (
        authority["allowed"]
        and access.scope == authority["scope"]
        and access.principal in authority["readers"]
    )


def reference(record):
    return {
        "evidence_id": record.evidence_id,
        "scope": record.scope,
        "digest": record.digest,
        "source_actor": record.source_actor,
        "source_locator": record.source_locator,
        "producer": record.producer,
        "observed_at": record.observed_at,
        "recorded_at": record.recorded_at,
    }


def visible(record, authority):
    return (
        record is not None
        and record.recorded_at <= authority["as_of"]
        and record.observed_at <= authority["effective_at"]
    )


def normalize_state(payload, authority):
    state = json.loads(payload)
    if (
        not isinstance(state, dict)
        or set(state) != {"kind", "task_id", "task_revision", "completed", "constraints"}
        or state["kind"] != "task_state"
        or state["task_id"] != authority["task_id"]
        or type(state["task_revision"]) is not int
        or state["task_revision"] != authority["task_revision"]
        or not isinstance(state["completed"], list)
        or any(not isinstance(s, str) for s in state["completed"])
        or len(set(state["completed"])) != len(state["completed"])
        or not set(state["completed"]) <= set(authority["steps"])
        or not isinstance(state["constraints"], dict)
        or set(state["constraints"]) != set(authority["constraint_keys"])
        or any(type(v) is not bool for v in state["constraints"].values())
    ):
        raise ValueError("Invalid canonical task-state certificate")
    return {
        "completed": [s for s in authority["steps"] if s in state["completed"]],
        "pending": [s for s in authority["steps"] if s not in state["completed"]],
        "constraints": state["constraints"],
    }


def canonical_state(store, access, authority, available_ids=None):
    if not authorized(authority, access):
        return result("unavailable")
    heads = authority["head_ids"]
    if not heads or len(heads) > MAX_REFS:
        return result("unavailable")
    if available_ids is not None and not set(heads) <= set(available_ids):
        return result("insufficient")
    states, citations = [], []
    for identifier in heads:
        record = store.get_evidence(access, identifier)
        if (
            not visible(record, authority)
            or record.status is not EvidenceStatus.RECORDED
            or record.source_actor != authority["executor"]
            or record.producer != authority["executor"]
            or record.source_locator != authority["source_locator"]
        ):
            return result("unavailable")
        try:
            states.append(normalize_state(record.payload, authority))
        except (ValueError, TypeError, UnicodeDecodeError):
            return result("contradictory")
        citations.append(reference(record))
    if len({digest(s) for s in states}) != 1:
        return result("contradictory")
    return result("ready", states[0], citations)


def restore_path(path: Path, store, access, authority):
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


def restore(checkpoint, store, access, authority):
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
    if checkpoint["generation"] < authority["active_generation"]:
        return result("superseded")
    if (
        checkpoint["generation"] != authority["active_generation"]
        or checkpoint["checkpoint_id"] != authority["active_checkpoint"]
    ):
        return result("unavailable")
    try:
        recorded, effective, expires = [
            utc_timestamp(checkpoint[name])
            for name in ("recorded_at", "effective_at", "expires_at")
        ]
    except (KeyError, ValueError, TypeError):
        return result("unavailable")
    if (
        recorded > authority["as_of"]
        or effective > authority["effective_at"]
        or expires <= recorded
    ):
        return result("unavailable")
    if expires <= authority["now"]:
        return result("expired")
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
    if checkpoint.get("task_revision") != authority["task_revision"] or set(identifiers) != set(
        authority["head_ids"]
    ):
        return result("stale")
    canonical = canonical_state(store, access, authority)
    if canonical["status"] != "ready":
        return canonical
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
        return result("contradictory")
    if any(checkpoint.get(name) != state[name] for name in ("completed", "pending", "constraints")):
        return result("contradictory")
    return canonical


def decide(reconstructed, authority):
    if reconstructed["status"] != "ready":
        return "abstain"
    state = reconstructed["state"]
    blocked = sorted(name for name, value in state["constraints"].items() if value)
    if blocked:
        return "resolve:" + blocked[0]
    for step in authority["steps"]:
        if step not in state["completed"]:
            return "do:" + step
    return "finish"
