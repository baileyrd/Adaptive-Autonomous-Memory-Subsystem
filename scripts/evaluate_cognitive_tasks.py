"""Bounded offline #117 decision replay. No model, network, product writes or activation.

Each arm ingests an identical synthetic source history in a preparer process, then a fresh
worker reopens its own database and makes decisions. Gold environment states reach scoring
only; the fixed agent receives only the common request and bounded retrieved citations.
"""

import argparse
import json
import os
import platform
import random
import resource
import sqlite3
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from math import ceil
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cognitive_task_agent import INSTRUCTION, POLICY_VERSION, decide  # noqa: E402
from cognitive_task_cases import RECIPE, cases, digest, oracle, world_state  # noqa: E402
from evaluate_semantic import timestamp  # noqa: E402

from aams.ranking import bm25_scores, tokens  # noqa: E402
from aams.recall import CognitiveMemory, CognitiveNeed  # noqa: E402
from aams.storage import AccessContext, SQLiteMemoryStore  # noqa: E402

ARMS = ("no_memory", "raw_search", "structured")
REGISTRATION = Path(__file__).with_name("cognitive_task_preregistration.json")


def verify_registration(recipe_path):
    registration = json.loads(REGISTRATION.read_text())
    directory = Path(__file__).parent
    for name, expected in registration["source_sha256"].items():
        if sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Preregistered source checksum mismatch")
    if sha256(recipe_path.read_bytes()).hexdigest() != registration["recipe_sha256"]:
        raise ValueError("Preregistered recipe checksum mismatch")
    recipe = json.loads(recipe_path.read_text())
    if digest(cases(recipe)) != registration["cases_sha256"]:
        raise ValueError("Preregistered case checksum mismatch")
    return recipe, registration


def database_digest(path):
    with sqlite3.connect(path) as db:
        return sha256("\n".join(db.iterdump()).encode()).hexdigest()


def prepare(path, episodes):
    store = SQLiteMemoryStore(path)
    # Supply observed and ingestion times independently (including delayed reports).
    from aams.contracts import (
        BeliefProposal,
        EpistemicState,
        Evidence,
        EvidenceStatus,
        MemoryFormation,
        MemoryKind,
    )

    for episode in episodes:
        parents = {}
        for row in episode["observations"]:
            payload = row["text"].encode()
            record = Evidence(
                row["id"],
                row["scope"],
                "source-" + row["source"],
                "simulator:" + row["source"],
                "collector",
                timestamp(row["observed"]),
                timestamp(row["recorded"]),
                EvidenceStatus.RECORDED,
                payload,
                "sha256:" + sha256(payload).hexdigest(),
            )
            formation = MemoryFormation(
                "f-" + row["id"],
                row["scope"],
                MemoryKind.EXPERIENCE,
                (row["id"],),
                "collector",
                timestamp(row["recorded"]),
                EpistemicState.OBSERVED,
            )
            store.ingest(
                AccessContext("collector", row["scope"], True), row["id"], formation, (record,)
            )
            if row["scope"] != episode["tasks"][0]["scope"] or row["source"] not in (
                "initial",
                "change",
                "late",
                "attempt-outcome",
                "conflict",
                "prior-training",
            ):
                continue
            fact = json.loads(row["text"])
            key = fact["check"]
            previous = parents.get(key)

            class SimulatedClock(datetime):
                @classmethod
                def now(cls, tz=None):
                    return datetime.fromisoformat(timestamp(row["recorded"])).astimezone(tz or UTC)

            # Fixture-only clock isolated to the preparer. Replay itself never writes.
            with patch("aams.storage.datetime", SimulatedClock):
                revised = store.revise(
                    AccessContext("collector", row["scope"], True),
                    episode["id"] + "-" + key,
                    previous.revision_id if previous else None,
                    BeliefProposal(
                        row["text"],
                        EpistemicState.CONTESTED
                        if row["source"] == "conflict"
                        else EpistemicState.INFERRED,
                        "Simulator host revision from a report; not an agent promotion.",
                        timestamp(row["observed"]),
                        support_ids=(row["id"],),
                        refute_ids=previous.proposal.support_ids
                        if previous and row["source"] == "conflict"
                        else (),
                    ),
                )
            parents[key] = revised
    store.verify_integrity()


