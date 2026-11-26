"""Run one locally pinned Gemma actor through the frozen #139 shipment gate."""

import argparse
import json
from hashlib import file_digest
from pathlib import Path

import evaluate_shipment_actor as actor
from cognitive_task_cases import digest
from shipment_gemma_cases import qualification

ROOT = Path(__file__).resolve().parent
PINS = {
    "model": "04a43a22e8d2003deda5acc262f68ec1005fa76c735a9962a8c77042a74a7d19",
    "cli": actor.PINS["cli"],
    "prompt": "079c3e9e863f3085cead46a47eebdea7ec3b1bffbbf0f289c0956ca7571cfd62",
    "grammar": actor.PINS["grammar"],
    "qualification": "fc4ea2337f001b5f5ad1e942703d931856abe907c4940cc9a203282ffc64ae73",
    "runner": "3be67b6b5b23f734d509da8205c88f9e4d44ba1e24cc873394ce4c874f190923",
    "held_out_source": "db66b999a585f5e74868519b44cdd9d3f4a1d8705a551d7a87a102a245430e34",
}


def run(infer):
    cases = qualification()
    if digest(cases) != PINS["qualification"]:
        raise ValueError("Qualification case drift")
    traces = [
        dict(case=case, expected=expected, rotation=rotation, **infer(rows, rotation, expected))
        for i, (case, expected, rows) in enumerate(cases)
        for rotation in ((i + step) % 3 for step in range(3))
    ]
    supported = sum(row["scores"]["supported_correct"] for row in traces)
    passed = supported == len(traces) == 18
    return dict(
        pins=PINS,
        flags=actor.FLAGS,
        qualification=traces,
        supported_correct=supported,
        qualified=passed,
        comparison=actor.comparison_run(infer) if passed else None,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    args = parser.parse_args()
    prompt = ROOT / "shipment_gemma_prompt.txt"
    grammar = ROOT / "shipment_actor_response.gbnf"
    artifacts = {
        "model": args.model,
        "cli": args.cli,
        "prompt": prompt,
        "grammar": grammar,
        "runner": ROOT / "evaluate_shipment_actor.py",
        "held_out_source": ROOT / "shipment_actor_cases.py",
    }
    for name, path in artifacts.items():
        with path.open("rb") as artifact:
            if file_digest(artifact, "sha256").hexdigest() != PINS[name]:
                raise ValueError(f"Pin mismatch: {name}")
    template = prompt.read_text(encoding="utf-8")

    def infer(rows, rotation, expected):
        return actor.execute(
            args.model.resolve(), args.cli.resolve(), template, grammar, rows, rotation, expected
        )

    print(json.dumps(run(infer), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
