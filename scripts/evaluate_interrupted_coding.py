"""One paired model-backed coding resume on isolated disposable checkouts."""

import argparse
import ast
import json
import os
import subprocess
import tempfile
from hashlib import file_digest
from pathlib import Path

from aams.learning import LearningCandidate
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.storage import AccessContext, SQLiteMemoryStore
from evaluate_learning import TIME, review, seed
from evaluate_shipment_actor import response_text

ROOT = Path(__file__).resolve().parent
BASE = "9dc755258116af9cfccc55a805d505054d9f5b15"
PINS = {
    "model": "48f4925de3417c3e259c5b460024ec9907458c52c9a7aab81269a4befd473e5e",
    "cli": "b411ede792661c7098a7bd8965ec92b062952010fecd816fd5f77b76b450631c",
    "prompt": "040de7be274becfa7215dda305cd3746566e11b40dd7a4df63a3693636e566a1",
    "grammar": "f201c18e5769b23d078ca3d1fe738496d79097a73bdf296e3bd5c52ec1401e05",
}
FLAGS = [
    "--no-conversation",
    "--no-display-prompt",
    "--simple-io",
    "--no-warmup",
    "-ngl",
    "0",
    "-t",
    "4",
    "-tb",
    "4",
    "-c",
    "4096",
    "--temp",
    "0",
    "--seed",
    "42",
    "-n",
    "160",
]
TARGET = Path("resume_fixture/labels.py")
INITIAL = (
    '"""Display-label formatting."""\n\n\ndef display_label(value: str) -> str:\n    return value\n'
)
SCOPE = "offline-labels"
LESSON = "Use explicit ASCII horizontal padding characters in strip; default strip removed NBSP."
PROBES = {
    "padding": (" \tOak\t ", "Oak"),
    "mistake": ("\u00a0Oak\u00a0", "\u00a0Oak\u00a0"),
    "unresolved": ("\nOak\r", "\nOak\r"),
    "interior": ("a\t b", "a\t b"),
}


def prepare_memory(path, prior_trial):
    store = SQLiteMemoryStore(path)
    example = prior_trial["input"]
    observed = prior_trial["observed"]
    want = prior_trial["required"]
    rows = [
        (
            "decision-ascii",
            "maintainer",
            "design-log",
            "labelresume: Prior decision: trim only ASCII space and tab at the two ends of display labels. Do not change stored values.",
        ),
        (
            "trial-strip",
            "qa-runner",
            "failed-probe",
            "labelresume: Concrete failed edit was return value.strip(). Input "
            f"{ascii(example)}, observed {ascii(observed)}, required {ascii(want)}. The edit was reverted.",
        ),
        (
            "display-contract",
            "fixture-verifier",
            "display-requirements",
            "labelresume: NBSP at the ends of display labels is significant and must survive normalization.",
        ),
        (
            "open-linebreak",
            "maintainer",
            "open-question",
            "labelresume: Whether to trim carriage returns and linefeeds is unresolved. Leave both intact for now.",
        ),
    ]
    seed(
        store,
        {
            "evidence": [
                (key, SCOPE, actor, actor, locator, payload)
                for key, actor, locator, payload in rows
            ]
        },
    )
    author = AccessContext("lesson-author", SCOPE, True)
    reviewer = AccessContext("fixture-reviewer", SCOPE, True, True)
    lesson = LearningCandidate(
        "lesson-strip",
        SCOPE,
        author.principal,
        LESSON,
        TIME,
        ("trial-strip", "display-contract"),
    )
    store.create_candidate(author, "candidate", lesson)
    if not review(store, lesson, reviewer):
        raise ValueError("Fixture lesson did not reach approved state")


