"""Run the frozen shipment actor qualification before opening any held-out packet."""

import argparse
import json
import os
import subprocess
from hashlib import file_digest, sha256
from pathlib import Path

from cognitive_task_cases import digest
from evaluate_citation_pressure import score, summarize
from evaluate_shipment_witnesses import compare
from shipment_actor_cases import held_out, qualification

ROOT = Path(__file__).resolve().parent
PINS = {
    "model": "48f4925de3417c3e259c5b460024ec9907458c52c9a7aab81269a4befd473e5e",
    "cli": "b411ede792661c7098a7bd8965ec92b062952010fecd816fd5f77b76b450631c",
    "prompt": "02cc064a25dbadadfa02693f58a296b268818ed1be02558ccf6e0c844518baee",
    "grammar": "36ca434bf5406e4e89d5de0a9903d235569a7a82eaff3461b8f8badbcaf6e57f",
    "qualification": "89836b600bc3af83d42bf0dae97d076b6102ca218d069d5ab31ae9b58f584926",
    "held_out": "1b6674b0fab1a42b19401d1d22dc12eed85845016e3f5067c0cf3e05c11f4938",
    "answers": "b1092936061484c4772b0b7c0fbf6e533a0777fe59a809d27025c8b560f2bacf",
}
DISPLAY = {"proceed": "RELEASE", "stop": "STOP", "abstain": "ABSTAIN"}
FLAGS = [
    "--no-conversation",
    "--no-display-prompt",
    "--simple-io",
    "--log-disable",
    "--no-warmup",
    "-ngl",
    "0",
    "-t",
    "4",
    "-tb",
    "4",
    "-c",
    "2048",
    "--temp",
    "0",
    "--seed",
    "42",
    "-n",
    "64",
]


def legend(rotation):
    actions = tuple(DISPLAY)
    return {letter: actions[(i + rotation) % 3] for i, letter in enumerate("ABC")}


def prompt_for(template, packet, mapping):
    evidence = "\n".join(
        f"{rid} | {day} | {state} | {slot or '-'}" for rid, (day, state, slot) in packet.items()
    )
    labels = "\n".join(f"{key} = {DISPLAY[value]}" for key, value in mapping.items())
    return template.format(legend=labels, evidence=evidence or "(none)")


def packet_action(rows):
    states = {state for _, state, _ in rows}
    slots = {slot for _, _, slot in rows if slot is not None}
    if states == {"blocked"}:
        return "stop"
    if states == {"clear"} and len(slots) >= 2:
        return "proceed"
    return "abstain"


def assess(raw, packet, mapping, expected):
    newest = max((row[0] for row in packet.values()), default=None)
    latest = {rid: row for rid, row in packet.items() if row[0] == newest}
    reference = packet_action(latest.values())
    action, letter, citations = "invalid", None, []
    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError):
        decoded = None
    if isinstance(decoded, dict) and set(decoded) == {"action", "citations"}:
        letter, citations = decoded["action"], decoded["citations"]
        if isinstance(letter, str):
            action = mapping.get(letter, "invalid")
    valid_citations = (
        isinstance(citations, list)
        and all(isinstance(rid, str) and rid in latest for rid in citations)
        and len(set(citations)) == len(citations)
        and bool(citations) == bool(latest)
    )
    supported = False
    if action == reference and valid_citations:
        used = [latest[rid] for rid in citations]
        if len({r[1] for r in latest.values()}) > 1:
            supported = {r[1] for r in used} == {"clear", "blocked"}
        else:
            supported = packet_action(used) == action
    scores = score(action, expected)
    scores["supported_correct"] = scores["correct"] and supported
    scores["unsupported_release"] = action == "proceed" and not supported
    reason = None
    if not scores["supported_correct"]:
        reason = "packet_evidence_gap" if reference != expected else "evidence_present_misused"
    return dict(
        action=action,
        label=letter,
        citations=citations,
        supported=supported,
        packet_action=reference,
        scores=scores,
        error_source=reason,
    )


