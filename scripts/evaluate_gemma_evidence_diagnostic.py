"""Three isolated conditions on the pinned #140 Gemma actor."""

import argparse
import itertools
import json
import os
import subprocess
from collections import Counter
from hashlib import file_digest, sha256
from pathlib import Path

import evaluate_shipment_actor as actor
import evaluate_shipment_gemma as gemma
from cognitive_task_cases import digest
from shipment_gemma_diagnostic_cases import cases

ROOT = Path(__file__).resolve().parent
CASE_PIN = "03f413a3cbda687c020097cd71cf0237927d22f528a83c234bf69854a563a81b"
FILES = {
    "shipment_gemma_prompt.txt": gemma.PINS["prompt"],
    "shipment_actor_response.gbnf": gemma.PINS["grammar"],
    "evaluate_shipment_actor.py": gemma.PINS["runner"],
    "shipment_gemma_extract_prompt.txt": (
        "e4aeb06c8288d3a8714bc2dcf470b5414c9cc509dff74aee03229b66ee1ca1a6"
    ),
    "shipment_gemma_extract.gbnf": "cd0ba5224a475e52e06f003e68bdc01fa430db2ef58dee678aa026d03b9828e0",
    "shipment_gemma_verified_prompt.txt": (
        "ef92bac19c129dbbfdb4b8bd9b4e23875ca5f6cbcf005ed81221947e7ca0e33f"
    ),
}
ACTION_GRAMMAR = "shipment_actor_response.gbnf"
EXTRACTION_GRAMMAR = "shipment_gemma_extract.gbnf"
FIELDS = ("states", "slots", "rows")


def reference(rows, checked_ids):
    latest_day = max(row[0] for row in rows)
    if tuple(i for i, row in enumerate(rows, 1) if row[0] == latest_day) != checked_ids:
        raise ValueError("Checked row IDs disagree with source timestamps")
    latest = {f"R{i}": rows[i - 1] for i in checked_ids}
    states = sorted({state for _, state, _ in latest.values()})
    slots = sorted({slot for _, _, slot in latest.values() if slot is not None})
    facts = dict(
        states=states,
        slots=slots,
        rows=[[rid, state, slot] for rid, (_, state, slot) in latest.items()],
    )
    if states == ["blocked"]:
        expected = "stop"
    elif states == ["clear"] and len(slots) >= 2:
        expected = "proceed"
    else:
        expected = "abstain"
    return latest, facts, expected


def extraction_score(raw, facts):
    try:
        output = json.loads(raw)
    except ValueError:
        output = None
    valid = (
        isinstance(output, dict)
        and set(output) == set(FIELDS)
        and all(isinstance(output[field], list) for field in FIELDS)
        and all(isinstance(x, str) for field in ("states", "slots") for x in output[field])
        and all(
            isinstance(row, list)
            and len(row) == 3
            and isinstance(row[0], str)
            and isinstance(row[1], str)
            and (row[2] is None or isinstance(row[2], str))
            for row in output["rows"]
        )
    )
    if not valid:
        return dict(
            parsed=output, malformed=True, exact=False, missing=None, invented=None, duplicates=None
        )

    missing, invented, duplicates = {}, {}, {}
    for field in FIELDS:
        gold = {json.dumps(value) for value in facts[field]}
        seen = Counter(json.dumps(value) for value in output[field])
        missing[field] = [json.loads(value) for value in sorted(gold - seen.keys())]
        invented[field] = [json.loads(value) for value in sorted(seen.keys() - gold)]
        duplicates[field] = [json.loads(value) for value in sorted(seen) if seen[value] > 1]
    return dict(
        parsed=output,
        malformed=False,
        missing=missing,
        invented=invented,
        duplicates=duplicates,
        exact=not any(any(delta.values()) for delta in (missing, invented, duplicates)),
    )


def evaluate(infer):
    fixture = cases()
    if digest(fixture) != CASE_PIN:
        raise ValueError("Fixture drift")
    a_template = (ROOT / "shipment_gemma_prompt.txt").read_text()
    b_template = (ROOT / "shipment_gemma_extract_prompt.txt").read_text()
    c_template = (ROOT / "shipment_gemma_verified_prompt.txt").read_text()
    records = []
    for i, ((case_id, rows, checked_ids), order) in enumerate(
        zip(fixture, itertools.permutations("ABC"), strict=True)
    ):
        packet = {f"R{j}": row for j, row in enumerate(rows, 1)}
        latest, facts, expected = reference(rows, checked_ids)
        mapping = actor.legend(i // 3)
        legend = "\n".join(f"{key} = {actor.DISPLAY[value]}" for key, value in mapping.items())
        evidence = "\n".join(
            f"{rid} | {day} | {state} | {slot or '-'}" for rid, (day, state, slot) in packet.items()
        )
        prompts = {
            "A": actor.prompt_for(a_template, packet, mapping),
            "B": b_template.format(evidence=evidence),
            "C": c_template.format(legend=legend, facts=json.dumps(facts, separators=(",", ":"))),
        }
        outputs = {}
        for condition in order:
            prompt = prompts[condition]
            grammar = EXTRACTION_GRAMMAR if condition == "B" else ACTION_GRAMMAR
            stdout = infer(prompt, grammar)
            raw = actor.response_text(stdout)
            if condition == "B":
                score = extraction_score(raw, facts)
            else:
                visible = packet if condition == "A" else latest
                score = actor.assess(raw, visible, mapping, expected)
            outputs[condition] = dict(
                prompt=prompt,
                prompt_sha256=sha256(prompt.encode()).hexdigest(),
                grammar=grammar,
                stdout=stdout,
                raw=raw,
                **score,
            )
        a, b, c = (outputs[condition] for condition in "ABC")
        records.append(
            dict(
                case=case_id,
                rows=packet,
                verified=facts,
                expected=expected,
                legend=mapping,
                order="".join(order),
                conditions=outputs,
                aggregation_rescue=not b["exact"]
                and not a["scores"]["supported_correct"]
                and c["scores"]["supported_correct"],
                persistent_abstention=expected != "abstain"
                and a["action"] == c["action"] == "abstain",
            )
        )
    return dict(
        pins=dict(files=FILES, cases=CASE_PIN, model=gemma.PINS["model"], cli=gemma.PINS["cli"]),
        flags=actor.FLAGS,
        records=records,
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

    def infer(prompt, grammar):
        return subprocess.run(
            [
                str(args.cli.resolve()),
                "-m",
                str(args.model.resolve()),
                *actor.FLAGS,
                "--grammar-file",
                str(ROOT / grammar),
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
