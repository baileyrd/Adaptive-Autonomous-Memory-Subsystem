"""Independently inspect published packet provenance, paired outcomes and replay equivalence."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median

from evaluate_q4_resume import ACTIONS, ARMS, adjudicate, fixtures, packet, prompt


def inspect(path: Path) -> dict:
    """Validate the event stream against fixture sources and return reproducible scorecards."""
    events = [json.loads(line) for line in path.read_bytes().splitlines()]
    cases, labels = fixtures()
    by_id = {c["id"]: c for c in cases}
    snapshots = [e for e in events if e["event"] == "integrity"]
    assert [s["stage"] for s in snapshots] == ["prepare", "full_evidence", *ARMS]
    for s in snapshots:
        assert (s["files"], s["logical_sha256"]) == (
            snapshots[0]["files"],
            snapshots[0]["logical_sha256"],
        )
    expected = {
        (c["id"], a)
        for c in cases
        for a in (("full_evidence",) if c["split"] == "diagnostic" else ARMS)
    }
    rows = [e for e in events if e["event"] == "decision"]
    assert {(r["task_id"], r["arm"]) for r in rows} == expected and len(rows) == len(expected)
    assert len({r["pid"] for r in rows}) == len(rows)
    for r in rows:
        case = by_id[r["task_id"]]
        task = case["request"]
        assert r["split"] == case["split"] and r["family"] == case["family"]
        source = {s["id"]: s for s in case["records"]}
        for citation in r["citations"]:
            original = source[citation["evidence_id"]]
            assert task["allowed"] and original["scope"] == task["scope"]
            assert (
                original["recorded_at"] <= task["as_of"]
                and original["observed_at"] <= task["effective_at"]
            )
            assert all(
                citation[k] == original[k]
                for k in (
                    "scope",
                    "source_locator",
                    "source_actor",
                    "producer",
                    "observed_at",
                    "recorded_at",
                    "digest",
                )
            )
            assert citation["preview"] == original["text"]
        assert prompt(packet(task, r["citations"])) == r["prompt"]
        action = ACTIONS[r["raw"]["choices"][0]["text"]]
        assert r["raw"]["usage"]["total_tokens"] <= 2048
        expected_scores = adjudicate(
            case,
            labels[case["id"]],
            action,
            [c["evidence_id"] for c in r["citations"]],
            r["candidates"],
            r["arm"],
        )
        assert all(r[k] == v for k, v in expected_scores.items())
    metrics = (
        "success",
        "raw_correct",
        "correct_resumption",
        "denial",
        "conflict_abstention",
        "incorrect_abstention",
        "unsupported_guess",
        "unsupported_action",
        "unsafe",
        "invented_progress",
        "repeated_work",
        "repeated_failure",
        "lost_constraint",
    )
    splits, families = {}, {}
    for split, arm in sorted({(r["split"], r["arm"]) for r in rows}):
        group = [r for r in rows if (r["split"], r["arm"]) == (split, arm)]
        summary = {k: sum(r[k] for r in group) for k in metrics}
        summary.update(
            n=len(group),
            actions=dict(Counter(r["action"] for r in group)),
            consequences=dict(Counter(r["consequence"] for r in group)),
            stages=dict(Counter(r["stage"] for r in group)),
            disclosures=0,
            authorized_decisive_sets=sum(
                r["decisive_present"] for r in group if r["family"] != "revoked"
            ),
            median_elapsed_ms=median(r["elapsed_ns"] for r in group) / 1e6,
            median_actor_cpu_ms=median(r["cpu_ns"] for r in group) / 1e6,
            max_actor_rss_kib=max(r["rss_kib"] for r in group),
            max_prompt_tokens=max(r["raw"]["usage"]["prompt_tokens"] for r in group),
        )
        splits.setdefault(split, {})[arm] = summary
        for family in sorted({r["family"] for r in group}):
            members = [r for r in group if r["family"] == family]
            families.setdefault(split, {}).setdefault(family, {})[arm] = {
                "n": len(members),
                "supported": sum(r["success"] for r in members),
            }
    effects = {}
    for c in cases:
        if c["split"] != "heldout":
            continue
        paired = {r["arm"]: r["success"] for r in rows if r["task_id"] == c["id"]}
        effects[c["id"]] = int(paired["checkpoint"]) - int(paired["structured"])
    assert events[-1]["event"] == "comparison"
    deterministic = []
    for r in rows:
        raw = {k: v for k, v in r["raw"].items() if k not in {"created", "id", "model"}}
        semantic = {
            k: v for k, v in r.items() if k not in {"raw", "pid", "rss_kib", "cpu_ns", "elapsed_ns"}
        }
        deterministic.append({**semantic, "raw": raw})
    canonical = json.dumps(deterministic, sort_keys=True, separators=(",", ":")).encode()
    return dict(
        splits=splits,
        families=families,
        paired_effects=effects,
        comparison=events[-1],
        semantic_sha256=hashlib.sha256(canonical).hexdigest(),
        logical_sha256=snapshots[0]["logical_sha256"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.events), sort_keys=True, indent=2))
