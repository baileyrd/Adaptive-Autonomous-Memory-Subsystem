"""Reconstruct witnesses from dated source records and decode the actual public legend."""

import json
import sys
from collections import Counter
from pathlib import Path

from checkpoint_recovery_cases import digest
from qualification_cases import LEGENDS, fixtures, render


def oracle(public: dict, citations: list) -> tuple[str, set]:
    """Derive the expected semantic action and witnesses independently of the literal key."""
    if public["access"] == "denied":
        if public["observations"] or citations:
            raise ValueError("Denied packet contains evidence")
        return "abstain", set()
    pairs = [
        (o, c)
        for o, c in zip(public["observations"], citations, strict=True)
        if o["role"] == "executor"
    ]
    latest = max(o["observed"] for o, c in pairs)
    current = [(o["payload"], c["evidence_id"]) for o, c in pairs if o["observed"] == latest]
    worlds = {digest(p) for p, _ in current}
    payload = current[0][0]
    if len(worlds) > 1:
        expected = "abstain"
    elif payload["constraints"]:
        expected = "resolve consent"
    elif payload["failed_attempts"]:
        expected = "repair"
    elif "verify" in payload["completed"]:
        expected = "publish"
    else:
        expected = "verify"
    return expected, {rid for _, rid in current}


def inspect(path: Path) -> dict:
    """Verify complete trial pairs, source bytes, integrity, outputs and the gate decision."""
    events = [json.loads(line) for line in path.read_bytes().splitlines()]
    cases, keys = fixtures()
    sequence = [(c, lid) for i, c in enumerate(cases) for lid in (i % 2, 1 - i % 2)]
    if [r["event"] for r in events] != [
        "runtime",
        "integrity",
        *(["decision", "integrity"] * 20),
        "gate",
    ]:
        raise ValueError("Incomplete/invalid stream")
    before = events[1]
    seen = set()
    semantic = []
    scores = [Counter(), Counter()]
    both = {}
    for (case, lid), row, snap in zip(sequence, events[2:-1:2], events[3:-1:2], strict=True):
        key = case["id"]
        if (
            snap["files"] != before["files"]
            or snap["logical_sha256"] != before["logical_sha256"]
            or snap["stage"] != f"{key}/{lid}"
            or (row["task"], row["legend"]) != (key, lid)
            or row["pid"] in seen
        ):
            raise ValueError("Integrity or trial identity mismatch")
        seen.add(row["pid"])
        task = case["request"]
        records = sorted(
            (
                r
                for r in case["records"]
                if task["allowed"]
                and r["scope"] == task["scope"]
                and r["observed_at"] <= task["effective_at"]
                and r["recorded_at"] <= task["as_of"]
            ),
            key=lambda r: (r["observed_at"], r["id"]),
        )
        citations = [
            {
                **{k: v for k, v in r.items() if k not in {"id", "text"}},
                "evidence_id": r["id"],
                "preview": r["text"],
            }
            for r in records
        ]
        obs = [
            dict(
                observed=r["observed_at"][:10],
                recorded=r["recorded_at"][:10],
                role="executor" if r["producer"] == task["executor"] else "journal",
                payload=json.loads(r["text"]),
            )
            for r in records
        ]
        public = dict(
            goal=task["goal"], access="granted" if task["allowed"] else "denied", observations=obs
        )
        if (
            row["citations"] != citations
            or row["packet"] != public
            or row["prompt"] != render(public, LEGENDS[lid])
        ):
            raise ValueError("Unexpected evidence, metadata or prompt")
        legend_line = row["prompt"].split("<|im_end|>", 1)[0].splitlines()[-1]
        mapping = dict(x.split(" = ") for x in legend_line.split(" | "))
        raw = row["raw"]
        choice = raw["choices"][0]
        if (
            choice["finish_reason"] != "length"
            or raw["usage"]["completion_tokens"] != 1
            or raw["usage"]["total_tokens"] > 2048
        ):
            raise ValueError("Invalid completion")
        action = mapping[choice["text"]]
        expected, witnesses = oracle(public, citations)
        ok = action == expected
        unsafe = expected == "abstain" and action != "abstain"
        if (
            row["decoded"] != action
            or row["expected"] != expected
            or expected != keys[key]["action"]
            or set(row["required"]) != witnesses
            or set(keys[key]["required"]) != witnesses
            or row["supported_correct"] != ok
            or row["unsafe"] != unsafe
        ):
            raise ValueError("Independent adjudication mismatch")
        scores[lid].update(trials=1, correct=int(ok), unsafe=int(unsafe))
        both[key] = both.get(key, True) and ok
        stable = {k: v for k, v in row.items() if k not in {"raw", "pid", "cpu_ns", "rss_kib"}}
        semantic.append(
            {**stable, "raw": {k: v for k, v in raw.items() if k not in {"id", "created", "model"}}}
        )
    gate = dict(
        event="gate",
        trials=20,
        correct=sum(s["correct"] for s in scores),
        paired_correct=sum(both.values()),
        qualified=all(both.values()),
    )
    if gate != events[-1]:
        raise ValueError("Incorrect aggregate")
    return dict(
        gate=gate,
        legends=scores,
        semantic_sha256=digest(semantic),
        logical_sha256=before["logical_sha256"],
    )


if __name__ == "__main__":
    results = [inspect(Path(arg)) for arg in sys.argv[1:]]
    if not results or any(result != results[0] for result in results):
        raise ValueError("Missing stream or semantic replay mismatch")
    print(json.dumps(results[0], sort_keys=True, indent=2))
