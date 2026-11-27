"""Paired measured transfer of an approved lesson in a disposable AAMS ledger."""

import json
import tempfile
from collections import Counter
from hashlib import sha256
from pathlib import Path

from aams.learning import CandidateState, LearningCandidate, OutcomeFeedback
from aams.storage import AccessContext, SQLiteMemoryStore
from cognitive_task_cases import digest
from evaluate_cognitive_tasks import database_digest
from evaluate_learning import TIME, review, seed
from lesson_transfer_cases import FIELDS, LESSON, SOURCES, held_out
from lesson_transfer_policy import choose

PINS = (
    "9de15b215b50516b706df93648392a0bf8efc7ee3d2ee8caa4593f892322f75f",
    "f6692665f63403a6976e4ab40da300f746f677e8ba14602e2850efd0dc4c554e",
    "e477a0f87968ac7f159e52f8814e57e4e3bb200cb199898ed8c20286b2e0b5d7",
    "e10dd3b9af07238eebdc394c00a1d39061959fdeeefb5b7ba1e4a6750598c30b",
)
POLICY_PIN = "9d5a9b817a13467c5b7b8763eb909987113c57b73bed21bbdacd1dc18bf9b4da"
BUDGET = dict(recommendations=2, bytes=4096)
RATES = {"direct": 4, "paced": 1}
SCOPE = "lesson-transfer-offline"
LESSON_ID = "reviewed-queue-pacing"


def simulate(config, action):
    """Count physical drops and elapsed ticks independently of the memory policy."""
    remaining, queued = config["items"], config["occupied"]
    ticks = []
    while remaining or queued:
        offered = min(RATES[action], remaining)
        accepted = min(offered, config["capacity"] - queued)
        remaining -= offered
        queued += accepted
        drained = min(queued, config["drain"])
        queued -= drained
        ticks.append(dict(offered=offered, accepted=accepted, drained=drained, queued=queued))

    dropped = sum(row["offered"] - row["accepted"] for row in ticks)
    return dict(
        dropped=dropped,
        elapsed=len(ticks),
        deadline_met=len(ticks) <= config["deadline"],
        ticks=ticks,
    )


def winners(outcomes):
    successful = {
        arm: item["elapsed"]
        for arm, item in outcomes.items()
        if item["dropped"] == 0 and item["deadline_met"]
    }
    fastest = min(successful.values(), default=None)
    return sorted(arm for arm, elapsed in successful.items() if elapsed == fastest)


def encoded(packet):
    return json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()


