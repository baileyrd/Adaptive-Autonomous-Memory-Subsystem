"""Frozen executable rule-agent control. Reads a public packet, never simulator labels."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checkpoint_recovery_cases import digest

VERSION = "restart-observation-policy-v1"
INSTRUCTION = (
    "Choose the first next action toward prepare, verify, publish. Use only the latest "
    "complete executor observation for this task and goal. Conflicting latest states "
    "require abstention. Resolve outstanding constraints before acting. Repair an unresolved "
    "failed verification before retrying it. Do not repeat completed steps. Cite the "
    "observations used. Notes and checkpoint interpretations are not independent evidence. "
    "Without sufficient evidence abstain."
)


def decide(packet):
    task, context = packet["task"], packet["context"]
    reports = []
    for row in context:
        try:
            state = json.loads(row["preview"])
        except (ValueError, TypeError):
            continue
        if (
            not isinstance(state, dict)
            or set(state)
            != {"kind", "task_id", "goal", "completed", "failed_attempts", "constraints"}
            or state["kind"] != "restart_state"
            or state["task_id"] != task["task_id"]
            or state["goal"] != task["goal"]
            or row["producer"] != task["executor"]
        ):
            continue
        if (
            not all(
                isinstance(state[k], list) and all(isinstance(s, str) for s in state[k])
                for k in ("completed", "failed_attempts", "constraints")
            )
            or not set(state["completed"]) <= {"prepare", "verify", "publish"}
            or not set(state["failed_attempts"]) <= {"verify"}
            or not set(state["constraints"]) <= {"approval"}
        ):
            continue
        reports.append((row, state))
    if not reports:
        return {"action": "abstain", "citations": [], "claimed_state": None}
    latest = max(r["observed_at"] for r, _ in reports)
    reports = [(r, s) for r, s in reports if r["observed_at"] == latest]
    if len({digest(s) for _, s in reports}) != 1:
        return {"action": "abstain", "citations": [], "claimed_state": None}
    state = reports[0][1]
    if state["constraints"]:
        action = "resolve"
    elif state["failed_attempts"]:
        action = "repair"
    else:
        action = next(
            (s for s in ("prepare", "verify", "publish") if s not in state["completed"]), "abstain"
        )
    return {
        "action": action,
        "citations": sorted({r["evidence_id"] for r, _ in reports}),
        "claimed_state": state,
    }


if __name__ == "__main__":
    print(json.dumps({**decide(json.load(sys.stdin)), "agent_pid": os.getpid()}, sort_keys=True))