def recall(path):
    store = SQLiteMemoryStore(path)
    access = AccessContext("resume-reader", SCOPE)
    reply = CognitiveMemory(store).recall(
        access, CognitiveNeed(query="labelresume", max_items=8, max_bytes=8192)
    )
    if reply["truncated"]:
        raise ValueError("Recall packet exceeded its bound")
    rows = {}
    for item in reply["items"]:
        for row in item["citations"]:
            canonical = store.get_evidence(access, row["evidence_id"])
            if canonical is None or row["digest"] != canonical.digest or row["preview_truncated"]:
                raise ValueError("Source verification failed")
            rows[row["evidence_id"]] = dict(
                id=row["evidence_id"], digest=row["digest"], text=row["preview"]
            )
    record = store.get_candidate(access, "lesson-strip")
    if (
        record.state.value != "approved"
        or not set(record.proposal.support_ids) <= rows.keys()
        or store.validate_candidate(access, "lesson-strip").independent_support
        != record.proposal.support_ids
    ):
        raise ValueError("Lesson review or recall lineage not verified")
    result = dict(
        items=list(rows.values()),
        reviewed_lesson=dict(
            id=record.proposal.candidate_id,
            text=record.proposal.claim,
            sources=record.proposal.support_ids,
            review=[
                dict(version=d.version, reviewer=d.request.actor, state=d.request.to_state.value)
                for d in record.history
            ],
        ),
    )
    if len(json.dumps(result).encode()) > 8192:
        raise ValueError("Combined memory packet exceeded its bound")
    return result


def git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args],
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "GIT_AUTHOR_DATE": TIME, "GIT_COMMITTER_DATE": TIME},
    ).stdout


def checkouts(root):
    original = root / "interrupted"
    git(root, "clone", "--quiet", "--shared", "--no-checkout", str(ROOT.parent), str(original))
    git(original, "checkout", "--quiet", "--detach", BASE)
    (original / TARGET).parent.mkdir()
    file = original / TARGET
    attempted = INITIAL.replace("return value", "return value.strip()")
    file.write_text(attempted, encoding="utf-8")
    example, want = PROBES["mistake"]
    observed = evaluate_expression(isolate_expression(file.read_text(encoding="utf-8")), example)
    if observed == want:
        raise ValueError("Expected concrete failed probe")
    file.write_text(INITIAL, encoding="utf-8")
    prior_trial = dict(input=example, observed=observed, required=want, reverted=True)
    git(original, "add", "--", str(TARGET))
    git(
        original,
        "-c",
        "user.name=Pilot",
        "-c",
        "user.email=pilot@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "Identical interrupted fixture",
    )
    copies = {}
    for arm in "AB":
        path = root / arm
        git(root, "clone", "--quiet", "--shared", str(original), str(path))
        if (path / TARGET).read_bytes() != INITIAL.encode() or git(path, "status", "--porcelain"):
            raise ValueError("Interrupted workspace mismatch")
        copies[arm] = path
    return copies, git(original, "rev-parse", "HEAD^{tree}").strip(), prior_trial


def session(path, memory_path, infer, instruction):
    history = ""
    events, seen = [], {}
    edited = False
    for _ in range(4):
        prompt = (
            f"<|im_start|>system\n{instruction}<|im_end|>\n"
            "<|im_start|>user\nResume the pending edit.<|im_end|>\n"
            f"{history}<|im_start|>assistant\n"
        )
        stdout = infer(prompt)
        raw = response_text(stdout)
        event = dict(prompt=prompt, stdout=stdout, raw=raw)
        events.append(event)
        try:
            call = json.loads(raw)
        except ValueError:
            event["error"] = "invalid tool call"
            break
        tool = call["tool"]
        event["call"] = call
        if tool == "stop":
            break
        if tool == "read":
            result = {"path": str(TARGET), "text": (path / TARGET).read_text(encoding="utf-8")}
        elif tool == "recall":
            result = recall(memory_path) if memory_path is not None else {"items": []}
            seen.update({row["id"]: row for row in result["items"]})
            if "reviewed_lesson" in result:
                lesson = result["reviewed_lesson"]
                seen[lesson["id"]] = lesson
        else:
            replacement = call["replacement"]
            if (
                "\n" in replacement
                or "\r" in replacement
                or not replacement.startswith("    return ")
            ):
                event["error"] = "edit must be one indented return line"
            else:
                original = (path / TARGET).read_text(encoding="utf-8")
                (path / TARGET).write_text(
                    original.replace("    return value", replacement, 1), encoding="utf-8"
                )
                edited = True
                event["result"] = {"applied": True}
            break
        event["result"] = result
        reply = json.dumps(result, ensure_ascii=True, separators=(",", ":"))
        history += f"<|im_start|>assistant\n{raw}<|im_end|>\n"
        history += f"<|im_start|>user\nTool result: {reply}<|im_end|>\n"
    return dict(
        events=events,
        available=seen,
        edited=edited,
        diff=git(path, "diff", "--no-ext-diff", "--", str(TARGET)),
        changed_files=git(path, "status", "--porcelain").splitlines(),
        result_file=(path / TARGET).read_text(encoding="utf-8"),
    )


