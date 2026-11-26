"""Literal YES/NO recognition and matched one-row evidence sensitivity."""

import argparse
import json
import os
import subprocess
from hashlib import file_digest, sha256
from pathlib import Path

import evaluate_shipment_actor as actor
import evaluate_shipment_gemma as gemma
from cognitive_task_cases import digest
from evaluate_gemma_evidence_diagnostic import reference
from shipment_gemma_literal_cases import pairs

ROOT = Path(__file__).resolve().parent
CASE_PIN = "de449300bf3e966d19c0b26e5c75d62bf992c79f0c6ed30b0a58a8190bc79651"
PROMPT = "shipment_gemma_literal_prompt.txt"
GRAMMAR = "shipment_gemma_literal.gbnf"
QUESTIONS = {
    "A": "Are all current inspections blocked?",
    "B": "Is at least one current inspection clear?",
}
FILES = {
    PROMPT: "4a9b49083dabe79adca5433aa91c6b7ee0a40607b1258848805231e5fa74bba6",
    GRAMMAR: "76c38b9536d0334b07585a12295d7e4980f4ac1a1a4e239e1d8cf0afa53a1327",
    "evaluate_gemma_evidence_diagnostic.py": (
        "5444e23c782a0ef0f279d1e72690af56e180c476db54ae9de5f11e9daa826ff6"
    ),
    "evaluate_shipment_actor.py": gemma.PINS["runner"],
}


def summarize(records, *, forced=None):
    def answer(variant, wording):
        return variant["trials"][wording]["answer"] if forced is None else forced[wording]

    def correct(variant, wording):
        return answer(variant, wording) == variant["expected"][wording]

    variants = [variant for row in records for variant in row["variants"].values()]
    return dict(
        sets=len(variants),
        pairs=len(records),
        accuracy={q: sum(correct(v, q) for v in variants) for q in QUESTIONS},
        invalid={q: sum(answer(v, q) is None for v in variants) for q in QUESTIONS},
        wording_reversals=sum({answer(v, "A"), answer(v, "B")} == {"YES", "NO"} for v in variants),
        both_wordings_correct=sum(all(correct(v, q) for q in QUESTIONS) for v in variants),
        evidence_flips={
            q: sum(
                {answer(v, q) for v in row["variants"].values()} == {"YES", "NO"} for row in records
            )
            for q in QUESTIONS
        },
        both_variants_correct={
            q: sum(all(correct(v, q) for v in row["variants"].values()) for row in records)
            for q in QUESTIONS
        },
    )


def evaluate(infer):
    fixture = pairs()
    if digest(fixture) != CASE_PIN:
        raise ValueError("Fixture drift")
    template = (ROOT / PROMPT).read_text(encoding="utf-8")
    records = []
    for pair_id, rows, latest_ids, decisive, flip_first, blocked_order in fixture:
        if decisive not in latest_ids or any(rows[i - 1][1] != "blocked" for i in latest_ids):
            raise ValueError("Pair lacks the intended all-blocked starting point")
        changed = list(rows)
        day, _, slot = changed[decisive - 1]
        changed[decisive - 1] = (day, "clear", slot)
        source = {"blocked": rows, "changed": changed}
        variant_order = ["changed", "blocked"] if flip_first else ["blocked", "changed"]
        variants = {}
        for name in variant_order:
            _, facts, _ = reference(source[name], latest_ids)
            expected = {
                "A": "YES" if facts["states"] == ["blocked"] else "NO",
                "B": "YES" if "clear" in facts["states"] else "NO",
            }
            facts_text = json.dumps(facts, separators=(",", ":"))
            order = blocked_order if name == "blocked" else blocked_order[::-1]
            trials = {}
            for wording in order:
                prompt = template.format(facts=facts_text, question=QUESTIONS[wording])
                stdout = infer(prompt)
                raw = actor.response_text(stdout)
                trials[wording] = dict(
                    prompt=prompt,
                    prompt_sha256=sha256(prompt.encode()).hexdigest(),
                    stdout=stdout,
                    raw=raw,
                    answer=raw if raw in {"YES", "NO"} else None,
                )
            variants[name] = dict(
                observations=source[name],
                verified=facts,
                expected=expected,
                order=order,
                trials=trials,
            )
        records.append(
            dict(pair=pair_id, decisive=f"R{decisive}", order=variant_order, variants=variants)
        )
    baseline_labels = {
        "always_yes": ("YES", "YES"),
        "always_no": ("NO", "NO"),
        "wording_yes_no": ("YES", "NO"),
        "wording_no_yes": ("NO", "YES"),
    }
    return dict(
        pins=dict(cases=CASE_PIN, files=FILES, model=gemma.PINS["model"], cli=gemma.PINS["cli"]),
        flags=actor.FLAGS,
        questions=QUESTIONS,
        records=records,
        summary=summarize(records),
        baselines={
            key: summarize(records, forced=dict(zip(QUESTIONS, labels)))
            for key, labels in baseline_labels.items()
        },
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    args = parser.parse_args()
    pins = {ROOT / name: pin for name, pin in FILES.items()}
    pins.update({args.model: gemma.PINS["model"], args.cli: gemma.PINS["cli"]})
    for path, pin in pins.items():
        with path.open("rb") as artifact:
            if file_digest(artifact, "sha256").hexdigest() != pin:
                raise ValueError(f"Pin mismatch: {path}")

    def infer(prompt):
        return subprocess.run(
            [
                str(args.cli.resolve()),
                "-m",
                str(args.model.resolve()),
                *actor.FLAGS,
                "--grammar-file",
                str(ROOT / GRAMMAR),
                "-p",
                prompt,
            ],
            text=True,
            capture_output=True,
            check=True,
            timeout=120,
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
        ).stdout

    print(json.dumps(evaluate(infer), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
