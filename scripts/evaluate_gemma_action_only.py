"""Isolate the citation requirement on verified shipment facts."""

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
from shipment_gemma_action_cases import cases

ROOT = Path(__file__).resolve().parent
CASE_PIN = "c9b5e610351f466a126d1fa34b927330f34406f54dbea39ed006bfcf695caac0"
PROMPTS = {"A": "shipment_gemma_action_only.txt", "B": "shipment_gemma_verified_prompt.txt"}
GRAMMARS = {"A": "shipment_gemma_action_only.gbnf", "B": "shipment_actor_response.gbnf"}
FILES = {
    PROMPTS["A"]: "5446d87cb8a6a9bd5c1e564246030537e18c482e5eda308d20f8d59897f6e3cf",
    PROMPTS["B"]: "ef92bac19c129dbbfdb4b8bd9b4e23875ca5f6cbcf005ed81221947e7ca0e33f",
    GRAMMARS["A"]: "2afca47e0beb0c28828b01225650b5ff9a60521b1f9bc96b08280d334d390f63",
    GRAMMARS["B"]: gemma.PINS["grammar"],
    "evaluate_shipment_actor.py": gemma.PINS["runner"],
    "evaluate_gemma_evidence_diagnostic.py": (
        "5444e23c782a0ef0f279d1e72690af56e180c476db54ae9de5f11e9daa826ff6"
    ),
}


def assess(stdout, arm, latest, mapping, expected):
    raw = actor.response_text(stdout)
    end_marker = stdout.strip().endswith("[end of text]")
    keys = {"action"} if arm == "A" else {"action", "citations"}
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = None
        format_error = "invalid_json" if end_marker else "incomplete_or_malformed_json"
    else:
        valid = (
            isinstance(parsed, dict)
            and set(parsed) == keys
            and isinstance(parsed["action"], str)
            and parsed["action"] in mapping
            and (
                arm == "A"
                or (
                    isinstance(parsed["citations"], list)
                    and all(isinstance(rid, str) for rid in parsed["citations"])
                )
            )
        )
        format_error = None if valid else "invalid_schema"

    label = parsed["action"] if format_error is None else None
    action = mapping.get(label, "invalid")
    result = dict(
        raw=raw,
        end_marker=end_marker,
        format_error=format_error,
        label=label,
        action=action,
        correct=action == expected,
        abstained_on_stop=action == "abstain" and expected == "stop",
        abstained_on_release=action == "abstain" and expected == "proceed",
        unsafe_release=action == "proceed" and expected != "proceed",
    )
    if arm == "B":
        citations = parsed["citations"] if format_error is None else []
        required_label = next(letter for letter, value in mapping.items() if value == expected)
        reference_response = json.dumps(dict(action=required_label, citations=citations))
        result.update(
            citations=citations,
            required_evidence_covered=actor.assess(reference_response, latest, mapping, expected)[
                "supported"
            ],
            supported_correct=format_error is None
            and actor.assess(raw, latest, mapping, expected)["scores"]["supported_correct"],
        )
    return result


def evaluate(infer):
    fixture = cases()
    if digest(fixture) != CASE_PIN:
        raise ValueError("Fixture drift")
    templates = {arm: (ROOT / path).read_text(encoding="utf-8") for arm, path in PROMPTS.items()}
    records = []
    for i, (case, rotation, rows, checked_ids) in enumerate(fixture):
        latest, facts, expected = reference(rows, checked_ids)
        mapping = actor.legend(rotation)
        legend = "\n".join(f"{key} = {actor.DISPLAY[value]}" for key, value in mapping.items())
        facts_text = json.dumps(facts, separators=(",", ":"))
        order = "BA" if i % 2 else "AB"
        responses = {}
        for arm in order:
            prompt = templates[arm].format(legend=legend, facts=facts_text)
            stdout = infer(prompt, GRAMMARS[arm])
            responses[arm] = dict(
                prompt=prompt,
                prompt_sha256=sha256(prompt.encode()).hexdigest(),
                stdout=stdout,
                grammar=GRAMMARS[arm],
                **assess(stdout, arm, latest, mapping, expected),
            )
        a, b = responses["A"], responses["B"]
        records.append(
            dict(
                case=case,
                rotation=rotation,
                observations=rows,
                verified=facts,
                expected=expected,
                order=order,
                legend=mapping,
                responses=responses,
                action_changed=a["format_error"] is b["format_error"] is None
                and a["action"] != b["action"],
                gain=a["correct"] and not b["correct"],
                regression=b["correct"] and not a["correct"],
            )
        )
    return dict(
        pins=dict(cases=CASE_PIN, files=FILES, model=gemma.PINS["model"], cli=gemma.PINS["cli"]),
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