def evaluate_expression(expression, value):
    # Interpret only the fixture's intended string operations; never execute generated code.
    if isinstance(expression, ast.Name) and expression.id == "value":
        return value
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Attribute)
        and expression.func.attr in {"strip", "lstrip", "rstrip"}
        and not expression.keywords
        and len(expression.args) <= 1
        and all(isinstance(arg, ast.Constant) and type(arg.value) is str for arg in expression.args)
    ):
        operand = evaluate_expression(expression.func.value, value)
        return getattr(operand, expression.func.attr)(*(arg.value for arg in expression.args))
    raise ValueError("Unsupported fixture expression")


def isolate_expression(text):
    parsed = ast.parse(text)
    try:
        statement = parsed.body[1].body[0]
    except (IndexError, AttributeError) as exc:
        raise ValueError("Missing fixture return statement") from exc
    if not isinstance(statement, ast.Return) or statement.value is None:
        raise ValueError("Missing fixture return expression")
    expression = statement.value
    statement.value = ast.Name(id="value", ctx=ast.Load())
    if ast.dump(parsed) != ast.dump(ast.parse(INITIAL)):
        raise ValueError("Edit changed more than the return expression")
    return expression


def score(run):
    checks = {}
    if run["edited"] and run["diff"]:
        try:
            expression = isolate_expression(run["result_file"])
            checks = {
                name: evaluate_expression(expression, value) == expected
                for name, (value, expected) in PROBES.items()
            }
        except (ValueError, SyntaxError, AttributeError, IndexError):
            pass
    correct = run["changed_files"] == [" M " + str(TARGET)] and all(
        checks.get(name, False) for name in ("padding", "unresolved", "interior")
    )
    avoided = checks.get("mistake")
    call = run["events"][-1].get("call", {})
    cited = call.get("citations", []) if call.get("tool") == "edit" else []
    known = set(run["available"])
    enough = {"decision-ascii", "open-linebreak"} <= set(cited) and (
        "trial-strip" in cited or "lesson-strip" in cited
    )
    return dict(
        correct_step=correct,
        mistake_avoided=avoided,
        citations=cited,
        checks=checks,
        evidence_support=bool(correct and avoided and enough and set(cited) <= known),
    )


def run(infer, instruction):
    with tempfile.TemporaryDirectory(prefix="aams-interrupted-") as directory:
        root = Path(directory)
        memory_path = root / "memory.sqlite"
        copies, tree, prior_trial = checkouts(root)
        prepare_memory(memory_path, prior_trial)
        arms = {
            arm: session(copies[arm], memory_path if arm == "B" else None, infer, instruction)
            for arm in "AB"
        }
        return dict(
            base=BASE,
            fixture_tree=tree,
            pins=PINS,
            flags=FLAGS,
            prior_trial=prior_trial,
            order=["A", "B"],
            arms=arms,
            scores={arm: score(result) for arm, result in arms.items()},
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    args = parser.parse_args()
    grammar = ROOT / "interrupted_coding.gbnf"
    prompt = ROOT / "interrupted_coding_prompt.txt"
    for kind, path in (
        ("model", args.model),
        ("cli", args.cli),
        ("prompt", prompt),
        ("grammar", grammar),
    ):
        with path.open("rb") as artifact:
            if file_digest(artifact, "sha256").hexdigest() != PINS[kind]:
                raise ValueError(f"Pin mismatch: {kind}")

    def infer(text):
        return subprocess.run(
            [
                str(args.cli.resolve()),
                "-m",
                str(args.model.resolve()),
                *FLAGS,
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
            env={"PATH": os.defpath, "LANG": "C.UTF-8"},
        ).stdout

    print(json.dumps(run(infer, prompt.read_text(encoding="utf-8")), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