def context_for(memory, task, arm, recipe):
    if arm == "no_memory":
        return []
    access = AccessContext("pilot", task["scope"])
    need = CognitiveNeed(
        task["topic"],
        max_items=recipe["max_citations"],
        max_bytes=recipe["context_bytes"],
        recorded_as_of=timestamp(task["as_of"]),
        effective_at=timestamp(task["day"]),
    )
    if arm == "structured":
        packet = memory.recall(access, need)
        rows = [citation for item in packet["items"] for citation in item["citations"]]
    elif arm == "raw_search":
        # Share canonical access/time visibility, not AAMS's ranker/formation interpretation.
        visible = {}
        for _, records in memory.store.scan_recall(
            access, recorded_as_of=need.recorded_as_of, effective_at=need.effective_at, kinds=()
        ):
            for record in records.values():
                citation = memory._citation(need, record, "source")
                if citation is not None:
                    visible[record.evidence_id] = (record, citation)
        entries = sorted(visible.values(), key=lambda pair: pair[0].evidence_id)
        scores = bm25_scores(
            frozenset(tokens(need.query)),
            [Counter(tokens(record.payload.decode())) for record, _ in entries],
        )
        ranked = sorted(
            zip(scores, entries, strict=True), key=lambda row: (-row[0], row[1][0].evidence_id)
        )
        rows = [entry[1] for score, entry in ranked if score > 0]
    else:
        raise ValueError("Unknown arm")
    # Exactly the same citation and serialized-byte ceilings for every agent context.
    bounded, identifiers = [], set()
    for row in rows:
        if row["evidence_id"] in identifiers:
            continue
        candidate = [*bounded, row]
        if len(candidate) > recipe["max_citations"]:
            break
        if len(json.dumps(candidate, sort_keys=True).encode()) > recipe["context_bytes"]:
            break
        bounded = candidate
        identifiers.add(row["evidence_id"])
    return bounded


def validate_context(store, task, context):
    """A bad citation invalidates a run; never silently filter safety failures from scores."""
    access = AccessContext("pilot", task["scope"])
    for row in context:
        record = store.get_evidence(access, row["evidence_id"])
        if (
            record is None
            or record.digest != row["digest"]
            or record.observed_at > timestamp(task["day"])
            or record.recorded_at > timestamp(task["as_of"])
            or row["preview"] != record.payload[:512].decode("utf-8", errors="replace")
            or row["source_actor"] != record.source_actor
            or row["source_locator"] != record.source_locator
            or row["producer"] != record.producer
            or row["status"] != record.status.value
            or row["observed_at"] != record.observed_at
            or row["recorded_at"] != record.recorded_at
        ):
            raise ValueError("Invalid scope/time/provenance citation")


def score(episode, task, request, context, decision):
    expected = oracle(episode, task)
    if decision["action"] not in ("proceed", "stop", "abstain"):
        raise ValueError("Invalid decision action")
    ids = {row["evidence_id"] for row in context}
    cited = decision["citations"]
    if len(cited) != len(set(cited)) or not set(cited) <= ids:
        raise ValueError("Agent cited unavailable evidence")
    used = [row for row in context if row["evidence_id"] in cited]
    grounded_action = decide(request, used)["action"]
    abstained = decision["action"] == "abstain"
    return {
        "task_id": task["id"],
        "episode_id": episode["id"],
        "family": episode["family"],
        "split": episode["split"],
        "historical": task["day"] < task["as_of"],
        "retrospective_state_correct": decision["observed_checks"]
        == {
            check: "clear" if value else "blocked"
            for check, value in world_state(episode, task).items()
        },
        "expected": expected,
        "decision": decision,
        "success": decision["action"] == expected,
        "abstained": abstained,
        "unsupported_assertion": not abstained and grounded_action != decision["action"],
        "wrong_nonabstaining": not abstained and decision["action"] != expected,
        "unsafe_proceed": decision["action"] == "proceed" and expected == "stop",
        "context_sensitive": decision["action"] != decide(request, [])["action"],
        "citations": len(cited),
        "valid_citations": len(cited),
        "conflict_case": episode["family"] == "conflicting_sources",
        "conflict_handled": decision["conflict_detected"] and abstained,
        "repeat_case": episode["family"] == "recurring_failure" and task["day"] == 5,
        "repeat_error": episode["family"] == "recurring_failure"
        and task["day"] == 5
        and decision["action"] == "proceed",
        "context_sha256": digest(context),
        "context_bytes": len(json.dumps(context, sort_keys=True).encode()),
    }


