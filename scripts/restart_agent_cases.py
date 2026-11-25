"""Source-disjoint #124 inputs and separate simulator keys; no labels in actor packets."""

from copy import deepcopy
from hashlib import sha256

from checkpoint_recovery_cases import day, digest

FAMILIES = (
    "partial",
    "prior_failure",
    "constraint",
    "superseded",
    "delayed",
    "expired",
    "unauthorized",
    "cross_scope",
)


def cases():
    inputs = []
    for split in ("calibration", "design", "heldout"):
        families = FAMILIES[:2] if split == "calibration" else FAMILIES
        for family in families:
            for variant in (0, 1):
                key = sha256(f"agent124:20261125:{split}:{family}:{variant}".encode()).hexdigest()[
                    :20
                ]
                pair = sha256(f"agent124:20261125:{split}:{family}".encode()).hexdigest()[:20]
                goal = "release the collection " + key
                task = {
                    "task_id": key,
                    "goal": goal,
                    "scope": "restart-" + key,
                    "principal": "reader-" + key,
                    "allowed": family != "unauthorized",
                    "as_of": day(6),
                    "effective_at": day(6),
                    "now": day(6),
                    "executor": "executor-" + key,
                }
                state = {
                    "kind": "restart_state",
                    "task_id": key,
                    "goal": goal,
                    "completed": ["prepare"],
                    "failed_attempts": [],
                    "constraints": [],
                }
                if family in ("partial", "expired", "unauthorized", "cross_scope", "delayed"):
                    state["completed"] += ["verify"] if variant else []
                elif family == "prior_failure":
                    state["failed_attempts"] = ["verify"] if variant == 0 else []
                else:
                    state["completed"].append("verify")
                    state["constraints"] = ["approval"] if variant == 0 else []
                records = []

                def add(suffix, payload, observed, recorded, scope=None, executor=None):
                    text = __import__("json").dumps(payload, sort_keys=True, separators=(",", ":"))
                    records.append(
                        {
                            "id": key + "-" + suffix,
                            "scope": scope or task["scope"],
                            "source_actor": executor or task["executor"],
                            "producer": executor or task["executor"],
                            "source_locator": "restart124://" + key,
                            "observed_at": day(observed),
                            "recorded_at": day(recorded),
                            "text": text,
                            "digest": "sha256:" + sha256(text.encode()).hexdigest(),
                        }
                    )

                old = deepcopy(state)
                if family == "superseded":
                    old["constraints"] = [] if state["constraints"] else ["approval"]
                if family == "delayed":
                    old["completed"] = ["prepare"]
                add("initial", old, 1, 1)
                add(
                    "current",
                    state,
                    3 if family != "delayed" else 5,
                    4 if family != "delayed" else 5,
                )
                # Recent journal chatter is eligible but cannot attest progress.
                for index in range(9):
                    add(
                        f"note{index}",
                        {
                            "kind": "note",
                            "task_id": key,
                            "text": "Discuss the collection release; this is not completion evidence.",
                        },
                        5,
                        5,
                        executor="journal-" + key,
                    )
                decoy = {**state, "completed": ["prepare", "verify"], "constraints": []}
                add("foreign", decoy, 5, 5, "private-" + key)
                add("future-recorded", decoy, 3, 9)
                add("future-effective", decoy, 9, 5)
                inputs.append(
                    {
                        "id": key,
                        "split": split,
                        "family": family,
                        "pair": pair,
                        "request": task,
                        "records": records,
                        "expires_at": day(5 if family == "expired" else 8),
                        "foreign_checkpoint": family == "cross_scope",
                    }
                )
    return inputs


def simulator_labels(inputs):
    """Parent-only oracle; never called by preparation, retrieval or actor processes."""
    import json

    # Authored action keys, independent of the actor's parsing or decision function.
    keys = {
        "partial": ("verify", "publish"),
        "prior_failure": ("repair", "verify"),
        "constraint": ("resolve", "publish"),
        "superseded": ("resolve", "publish"),
        "delayed": ("verify", "publish"),
        "expired": ("verify", "publish"),
        "unauthorized": ("abstain", "abstain"),
        "cross_scope": ("verify", "publish"),
    }
    labels = {}
    for index, e in enumerate(inputs):
        world = json.loads(next(r["text"] for r in e["records"] if r["id"] == e["id"] + "-current"))
        expected = keys[e["family"]][index % 2]
        labels[e["id"]] = {
            "action": expected,
            "world": world,
            "required": [] if not e["request"]["allowed"] else [e["id"] + "-current"],
        }
    return labels


def verify_separation(batch):
    seen = set()
    for split in ("calibration", "design", "heldout"):
        identities = {
            v
            for e in batch
            if e["split"] == split
            for r in e["records"]
            for v in (r["id"], r["scope"], r["source_actor"], r["source_locator"])
        }
        if seen & identities:
            raise ValueError("Source overlap")
        seen |= identities
    return digest(batch)
