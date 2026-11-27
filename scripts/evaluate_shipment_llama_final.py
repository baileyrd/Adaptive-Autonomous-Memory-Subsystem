"""Replay the final shipment qualification with the frozen Llama 3.2 configuration."""

import argparse
import json
from hashlib import file_digest, sha256
from pathlib import Path

import evaluate_shipment_actor as actor
import evaluate_shipment_gemma as gate

MODEL = "dde5aa3fc5ffc17176b5e8bdc82f587b24b2678c6c66101bf7da77af9f7ccdff"
CLI = "e5979f79b765e842a622d98279dbf7c82b0d50d55ec5c96f2eca08134c1ff679"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    args = parser.parse_args()
    prompt = actor.ROOT / "shipment_gemma_prompt.txt"
    grammar = actor.ROOT / "shipment_actor_response.gbnf"
    for path, expected in (
        (args.model, MODEL),
        (args.cli, CLI),
        (grammar, gate.PINS["grammar"]),
        (prompt, gate.PINS["prompt"]),
        (actor.ROOT / "evaluate_shipment_actor.py", gate.PINS["runner"]),
        (actor.ROOT / "shipment_actor_cases.py", gate.PINS["held_out_source"]),
    ):
        with path.open("rb") as source:
            if file_digest(source, "sha256").hexdigest() != expected:
                raise ValueError(f"Pin mismatch for {path.name}")
    content = prompt.read_text(encoding="utf-8").splitlines()[1:-2]
    template = (
        "<|start_header_id|>user<|end_header_id|>\n\n"
        + "\n".join(content)
        + "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
    )

    def infer(rows, rotation, expected):
        return actor.execute(args.model, args.cli, template, grammar, rows, rotation, expected)

    result = gate.run(infer)
    result["pins"] = {
        **gate.PINS,
        "model": MODEL,
        "cli": CLI,
        "source_prompt": gate.PINS["prompt"],
    }
    result["pins"]["prompt"] = sha256(template.encode()).hexdigest()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