def summarize(rows):
    def rate(field, subset=rows):
        return sum(row[field] for row in subset) / len(subset) if subset else None

    cited = sum(row["citations"] for row in rows)
    historical = [row for row in rows if row["historical"]]
    conflict = [row for row in rows if row["conflict_case"]]
    repeated = [row for row in rows if row["repeat_case"]]
    return {
        "tasks": len(rows),
        "families": len({r["family"] for r in rows}),
        "success_rate": rate("success"),
        "historical_success_rate": rate("success", historical),
        "retrospective_state_accuracy": rate("retrospective_state_correct", historical),
        "abstention_rate": rate("abstained"),
        "unsupported_assertions": sum(r["unsupported_assertion"] for r in rows),
        "wrong_nonabstaining_rate": rate("wrong_nonabstaining"),
        "unsafe_proceed_count": sum(row["unsafe_proceed"] for row in rows),
        "citation_precision": sum(r["valid_citations"] for r in rows) / cited if cited else None,
        "context_sensitive_rate": rate("context_sensitive"),
        "conflict_handling_rate": rate("conflict_handled", conflict),
        "known_failure_repeat_rate": rate("repeat_error", repeated),
    }


def interval(before, after, samples, seed_value):
    """Paired bootstrap over whole scenario families, not tasks/repeated timings."""
    if [row["task_id"] for row in before] != [row["task_id"] for row in after]:
        raise ValueError("Unmatched tasks")
    if any(
        a["family"] != b["family"] or a["split"] != b["split"]
        for a, b in zip(before, after, strict=True)
    ):
        raise ValueError("Unmatched task grouping")
    groups = sorted({row["family"] for row in before})
    deltas = {
        group: [
            int(b["success"]) - int(a["success"])
            for a, b in zip(before, after, strict=True)
            if a["family"] == group
        ]
        for group in groups
    }
    rng = random.Random(seed_value)
    boots = sorted(
        statistics.mean(
            value for group in rng.choices(groups, k=len(groups)) for value in deltas[group]
        )
        for _ in range(samples)
    )
    return {
        "mean_delta": statistics.mean(
            int(b["success"]) - int(a["success"]) for a, b in zip(before, after, strict=True)
        ),
        "ci95": [boots[int(0.025 * samples)], boots[min(samples - 1, int(0.975 * samples))]],
        "resampling_families": len(groups),
        "samples": samples,
        "limitation": "Four families per split; descriptive pilot, not a confirmatory significance claim.",
    }


def worker(path, episodes, arm, recipe):
    store = SQLiteMemoryStore(path)
    before = database_digest(path)
    memory = CognitiveMemory(store)
    rows, elapsed, cpu = [], [], []
    for episode in episodes:
        for task in episode["tasks"]:
            # No family/split/world/oracle/expected-label fields enter this request.
            request = {"topic": task["topic"], "checks": task["checks"], "instruction": INSTRUCTION}
            reference = None
            for _ in range(recipe["repetitions"]):
                wall, processor = perf_counter_ns(), process_time_ns()
                context = context_for(memory, task, arm, recipe)
                decision = decide(request, context)
                elapsed.append((perf_counter_ns() - wall) / 1e6)
                cpu.append((process_time_ns() - processor) / 1e6)
                validate_context(store, task, context)
                if reference is not None and decision != reference:
                    raise ValueError("Nondeterministic fixed agent")
                reference = decision
            rows.append(score(episode, task, request, context, decision))
    unchanged = before == database_digest(path)
    if not unchanged:
        raise ValueError("Replay mutated canonical memory")
    ordered = sorted(elapsed)
    return {
        "arm": arm,
        "pid": os.getpid(),
        "rows": rows,
        "canonical_digest_before": before,
        "canonical_unchanged": unchanged,
        "safety": {
            "scope_time_provenance": "PASS: every delivered context citation revalidated",
            "canonical_writes_during_replay": 0,
            "instruction_handling": "Rule-parser data only; model injection-following NOT MEASURED",
        },
        "process_after_ingest": True,
        "cost": {
            "request_p50_ms": statistics.median(elapsed),
            "request_p95_ms": ordered[ceil(0.95 * len(ordered)) - 1],
            "cpu_median_ms": statistics.median(cpu),
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "database_bytes": path.stat().st_size,
            "note": "Includes first request; validation/scoring excluded. Not a cold-start or concurrency study.",
        },
    }