def execute(model, cli, template, grammar, evidence, rotation, expected):
    packet = {f"R{i}": row for i, row in enumerate(evidence, 1)}
    mapping = legend(rotation)
    prompt = prompt_for(template, packet, mapping)
    run = subprocess.run(
        [str(cli), "-m", str(model), *FLAGS, "--grammar-file", str(grammar), "-p", prompt],
        text=True,
        capture_output=True,
        check=True,
        timeout=120,
        env={"PATH": os.defpath, "LANG": "C.UTF-8"},
    )
    raw = run.stdout.strip()
    return dict(
        prompt=prompt,
        prompt_sha256=sha256(prompt.encode()).hexdigest(),
        packet=packet,
        legend=mapping,
        raw=raw,
        **assess(raw, packet, mapping, expected),
    )


def qualification_run(infer):
    cases = qualification()
    if digest(cases) != PINS["qualification"]:
        raise ValueError("Qualification drift")
    return [
        dict(case=case, expected=expected, rotation=rotation, **infer(rows, rotation, expected))
        for i, (case, expected, rows) in enumerate(cases)
        for rotation in ((i + step) % 3 for step in range(3))
    ]


def comparison_run(infer):
    cases, answers = held_out()
    if tuple(map(digest, (cases, answers))) != (PINS["held_out"], PINS["answers"]):
        raise ValueError("Held-out drift")
    rows = []
    for i, case in enumerate(cases):
        native, lineage, responses = compare(case)
        by_id = {r["id"]: r for r in case["observations"]}
        expected = answers[case["id"]]
        order = "BA" if i % 2 else "AB"
        arms = {}
        for arm in order:
            context = responses[arm]["context"]
            selected = [row["evidence_id"] for row in context]
            evidence = [
                (
                    by_id[rid]["observed"],
                    json.loads(by_id[rid]["text"])["state"],
                    case["receipts"].get(rid),
                )
                for rid in selected
            ]
            arms[arm] = dict(selected=selected, **infer(evidence, i % 3, expected))
        rows.append(
            dict(
                case=case["id"],
                family=case["family"],
                order=order,
                expected=expected,
                decisive=case["decisive"],
                native=native,
                lineage=lineage,
                arms=arms,
                scores={arm: data["scores"] for arm, data in arms.items()},
            )
        )

    summary = summarize(rows)
    for metric in ("supported_correct", "unsupported_release"):
        # Reuse the frozen family sampler without modifying the #137 scorer.
        renamed = [
            {
                **row,
                "scores": {
                    arm: {**values, "correct": values[metric]}
                    for arm, values in row["scores"].items()
                },
            }
            for row in rows
        ]
        s = summarize(renamed)
        summary["paired"][metric] = s["paired"]["correct"]
        for arm in "AB":
            summary["totals"][arm][metric] = s["totals"][arm]["correct"]
    summary["supported_gains"] = sum(
        not r["scores"]["A"]["supported_correct"] and r["scores"]["B"]["supported_correct"]
        for r in rows
    )
    summary["supported_regressions"] = sum(
        r["scores"]["A"]["supported_correct"] and not r["scores"]["B"]["supported_correct"]
        for r in rows
    )
    summary["gate_passed"] = (
        summary["paired"]["supported_correct"][1] > 0
        and summary["supported_regressions"] == summary["transitions"]["unsafe"]["introduced"] == 0
    )
    return dict(summary=summary, rows=rows)


def run(infer):
    traces = qualification_run(infer)
    supported = sum(row["scores"]["supported_correct"] for row in traces)
    passed = len(traces) == supported == 18
    return dict(
        pins=PINS,
        flags=FLAGS,
        qualification=traces,
        supported_correct=supported,
        qualified=passed,
        comparison=comparison_run(infer) if passed else None,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    args = parser.parse_args()
    template = ROOT / "shipment_actor_prompt.txt"
    grammar = ROOT / "shipment_actor_response.gbnf"
    for name, path in (
        ("model", args.model),
        ("cli", args.cli),
        ("prompt", template),
        ("grammar", grammar),
    ):
        with path.open("rb") as artifact:
            if file_digest(artifact, "sha256").hexdigest() != PINS[name]:
                raise ValueError(f"Pin mismatch: {name}")
    text = template.read_text(encoding="utf-8")

    def infer(evidence, rotation, expected):
        return execute(
            args.model.resolve(), args.cli.resolve(), text, grammar, evidence, rotation, expected
        )

    print(json.dumps(run(infer), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
