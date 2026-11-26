"""Paired direct predicate and shipment action in independent local sessions."""

import argparse
import json
import os
import subprocess
from hashlib import file_digest, sha256
from pathlib import Path

import evaluate_gemma_action_only as action
import evaluate_shipment_actor as actor
import evaluate_shipment_gemma as gemma
from cognitive_task_cases import digest
from evaluate_gemma_evidence_diagnostic import reference
from shipment_gemma_blocked_cases import cases

ROOT = Path(__file__).resolve().parent
CASE_PIN = "094a33e1d0520b6c0523c77662c1c12238118bebbd0822341472e0062c03c4b2"
PROMPTS = {"P": "shipment_gemma_blocked_prompt.txt", "A": action.PROMPTS["A"]}
GRAMMARS = {"P": "shipment_gemma_blocked.gbnf", "A": action.GRAMMARS["A"]}
FILES = {
    PROMPTS["P"]: "c42c1c5d87e5fb61b404ee6cd65a5c5ef4039629f620e8c70fd2785c222ee9cd",
    GRAMMARS["P"]: "b0418af279d4212b83d404ccd78f893299f1f380c0612408daf2c064defea3ee",
    PROMPTS["A"]: action.FILES[PROMPTS["A"]],
    GRAMMARS["A"]: action.FILES[GRAMMARS["A"]],
    "evaluate_gemma_action_only.py": (
        "cbfc99494d17c58c5c4b786483ea3f8e2f097798c9623b6c182a9f8ff5f8a020"
    ),
    "evaluate_gemma_evidence_diagnostic.py": action.FILES["evaluate_gemma_evidence_diagnostic.py"],
    "evaluate_shipment_actor.py": gemma.PINS["runner"],
}


def predicate_score(stdout, mapping, expected):
    raw = actor.response_text(stdout)
    try:
        item = json.loads(raw)
    except ValueError:
        item = None
    label = item["answer"] if isinstance(item, dict) and set(item) == {"answer"} else None
    answer = mapping.get(label) if isinstance(label, str) else None
    return dict(
        raw=raw,
        label=label,
        answer=answer,
        malformed=answer is None,
        correct=answer == expected,
    )


def evaluate(infer):
    fixture = cases()
    if digest(fixture) != CASE_PIN:
        raise ValueError("Fixture drift")
    templates = {
        name: (ROOT / filename).read_text(encoding="utf-8") for name, filename in PROMPTS.items()
    }
    results = []
    for i, (case_id, reverse, order, rows, latest_ids) in enumerate(fixture):
        latest, verified, expected_action = reference(rows, latest_ids)
        expected_predicate = "YES" if verified["states"] == ["blocked"] else "NO"
        predicate_mapping = dict(zip("AB", ("NO", "YES") if reverse else ("YES", "NO")))
        action_mapping = actor.legend(i % 3)
        mappings = {"P": predicate_mapping, "A": action_mapping}
        legends = {
            "P": predicate_mapping,
            "A": {letter: actor.DISPLAY[value] for letter, value in action_mapping.items()},
        }
        facts = json.dumps(verified, separators=(",", ":"))
        prompts = {
            name: template.format(
                facts=facts,
                legend="\n".join(f"{letter} = {word}" for letter, word in legends[name].items()),
            )
            for name, template in templates.items()
        }
        trials = {}
        for name in order:
            prompt = prompts[name]
            stdout = infer(prompt, GRAMMARS[name])
            score = (
                predicate_score(stdout, predicate_mapping, expected_predicate)
                if name == "P"
                else action.assess(stdout, "A", latest, action_mapping, expected_action)
            )
            trials[name] = dict(
                prompt=prompt,
                prompt_sha256=sha256(prompt.encode()).hexdigest(),
                grammar=GRAMMARS[name],
                stdout=stdout,
                **score,
            )
        predicate = trials["P"]["answer"]
        chosen = trials["A"]["action"]
        results.append(
            dict(
                case=case_id,
                observations=rows,
                verified=verified,
                expected_action=expected_action,
                expected_predicate=expected_predicate,
                order=order,
                mappings=mappings,
                trials=trials,
                recognized_but_no_stop=expected_predicate == predicate == "YES"
                and chosen != "stop",
                failed_to_recognize=expected_predicate == "YES" and predicate == "NO",
            )
        )
    return dict(
        pins=dict(cases=CASE_PIN, files=FILES, model=gemma.PINS["model"], cli=gemma.PINS["cli"]),
        flags=actor.FLAGS,
        records=results,
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
