"""Run the fixed AAMS governed-learning evaluation against scoped lexical recall."""

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns

from aams.consolidation import propose
from aams.contracts import EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind
from aams.learning import CandidateState, CandidateTransitionRequest
from aams.ranking import LexicalRanking
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.storage import AccessContext, SQLiteMemoryStore

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/learning_evaluation.json"
TIME = "2026-01-01T00:00:00Z"


def seed(store, fixture):
    for identifier, scope, producer, source, locator, text in fixture["evidence"]:
        access = AccessContext(producer, scope, True)
        payload = text.encode()
        digest = "sha256:" + sha256(payload).hexdigest()
        record = Evidence(
            identifier,
            scope,
            source,
            locator,
            producer,
            TIME,
            TIME,
            EvidenceStatus.RECORDED,
            payload,
            digest,
        )
        formation = MemoryFormation(
            "formation-" + identifier,
            scope,
            MemoryKind.EXPERIENCE,
            (identifier,),
            producer,
            TIME,
            EpistemicState.OBSERVED,
        )
        store.ingest(access, identifier, formation, (record,))


def review(store, candidate, reviewer):
    for version, old, new in (
        (0, CandidateState.PROPOSED, CandidateState.VALIDATED),
        (1, CandidateState.VALIDATED, CandidateState.APPROVED),
    ):
        request = CandidateTransitionRequest(
            candidate.candidate_id,
            candidate.scope,
            old,
            new,
            reviewer.principal,
            "Apply scoped fixture approval policy.",
            TIME,
        )
        try:
            store.decide_candidate(reviewer, new.value, version, request)
        except PermissionError:
            if new is not CandidateState.APPROVED:
                raise
            rejection = CandidateTransitionRequest(
                candidate.candidate_id,
                candidate.scope,
                old,
                CandidateState.REJECTED,
                reviewer.principal,
                "Insufficient independent support or recorded refutation.",
                TIME,
            )
            store.decide_candidate(reviewer, "rejected", version, rejection)
            return False
    return True


def read_restart(path, identifiers):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--verify", str(path)],
        input=json.dumps(identifiers),
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    )
    return json.loads(result.stdout)


def verify_child(path):
    store = SQLiteMemoryStore(path)
    store.verify_integrity()
    access = AccessContext("proposer", "eval")
    foreign = AccessContext("outsider", "private")
    output = {}
    for identifier in json.load(sys.stdin):
        record = store.get_candidate(access, identifier)
        validation = store.validate_candidate(access, identifier)
        output[record.proposal.claim] = {
            "state": record.state.value,
            "versions": [decision.version for decision in record.history],
            "support_groups": len(validation.independent_support),
            "refutations": list(validation.refute_ids),
            "canonical": store.get_belief(access, identifier) is not None,
            "foreign_visible": store.get_candidate(foreign, identifier) is not None,
        }
    return output


def evaluate(path, repetitions):
    fixture = json.loads(FIXTURE.read_text())
    store = SQLiteMemoryStore(path)
    seed(store, fixture)
    author = AccessContext("proposer", "eval", True)
    reviewer = AccessContext("reviewer", "eval", True, True)
    # Historical baselines keep the legacy ranker so published audits stay reproducible.
    memory = CognitiveMemory(store, lexical_ranking=LexicalRanking.OVERLAP)

    def baseline():
        return {
            query: {
                edge["evidence_id"]
                for item in memory.recall(author, CognitiveNeed(query=query, max_items=2))["items"]
                for edge in item["citations"]
            }
            for query in fixture["tasks"]
        }

    def generation():
        return propose(store, author, since=TIME, through=TIME)

    def compare():
        packets = baseline()
        for item in generation().proposals:
            if item.claim in packets:
                packets[item.claim].update(item.support_ids + item.refute_ids)
        return packets

    def timed(operation):
        operation()
        durations = []
        for _ in range(repetitions):
            start = perf_counter_ns()
            result = operation()
            durations.append((perf_counter_ns() - start) / 1e6)
        return result, round(statistics.median(durations), 3)

    original, baseline_ms = timed(baseline)
    augmented, augmented_ms = timed(compare)
    batch, generation_ms = timed(generation)
    if batch.truncated:
        raise RuntimeError("Evaluation requires the complete fixture")
    claimed = {item.claim for item in batch.proposals}
    useful = set(fixture["useful_proposals"])
    approved = set()
    for candidate in batch.proposals:
        store.create_candidate(author, candidate.candidate_id, candidate)
        if review(store, candidate, reviewer):
            approved.add(candidate.claim)
    restarted = read_restart(path, [item.candidate_id for item in batch.proposals])

    def tasks(packets):
        return sum(set(required) <= packets[query] for query, required in fixture["tasks"].items())

    return {
        "proposal_precision": len(claimed & useful) / len(claimed),
        "proposal_recall": len(claimed & useful) / len(useful),
        "proposals": sorted(claimed),
        "approvals": sorted(approved),
        "false_approvals": len(approved - set(fixture["approvable"])),
        "canonical_promotions": sum(item["canonical"] for item in restarted.values()),
        "foreign_candidates_visible": sum(item["foreign_visible"] for item in restarted.values()),
        "baseline_tasks_complete": tasks(original),
        "augmented_tasks_complete": tasks(augmented),
        "task_count": len(fixture["tasks"]),
        "baseline_evidence_links": sum(map(len, original.values())),
        "augmented_evidence_links": sum(map(len, augmented.values())),
        "baseline_median_ms": baseline_ms,
        "augmented_median_ms": augmented_ms,
        "proposal_scan_median_ms": generation_ms,
        "restarted_records": restarted,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--verify", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("Use at least one repetition")
    if args.verify:
        result = verify_child(args.verify)
    else:
        with tempfile.TemporaryDirectory(prefix="aams-learning-") as directory:
            result = evaluate(Path(directory) / "memory.db", args.repetitions)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