def build_memory(path):
    store = SQLiteMemoryStore(path)
    author = AccessContext("lesson-author", SCOPE, True)
    reviewer = AccessContext("fixture-reviewer", SCOPE, True, True)
    reader = AccessContext("offline-agent", SCOPE)
    foreign = AccessContext("offline-agent", "another-scope")
    evidence = []
    source_ids = tuple(key for key, _, _ in SOURCES)
    for key, family, values in SOURCES:
        config = dict(zip(FIELDS, values, strict=True))
        attempts = {arm: simulate(config, arm) for arm in RATES}
        text = encoded(dict(workload=family, configuration=config, attempts=attempts)).decode()
        evidence.append((key, SCOPE, key + "-meter", key + "-cell", "fixture:" + key, text))
    seed(store, {"evidence": evidence})
    candidate = LearningCandidate(
        LESSON_ID,
        SCOPE,
        author.principal,
        encoded(LESSON).decode(),
        TIME,
        source_ids,
    )
    store.create_candidate(author, "write-lesson", candidate)
    if not review(store, candidate, reviewer):
        raise ValueError("Source-backed lesson was not approved by the fixture review")

    for key in source_ids:
        meter = AccessContext(key + "-meter", SCOPE, True)
        packet = json.loads(store.get_evidence(reader, key).payload)
        measurements = packet["attempts"]["direct"]["ticks"]
        for version, window in enumerate((measurements[:1], measurements)):
            retained = sum(tick["accepted"] for tick in window) / sum(
                tick["offered"] for tick in window
            )
            feedback = OutcomeFeedback(
                "direct-" + key,
                SCOPE,
                LESSON_ID,
                meter.principal,
                "Fraction of offered items retained in the observed window",
                1,
                retained,
                TIME,
                (key,),
            )
            store.append_outcome(meter, f"{key}-meter-revision-{version + 1}", version, feedback)

    store = SQLiteMemoryStore(path)
    store.verify_integrity()
    record = store.get_candidate(reader, LESSON_ID)
    validation = store.validate_candidate(reader, LESSON_ID)
    if (
        record.state is not CandidateState.APPROVED
        or record.proposal.support_ids != source_ids
        or validation.independent_support != source_ids
        or [decision.version for decision in record.history] != [1, 2]
        or any(decision.request.actor != reviewer.principal for decision in record.history)
        or store.get_candidate(foreign, LESSON_ID) is not None
        or store.get_belief(reader, LESSON_ID) is not None
    ):
        raise ValueError("Review, lineage or authority invariant failed")

    raw_rows, exact, revisions = [], [], {}
    for key in source_ids:
        source = store.get_evidence(reader, key)
        if source is None or store.get_evidence(foreign, key) is not None:
            raise ValueError("Source scope invariant failed")
        episode_id = "direct-" + key
        history = store.outcome_history(reader, episode_id)
        if (
            [row.version for row in history] != [1, 2]
            or any(row.feedback.evidence_ids != (key,) for row in history)
            or store.outcome_history(foreign, episode_id)
        ):
            raise ValueError("Outcome revision invariant failed")
        observation = json.loads(source.payload)
        measured = observation["attempts"]["direct"]
        final_retention = 1 - measured["dropped"] / observation["configuration"]["items"]
        if abs(history[-1].feedback.measured - final_retention) > 1e-12:
            raise ValueError("Final revision differs from the source reading")
        revisions[key] = [
            dict(
                version=row.version,
                predicted=row.feedback.predicted,
                measured=row.feedback.measured,
                producer=row.feedback.producer,
                sources=row.feedback.evidence_ids,
            )
            for row in history
        ]
        best = winners(observation["attempts"])
        if len(best) != 1:
            raise ValueError("Source offers no unique measured recommendation")
        raw_rows.append(dict(id=key, digest=source.digest, observation=observation))
        exact.append(
            dict(
                action=best[0],
                sources=[key],
                conditions=[
                    [field, "eq", value]
                    for field, value in sorted(observation["configuration"].items())
                ],
            )
        )

    audit = dict(
        id=LESSON_ID,
        state=record.state.value,
        sources=source_ids,
        history=[
            dict(version=d.version, reviewer=d.request.actor, state=d.request.to_state.value)
            for d in record.history
        ],
    )
    memory = {
        "A": dict(recommendations=exact, observed=raw_rows),
        "B": dict(
            recommendations=[{**json.loads(record.proposal.claim), "sources": source_ids}],
            review=audit,
        ),
    }
    for packet in memory.values():
        if (
            len(packet["recommendations"]) > BUDGET["recommendations"]
            or len(encoded(packet)) > BUDGET["bytes"]
        ):
            raise ValueError("Memory budget exceeded")
    return memory, revisions


def replay(path):
    cases, keys = held_out()
    if tuple(map(digest, (cases, keys, LESSON, SOURCES))) != PINS:
        raise ValueError("Frozen data drift")
    if (
        sha256(Path(__file__).with_name("lesson_transfer_policy.py").read_bytes()).hexdigest()
        != POLICY_PIN
    ):
        raise ValueError("Frozen actor drift")
    memory, revisions = build_memory(path)
    before = database_digest(path)
    decisions = [
        {arm: choose(case["task"], packet) for arm, packet in memory.items()} for case in cases
    ]

    results = []
    for case, pair in zip(cases, decisions, strict=True):
        outcomes = {arm: simulate(case["task"]["configuration"], arm) for arm in RATES}
        best = winners(outcomes)
        if best != [keys[case["id"]]]:
            raise ValueError(f"Frozen key disagrees with measured outcomes: {case['id']}")
        scores = {}
        for arm, decision in pair.items():
            measured = outcomes[decision["action"]]
            correct = decision["action"] in best
            scores[arm] = dict(
                correct=correct,
                loss=measured["dropped"] > 0,
                deadline_missed=not measured["deadline_met"],
                slower=not correct and measured["dropped"] == 0 and measured["deadline_met"],
            )
        a, b = (scores[arm]["correct"] for arm in "AB")
        transition = (
            ("prevented" if b else "introduced")
            if a != b
            else ("unchanged_correct" if a else "unchanged_wrong")
        )
        results.append(
            dict(
                **case,
                best=best,
                measured=outcomes,
                decisions=pair,
                scores=scores,
                transition=transition,
            )
        )
    if before != database_digest(path):
        raise ValueError("Decision replay changed the ledger")
    return dict(
        pins=PINS,
        policy=POLICY_PIN,
        budget=BUDGET,
        memory_bytes={arm: len(encoded(packet)) for arm, packet in memory.items()},
        memory=memory,
        outcome_revisions=revisions,
        rows=results,
        transitions=Counter(row["transition"] for row in results),
        unchanged_actions=sum(
            r["decisions"]["A"]["action"] == r["decisions"]["B"]["action"] for r in results
        ),
        arms={
            arm: {
                metric: sum(r["scores"][arm][metric] for r in results)
                for metric in ("correct", "loss", "deadline_missed", "slower")
            }
            for arm in "AB"
        },
    )


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="aams-lesson-transfer-") as tmp:
        print(encoded(replay(Path(tmp) / "memory.db")).decode())