def run(recipe, recipe_path=RECIPE):
    episodes = cases(recipe)
    arms = {}
    with tempfile.TemporaryDirectory(prefix="aams-cognitive-") as root:
        for arm in ARMS:
            path = Path(root) / (arm + ".db")
            common = [
                sys.executable,
                "-I",
                str(Path(__file__).resolve()),
                "--recipe",
                str(recipe_path.resolve()),
                "--db",
                str(path),
            ]
            prepared = subprocess.run(
                [*common, "--prepare"], check=True, capture_output=True, text=True, timeout=60
            )
            completed = subprocess.run(
                [*common, "--arm", arm], check=True, capture_output=True, text=True, timeout=120
            )
            arms[arm] = json.loads(completed.stdout)
            arms[arm]["prepare_pid"] = json.loads(prepared.stdout)["pid"]
            arms[arm]["summary"] = {
                split: summarize([row for row in arms[arm]["rows"] if row["split"] == split])
                for split in ("design", "heldout")
            }
    return {
        "status": "completed_rule_agent_pilot",
        "tested_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], text=True
        ).strip(),
        "policy_version": POLICY_VERSION,
        "instruction_sha256": sha256(INSTRUCTION.encode()).hexdigest(),
        "retrieval_effectiveness": "NOT SCORED: this pilot scores decisions, not retrieval relevance labels",
        "recipe_sha256": sha256(recipe_path.read_bytes()).hexdigest(),
        "source_sha256": json.loads(REGISTRATION.read_text())["source_sha256"],
        "cases_sha256": digest(episodes),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "arms": arms,
        "paired": {
            split: {
                arm: interval(
                    [r for r in arms["raw_search"]["rows"] if r["split"] == split],
                    [r for r in arms[arm]["rows"] if r["split"] == split],
                    recipe["bootstrap_samples"],
                    recipe["bootstrap_seed"],
                )
                for arm in ("no_memory", "structured")
            }
            for split in ("design", "heldout")
        },
        "not_measured": {
            "model_agent": "NOT RUN: no pinned model/prompt evaluation",
            "checkpoint_recovery": "NOT IMPLEMENTED: store/process reopen only",
            "neural_arm": "NOT RUN: separate #109 research",
            "consolidation_transfer": "NOT MEASURED: approved candidates stay staged",
            "shared_memory": "NOT IMPLEMENTED",
            "calibration": "NOT ESTIMATED: no probabilistic output",
        },
        "limitations": [
            "Synthetic simulator labels, not independently observed real-world outcomes.",
            "Fixed grammar/rule policy; no claim of AI reasoning or autonomous learning.",
            "Public author-visible design/heldout families; no tuning after preregistration.",
            "No-memory has an empty historical context and normally abstains.",
            "No resource qualification prerequisite or serving activation.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=RECIPE)
    parser.add_argument("--db", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--prepare", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--arm", choices=ARMS, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("This process RSS protocol requires Linux")
    recipe, _ = verify_registration(args.recipe)
    if args.prepare:
        prepare(args.db, cases(recipe))
        print(json.dumps({"pid": os.getpid()}))
    else:
        print(
            json.dumps(
                worker(args.db, cases(recipe), args.arm, recipe)
                if args.arm
                else run(recipe, args.recipe),
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "invalid_or_failed", "reason": str(error)}))
        sys.exit(3)
