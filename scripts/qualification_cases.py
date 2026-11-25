"""Preregistered seal-room histories, independent literal answer sheet and public interface."""

import json
from hashlib import sha256

from checkpoint_recovery_cases import day, digest

# Each row is a different seal-room ledger. Day 2 is visible at interruption on day 4.
# Day 5 supersedes day 2. Multiple day-5 receipts have equal authority.
HISTORIES = (
    ("marl", "checked", ("ready",), True),
    ("tufa", "failed", ("checked",), True),
    ("mica", "ready", ("hold",), True),
    ("flint", "hold", ("failed",), True),
    ("jasper", "ready", ("checked", "hold"), True),
    ("shale", "failed", (), True),
    ("ochre", "hold", (), True),
    ("slate", "checked", ("ready",), False),
    ("agate", "hold", ("checked",), True),
    ("opal", "ready", (), True),
)
# Adjudicated from the history specification above, before retrieval/actor code.
# Witness indices are slots in the official receipt sequence, beginning at day 2.
ANSWERS = (
    ("verify", (1,)),
    ("publish", (1,)),
    ("resolve consent", (1,)),
    ("repair", (1,)),
    ("abstain", (1, 2)),
    ("repair", (0,)),
    ("resolve consent", (0,)),
    ("abstain", ()),
    ("publish", (1,)),
    ("verify", (0,)),
)
STATES = {
    "ready": (["prepare"], [], []),
    "checked": (["prepare", "verify"], [], []),
    "failed": (["prepare"], ["verify"], []),
    "hold": (["prepare", "verify"], [], ["owner signature"]),
}
LEGENDS = (
    ("verify", "repair", "resolve consent", "publish", "abstain"),
    ("publish", "abstain", "verify", "repair", "resolve consent"),
)
RULE = """Resume the interrupted seal-room job. Use the first matching row:
1. Access denied, no official receipt, or disagreement between newest official receipts -> abstain
2. Newest official receipt has a pending signature -> resolve consent
3. Newest official receipt records a failed verification -> repair
4. Verification is unfinished -> verify
5. Verification is finished -> publish
Use observation date to find the newest receipt. Ignore journal notes.
Translate your action using this key and output only its letter."""


def opaque(value: str) -> str:
    """Namespace all public identities independently of outcomes."""
    return sha256(("seal-room-nov25-v1/" + value).encode()).hexdigest()[:20]


def fixtures() -> tuple[list, dict]:
    """Construct dated source records and a separate parent-only key."""
    cases, labels = [], {}
    for (name, initial, updates, allowed), (action, witnesses) in zip(
        HISTORIES, ANSWERS, strict=True
    ):
        key = opaque(name)
        scope, executor = "room-" + key, "inspector-" + key
        goal = "release seal-room batch " + key
        task = dict(
            task_id=key,
            goal=goal,
            scope=scope,
            executor=executor,
            principal="reader-" + key,
            allowed=allowed,
            as_of=day(6),
            effective_at=day(6),
            now=day(6),
        )
        records = []
        specs = [(initial, 2, 3, scope, executor)]
        specs.extend((state, 5, 5, scope, executor) for state in updates)
        specs.extend(
            [
                ("ready", 6, 6, scope, "journal-" + key),
                ("hold", 6, 6, "external-" + key, executor),
                ("failed", 5, 8, scope, executor),
                ("checked", 8, 5, scope, executor),
            ]
        )
        for slot, (state, observed, recorded, source_scope, producer) in enumerate(specs):
            completed, failures, constraints = STATES[state]
            payload = dict(
                kind="restart_state",
                completed=completed,
                failed_attempts=failures,
                constraints=constraints,
                goal=goal,
            )
            if producer != executor:
                payload = dict(kind="note", text="Tray count recorded.")
            text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            records.append(
                dict(
                    id=opaque(f"{name}/{slot}"),
                    source_actor=producer,
                    producer=producer,
                    scope=source_scope,
                    source_locator=f"sealroom://{key}/{slot}",
                    observed_at=day(observed),
                    recorded_at=day(recorded),
                    text=text,
                    digest="sha256:" + sha256(text.encode()).hexdigest(),
                )
            )
        cases.append(
            dict(id=key, request=task, records=records, expires_at=day(9), foreign_checkpoint=False)
        )
        labels[key] = dict(action=action, required=[records[i]["id"] for i in witnesses])
    return cases, labels


def render(packet: dict, legend: tuple) -> str:
    """Render only the public evidence packet and assigned response legend."""
    mapping = " | ".join(f"{c} = {a}" for c, a in zip("ABCDE", legend, strict=True))
    body = json.dumps(packet, sort_keys=True, separators=(",", ":"))
    return (
        "<|im_start|>system\n"
        + RULE
        + "\n"
        + mapping
        + "<|im_end|>\n<|im_start|>user\n"
        + body
        + "<|im_end|>\n<|im_start|>assistant\n"
    )


if __name__ == "__main__":
    print(*(digest(x) for x in fixtures()), sep="\n")
