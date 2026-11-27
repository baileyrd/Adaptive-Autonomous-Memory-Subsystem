"""One frozen #150 follow-up with host-delivered memory at startup."""

import argparse
import json
import os
import re
import subprocess
import tempfile
from hashlib import file_digest, sha256
from pathlib import Path

import evaluate_interrupted_coding as prior
from aams.storage import AccessContext, SQLiteMemoryStore
from evaluate_cognitive_tasks import database_digest

ROOT = Path(__file__).resolve().parent
TRACE = ROOT.parent / "docs/audit/interrupted-coding-pilot-traces.json"
RUNNER_PIN = "35552d82c06001cf248e72251683e221163ba69ed1c0833da5cae825c1fb42bf"
TRACE_PIN = "f792470ce7aad731efbac88bd9dea6047e2105d8c1ad58bef3a8695a39550c53"
TOKENIZER_PIN = "b250c7af88c58c2f8b225139d5661dbdc431dd0ffd7f427e755e8bdc0b60aeca"
ANCHOR = "Resume the pending edit.<|im_end|>\n"
PACKET_LABEL = "\nStartup memory packet: "
SOURCE_IDS = {"decision-ascii", "display-contract", "open-linebreak", "trial-strip"}
ENV = {"PATH": os.defpath, "LANG": "C.UTF-8"}


def sha(text):
    return sha256(text.encode()).hexdigest()


