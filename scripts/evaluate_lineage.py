"""Run the frozen paired derived-report experiment in a disposable SQLite ledger."""

import json
import random
import sqlite3
import statistics
import tempfile
from pathlib import Path

from aams.recall import CognitiveMemory
from aams.storage import SQLiteMemoryStore
from cognitive_task_agent import INSTRUCTION, decide
from cognitive_task_cases import digest
from evaluate_cognitive_tasks import database_digest, prepare, validate_context
from evaluate_copy_context import candidate_pool, checked_inputs
from evaluate_selection_factorial import selection
from lineage_cases import CONTROLS, DEFAULT, fixtures
from lineage_selector import components, respond
from selection_factorial_cases import cases as factorial_cases

PINS = (
    "36ac0716b0b81be606a33296959c3144fb93e3ed99e30b9f4376fd8400a9bba1",
    "11ca2b667ae5d2f38116c3fa47664d94d8a7eb9ea534b44eac2df9e1310d5c8a",
)
WINDOW = dict(candidate_citations=100, candidate_bytes=65536)


def score(response: dict, label: dict) -> dict:
    """Score source claims and actual decisions after selection is complete."""
    action = response["decision"]["action"]
    expected = label["expected"]
    origins = label["origins"]
    selected = [origins[r["evidence_id"]] for r in response["context"]]
    known = {x for x in selected if x is not None}
    unknown = selected.count(None)
    # Explicit lineage can establish dependence; this interface has no positive attestation.
    return dict(
        action=action,
        correct=action == expected,
        unsafe=action == "proceed" and expected != "proceed",
        retained_known=len(known),
        source_groups=response["source_groups"],
        conflict_seen=response["decision"].get("conflict_detected", False),
        unknown_rows=unknown,
        excess_proxy=None if unknown else max(0, response["source_groups"] - len(known)),
        unsupported_independence_claims=len(response["independent_pairs"]),
    )


def summarize(rows: list) -> dict:
    """Count paired transitions and arm-specific diagnostics on the named set of histories."""
    a, b = ([r["scores"][arm] for r in rows] for arm in "AB")
    return dict(
        n=len(rows),
        corrected_unsafe=sum(x["unsafe"] and y["correct"] for x, y in zip(a, b)),
        correct_lost=sum(x["correct"] and not y["correct"] for x, y in zip(a, b)),
        benign_lost=sum(
            x["correct"] and x["action"] == "proceed" and not y["correct"] for x, y in zip(a, b)
        ),
        unchanged_action=sum(x["action"] == y["action"] for x, y in zip(a, b)),
        arms={
            arm: {
                k: sum(s[k] or 0 for s in scores)
                for k in (
                    "correct",
                    "unsafe",
                    "retained_known",
                    "source_groups",
                    "conflict_seen",
                    "unknown_rows",
                    "excess_proxy",
                    "unsupported_independence_claims",
                )
            }
            for arm, scores in zip("AB", (a, b))
        },
    )


def paired_interval(rows: list, metric: str) -> list:
    """Resample whole families, keeping paired histories together."""
    families = sorted({r["family"] for r in rows})
    effects = [
        statistics.mean(
            int(r["scores"]["B"][metric]) - int(r["scores"]["A"][metric])
            for r in rows
            if r["family"] == family
        )
        for family in families
    ]
    rng = random.Random(0)
    boots = sorted(statistics.mean(rng.choices(effects, k=len(effects))) for _ in range(2000))
    return [statistics.mean(effects), boots[50], boots[1950]]


def run() -> dict:
    """Build the host-visible evidence snapshot and replay the registered arms and shadow controls."""
    cases, keys = fixtures()
    if tuple(map(digest, (cases, keys))) != PINS:
        raise ValueError("Fixture drift")
    _, prior = checked_inputs()
    from cognitive_task_cases import cases as originals

    prior += factorial_cases() + originals(
        json.loads(Path(__file__).with_name("cognitive_task_recipe.json").read_text())
    )
    for field in ("id", "source", "scope"):
        old = {r[field] for e in prior for r in e["observations"]}
        for e in cases:
            own = {r[field] for r in e["observations"]}
            if own & old:
                raise ValueError("Source overlap")
            old.update(own)
    rows = []
    controls = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "memory.db"
        prepare(
            path,
            [
                {
                    **e,
                    "observations": [r for r in e["observations"] if r["id"] not in e["withheld"]],
                }
                for e in cases
            ],
        )
        memory = CognitiveMemory(SQLiteMemoryStore(path))
        before = database_digest(path)
        for e in cases:
            task = e["tasks"][0]
            pool, truncated = (
                candidate_pool(memory, task, WINDOW) if task["allowed"] else ([], False)
            )
            withheld = set(e["withheld"])
            authorized = {
                r["id"]
                for r in e["observations"]
                if task["allowed"]
                and r["scope"] == task["scope"]
                and r["id"] not in withheld
                and r["recorded"] <= task["as_of"]
                and r["observed"] <= task["day"]
            }
            if truncated or authorized != {r["evidence_id"] for r in pool}:
                raise ValueError("Pool differs from eligible source universe")
            a = respond(pool, task, {})
            reference = selection(pool, True)
            req = dict(topic=task["topic"], checks=task["checks"], instruction=INSTRUCTION)
            if reference != a["context"] or decide(req, reference) != a["decision"]:
                raise ValueError("Arm D parity failure")
            for mode in (DEFAULT, *CONTROLS) if e["family"] == "missing" else (DEFAULT,):
                links = e["links"][mode]
                groups = components(memory.store, task, pool, links, withheld)
                b = respond(pool, task, groups)
                validate_context(memory.store, task, b["context"])
                if mode not in (DEFAULT, "visible") and b != a:
                    raise ValueError("Unavailable overlay changed public result")
                if mode == DEFAULT:
                    if e["family"] == "dispute" and not b["decision"]["conflict_detected"]:
                        raise ValueError("Shared-origin conflict lost")
                    rows.append(
                        dict(
                            task=e["id"],
                            family=e["family"],
                            expected=keys[e["id"]]["expected"],
                            pool=pool,
                            window_truncated=truncated,
                            visible_components=groups,
                            responses=dict(A=a, B=b),
                            scores={
                                arm: score(out, keys[e["id"]]) for arm, out in zip("AB", (a, b))
                            },
                        )
                    )
                else:
                    controls.append(
                        dict(
                            task=e["id"],
                            overlay=mode,
                            pool_sha256=digest(pool),
                            response=b,
                            visible_components=groups,
                        )
                    )
        if before != database_digest(path):
            raise ValueError("Ledger changed")
    return dict(
        case_sha256=PINS[0],
        label_sha256=PINS[1],
        database_digest=before,
        sqlite=sqlite3.sqlite_version,
        summary=summarize(rows),
        families={
            f: summarize([r for r in rows if r["family"] == f])
            for f in sorted({r["family"] for r in rows})
        },
        paired={k: paired_interval(rows, k) for k in ("correct", "unsafe")},
        rows=rows,
        controls=controls,
    )


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
