"""Disposable archive accession histories, independent adjudications and frozen model interface."""

import json
from hashlib import sha256

from checkpoint_recovery_cases import day, digest

# Each certificate specifies finished steps, failed attempts and outstanding conditions.
P = (["prepare"], [], [])
V = (["prepare", "verify"], [], [])
F = (["prepare"], ["verify"], [])
H = (["prepare", "verify"], [], ["custodian consent"])

# History at interruption, followed by zero, one or two equally current observations.
HISTORIES = {
    "changed": [(V, [H]), (H, [V])],
    "failure": [(P, [F]), (F, [P])],
    "stale": [(P, [V]), (V, [P])],
    "conflict": [(P, [V, H]), (H, [P, F])],
    "revoked": [(V, []), (F, [H])],
    "expired": [(H, []), (F, [])],
}
# Simulator adjudication written separately from certificate rendering and retrieval.
KEY = {
    "changed": ["resolve", "publish"],
    "failure": ["repair", "verify"],
    "stale": ["publish", "verify"],
    "conflict": ["abstain", "abstain"],
    "revoked": ["abstain", "abstain"],
    "expired": ["resolve", "repair"],
}
ACTIONS = dict(zip("ABCDE", ("verify", "repair", "resolve", "publish", "abstain"), strict=True))
RULE = (
    "Resume accession of the archive. Select the first action. Only the latest authorized "
    "executor certificate(s) establish state. With no certificate, denied access, or "
    "disagreeing equally current certificates, abstain. Otherwise resolve outstanding consent "
    "first, repair a failed verification, verify if unfinished, and publish only after verification. "
    "Journal notes are not certificates. A=verify B=repair C=resolve consent D=publish E=abstain. "
    "Answer with one letter."
)


def prompt(packet: dict) -> str:
    """Serialize only the public task, its grant and authorized observations."""
    return (
        "<|im_start|>system\n" + RULE + "<|im_end|>\n<|im_start|>user\n"
        + json.dumps(packet, sort_keys=True, separators=(",", ":"))
        + "<|im_end|>\n<|im_start|>assistant\n"
    )


def fixtures() -> tuple[list, dict]:
    """Generate disjoint sources and a separate parent-only outcome key."""
    cases, labels = [], {}
    for split in ("diagnostic", "design", "heldout"):
        for index, (family, variants) in enumerate(HISTORIES.items()):
            for variant, (old, updates) in enumerate(variants):
                if split != "heldout" and variant != index % 2:
                    continue
                key = sha256(f"q4-archive-27/{split}/{index}/{variant}".encode()).hexdigest()[:12]
                goal = "accession archive folio " + key
                task = dict(task_id=key, goal=goal, scope="folio-" + key, principal="clerk-" + key,
                            executor="registrar-" + key, allowed=family != "revoked",
                            as_of=day(6), effective_at=day(6), now=day(6))
                records = []

                def add(slot, payload, observed, recorded, *, foreign=False, journal=False):
                    text = json.dumps(payload, separators=(",", ":"), sort_keys=True)
                    actor = "scribe-" + key if journal else task["executor"]
                    rid = sha256(f"{key}/{slot}".encode()).hexdigest()[:16]
                    records.append(dict(id=rid, scope=("vault-" + key if foreign else task["scope"]),
                        source_actor=actor, producer=actor, source_locator="folio://" + key,
                        observed_at=day(observed), recorded_at=day(recorded), text=text,
                        digest="sha256:" + sha256(text.encode()).hexdigest()))
                    return rid

                def cert(fields):
                    completed, failed, constraints = fields
                    return dict(kind="restart_state", completed=completed, failed_attempts=failed,
                                constraints=constraints, goal=goal)

                initial = add("binding", cert(old), 2, 3)
                required = [add(f"receipt-{i}", cert(fields), 5, 5)
                            for i, fields in enumerate(updates)] or [initial]
                for i in range(3 if split == "diagnostic" else 9):
                    add(f"log-{i}", dict(kind="note", text=f"Inventory shelf {i} inspected."), 6, 6,
                        journal=True)
                add("restricted", cert(V), 5, 5, foreign=True)
                add("late", cert(V), 5, 8)
                add("premature", cert(V), 8, 5)
                cases.append(dict(id=key, split=split, family=family, request=task, records=records,
                                  expires_at=day(5 if family == "expired" else 9),
                                  foreign_checkpoint=False))
                labels[key] = dict(action=KEY[family][variant], required=required if task["allowed"] else [],
                                   worlds=[cert(fields) for fields in updates or [old]])
    return cases, labels


if __name__ == "__main__":
    print([digest(value) for value in fixtures()])