def packet_text(packet):
    return json.dumps(packet, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def insert_packet(prompt, wire):
    if prompt.count(ANCHOR) != 1:
        raise ValueError("Missing or ambiguous first-user-turn anchor")
    return prompt.replace(
        ANCHOR, "Resume the pending edit." + PACKET_LABEL + wire + "<|im_end|>\n", 1
    )


def verify_packet(path, packet):
    store = SQLiteMemoryStore(path)
    store.verify_integrity()
    authorized = AccessContext("resume-reader", prior.SCOPE)
    foreign = AccessContext("resume-reader", "unrelated-scope")
    if {row["id"] for row in packet["items"]} != SOURCE_IDS:
        raise ValueError("Unexpected startup sources")
    for row in packet["items"]:
        record = store.get_evidence(authorized, row["id"])
        if (
            record is None
            or record.scope != prior.SCOPE
            or record.digest != row["digest"]
            or record.payload != row["text"].encode()
            or store.get_evidence(foreign, row["id"]) is not None
        ):
            raise ValueError("Invalid startup source or scope")
    lesson = packet["reviewed_lesson"]
    if (
        lesson["id"] != "lesson-strip"
        or not set(lesson["sources"]) <= SOURCE_IDS
        or lesson["review"][-1]["state"] != "approved"
        or store.get_candidate(foreign, lesson["id"]) is not None
    ):
        raise ValueError("Invalid startup lesson or scope")


def analyze_delivery(original, packet, tokenize):
    wire = packet_text(packet)
    intended = insert_packet(original, wire)
    # The unchanged llama.cpp CLI interprets backslash escapes in argv prompts.
    # Escape once for transport and verify the complete model-facing token sequence.
    argument = insert_packet(original, wire.replace("\\", "\\\\"))
    actual_ids = tokenize(argument, escape=True)
    if actual_ids != tokenize(intended, escape=False):
        raise ValueError("Startup packet tokenization did not preserve the intended input")
    if len(actual_ids) + 160 > 4096:
        raise ValueError("Startup input exceeds the frozen context budget")
    return dict(
        packet=packet,
        packet_sha256=sha(wire),
        evidence_ids=[row["id"] for row in packet["items"]],
        lesson_id=packet.get("reviewed_lesson", {}).get("id"),
        first_input=intended,
        first_input_sha256=sha(intended),
        first_argv_prompt=argument,
        first_tokens=len(actual_ids),
        token_ids_sha256=sha(json.dumps(actual_ids)),
    )


def run(infer, tokenize, instruction, delivery_path):
    old = json.loads(TRACE.read_text(encoding="utf-8"))
    first = old["arms"]["A"]["events"][0]["prompt"]
    if first != old["arms"]["B"]["events"][0]["prompt"]:
        raise ValueError("Original initial prompts differed")
    with tempfile.TemporaryDirectory(prefix="aams-startup-") as directory:
        root = Path(directory)
        copies, tree, prior_trial = prior.checkouts(root)
        if (
            tree != old["fixture_tree"]
            or prior_trial != old["prior_trial"]
            or any(
                prior.git(p, "rev-parse", "HEAD^{tree}").strip() != tree for p in copies.values()
            )
        ):
            raise ValueError("Interrupted tree or prior probe changed")
        ledger = root / "memory.sqlite"
        prior.prepare_memory(ledger, prior_trial)
        packet = prior.recall(ledger)
        verify_packet(ledger, packet)
        before = database_digest(ledger)

        delivery = {
            arm: analyze_delivery(first, contents, tokenize)
            for arm, contents in (("A", {"items": []}), ("B", packet))
        }
        delivery_path.write_text(
            json.dumps(delivery, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        arms = {}
        for arm in "AB":
            proof = delivery[arm]
            contents = proof["packet"]
            wire = packet_text(contents)
            sent = []

            def send(base_prompt):
                argument = insert_packet(base_prompt, wire.replace("\\", "\\\\"))
                if not sent and argument != proof["first_argv_prompt"]:
                    raise ValueError("Actual first input differs from verified input")
                tokens = len(tokenize(argument, escape=True))
                if tokens + 160 > 4096:
                    raise ValueError("Input exceeds the frozen context budget")
                stdout, evaluated = infer(argument)
                if evaluated != tokens:
                    raise ValueError("Runtime evaluated a different prompt length")
                sent.append(dict(argv_prompt=argument, tokens=tokens, evaluated=evaluated))
                return stdout

            result = prior.session(copies[arm], ledger if arm == "B" else None, send, instruction)
            for event, transport in zip(result["events"], sent, strict=True):
                event["argv_prompt"] = transport["argv_prompt"]
                event["input_tokens"] = transport["tokens"]
                event["evaluated_tokens"] = transport["evaluated"]
            received = {entry["id"]: entry for entry in contents["items"]}
            if "reviewed_lesson" in contents:
                lesson = contents["reviewed_lesson"]
                received[lesson["id"]] = lesson
            result["available"].update(received)
            arms[arm] = result

        if before != database_digest(ledger) or arms["A"]["available"]:
            raise ValueError("Memory mutation or control isolation failure")
        return dict(
            fixture_tree=tree,
            prior_trial=prior_trial,
            pins=prior.PINS,
            flags=prior.FLAGS,
            original_trace_sha256=TRACE_PIN,
            runner_sha256=RUNNER_PIN,
            tokenizer_sha256=TOKENIZER_PIN,
            order=["A", "B"],
            delivery=delivery,
            arms=arms,
            scores={arm: prior.score(result) for arm, result in arms.items()},
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--delivery-out", type=Path, required=True)
    args = parser.parse_args()
    grammar = ROOT / "interrupted_coding.gbnf"
    prompt = ROOT / "interrupted_coding_prompt.txt"
    pins = {
        args.model: prior.PINS["model"],
        args.cli: prior.PINS["cli"],
        args.tokenizer: TOKENIZER_PIN,
        grammar: prior.PINS["grammar"],
        prompt: prior.PINS["prompt"],
        Path(prior.__file__): RUNNER_PIN,
        TRACE: TRACE_PIN,
    }
    for path, pin in pins.items():
        with path.open("rb") as artifact:
            if file_digest(artifact, "sha256").hexdigest() != pin:
                raise ValueError(f"Pin mismatch: {path}")

    def tokenize(text, *, escape):
        flags = [] if escape else ["--no-escape"]
        result = subprocess.run(
            [
                str(args.tokenizer.resolve()),
                "-m",
                str(args.model.resolve()),
                "--ids",
                "--log-disable",
                *flags,
                "-p",
                text,
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=30,
            check=True,
            env=ENV,
        )
        return json.loads(result.stdout)

    def infer(text):
        result = subprocess.run(
            [
                str(args.cli.resolve()),
                "-m",
                str(args.model.resolve()),
                *prior.FLAGS,
                "--grammar-file",
                str(grammar),
                "-p",
                text,
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=120,
            check=True,
            env=ENV,
        )
        count = re.search(r"prompt eval time\s*=.*?/\s*(\d+) tokens", result.stderr)
        if count is None:
            raise ValueError("Runtime did not report prompt evaluation length")
        return result.stdout, int(count[1])

    result = run(infer, tokenize, prompt.read_text(encoding="utf-8"), args.delivery_out)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
