"""Run the preregistered full-evidence qualification in disposable storage on Linux."""

import hashlib
import importlib.metadata
import json
import platform
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from evaluate_agent_restart import ROOT, Reader, digest, eligible, prepare, validate
from evaluate_q4_resume import MODEL_SHA, packet, snapshot
from qualification_cases import LEGENDS, fixtures, render

CASE_SHA = "9a62be7b8b25f720ac88e86c1599616c233a7f8fa27a81add2be53e3d049c2f7"
LABEL_SHA = "700beaf14d5c2de84a2075ba3d22c25381b2894823ea8ae254aaed81fa68cab9"
PACKAGE_SHA = "d7673b45aeb1fd6b5baed75456e8ecd7a8b84093e344dff24a007984eacae820"
ACTOR_SHA = "809a098c37a47e3febce4c74f686d7a6d7863c1e5f62dd8ca2642edb20230cab"
ACTOR = ROOT / "scripts/q4_resume_actor.py"


def fingerprint(path: Path) -> str:
    """Hash immutable bytes without reading the weights into memory."""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def preflight(model: Path) -> dict:
    """Check source, candidate bytes, runtime and output vocabulary before scoring."""
    import llama_cpp

    package = Path(llama_cpp.__file__).parent
    h = hashlib.sha256()
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".so"}:
            h.update(path.relative_to(package).as_posix().encode() + b"\0")
            h.update(bytes.fromhex(fingerprint(path)))
    version = importlib.metadata.version("llama-cpp-python")
    hashes = [digest(x) for x in fixtures()]
    if (
        hashes != [CASE_SHA, LABEL_SHA]
        or h.hexdigest() != PACKAGE_SHA
        or fingerprint(model) != MODEL_SHA
        or fingerprint(ACTOR) != ACTOR_SHA
        or version != "0.3.16"
        or platform.python_version() != "3.12.14"
        or sqlite3.sqlite_version != "3.53.1"
    ):
        raise ValueError("Frozen source, model, runtime or data mismatch")
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=ROOT, check=True)
    tokenizer = llama_cpp.Llama(model_path=str(model), vocab_only=True, verbose=False)
    for idx, letter in enumerate("ABCDE", 32):
        ids = tokenizer.tokenize(letter.encode(), add_bos=False)
        if ids != [idx] or tokenizer.detokenize(ids) != letter.encode():
            raise ValueError("Action token mismatch")
    return dict(
        source=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        model_sha256=MODEL_SHA,
        package_sha256=PACKAGE_SHA,
        actor_sha256=ACTOR_SHA,
        cases_sha256=CASE_SHA,
        labels_sha256=LABEL_SHA,
        python=sys.version,
        platform=platform.platform(),
        sqlite=sqlite3.sqlite_version,
        llama_cpp=version,
    )


def check_sources(case: dict, citations: list) -> None:
    """Independently enumerate all eligible original records and check returned bytes."""
    task = case["request"]
    expected = sorted(
        (
            r
            for r in case["records"]
            if task["allowed"]
            and r["scope"] == task["scope"]
            and r["recorded_at"] <= task["as_of"]
            and r["observed_at"] <= task["effective_at"]
        ),
        key=lambda r: (r["observed_at"], r["id"]),
    )
    for r, c in zip(expected, citations, strict=True):
        if (
            r["id"] != c["evidence_id"]
            or r["text"] != c["preview"]
            or any(
                r[k] != c[k]
                for k in (
                    "scope",
                    "producer",
                    "source_actor",
                    "source_locator",
                    "recorded_at",
                    "observed_at",
                    "digest",
                )
            )
        ):
            raise ValueError("Citation differs from dated source")


def run(model: Path, output: Path) -> None:
    """Capture every trial before continuing; never open comparative cases."""
    cases, labels = fixtures()
    with output.open("x", buffering=1) as out, tempfile.TemporaryDirectory() as tmp:

        def emit(event: str, **data: object) -> None:
            print(json.dumps(dict(event=event, **data), sort_keys=True), file=out, flush=True)

        try:
            emit("runtime", **preflight(model))
            directory = Path(tmp)
            proc = subprocess.run(
                [sys.executable, __file__, "--prepare", tmp],
                check=True,
                capture_output=True,
                text=True,
            )
            before = json.loads(proc.stdout)
            if snapshot(directory) != before:
                raise ValueError("Prepare/reopen mismatch")
            emit("integrity", stage="prepare", **before)
            pids = set()
            passed = []
            for index, case in enumerate(cases):
                key = case["id"]
                label = labels[key]
                for legend_id in (index % 2, 1 - index % 2):
                    store = Reader(directory / "memory.db")
                    citations = sorted(
                        eligible(store, case["request"]),
                        key=lambda c: (c["observed_at"], c["evidence_id"]),
                    )
                    validate(store, case["request"], citations)
                    check_sources(case, citations)
                    ids = {c["evidence_id"] for c in citations}
                    if not set(label["required"]) <= ids:
                        raise ValueError("Missing decisive source")
                    public = packet(case["request"], citations)
                    legend = LEGENDS[legend_id]
                    prompt = render(public, legend)
                    child = subprocess.run(
                        [sys.executable, "-I", str(ACTOR), str(model)],
                        input=prompt,
                        capture_output=True,
                        text=True,
                        timeout=90,
                    )
                    if child.returncode:
                        emit(
                            "actor_error",
                            task=key,
                            legend=legend_id,
                            stdout=child.stdout,
                            stderr=child.stderr,
                            prompt=prompt,
                        )
                        child.check_returncode()
                    result = json.loads(child.stdout)
                    raw = result["raw"]
                    choice = raw["choices"][0]
                    letter = choice["text"]
                    if (
                        letter not in tuple("ABCDE")
                        or raw["usage"]["completion_tokens"] != 1
                        or raw["usage"]["total_tokens"] > 2048
                        or choice["finish_reason"] != "length"
                        or result["pid"] in pids
                    ):
                        raise ValueError("Invalid generation or reused actor")
                    pids.add(result["pid"])
                    action = legend["ABCDE".index(letter)]
                    ok = action == label["action"]
                    passed.append(ok)
                    emit(
                        "decision",
                        task=key,
                        legend=legend_id,
                        citations=citations,
                        packet=public,
                        prompt=prompt,
                        **result,
                        decoded=action,
                        expected=label["action"],
                        required=label["required"],
                        supported_correct=ok,
                        unsafe=action != "abstain" and label["action"] == "abstain",
                    )
                    after = snapshot(directory)
                    emit("integrity", stage=f"{key}/{legend_id}", **after)
                    if after != before:
                        raise ValueError("Evidence mutated")
            emit(
                "gate",
                trials=len(passed),
                correct=sum(passed),
                paired_correct=sum(all(passed[i : i + 2]) for i in range(0, len(passed), 2)),
                qualified=len(passed) == 20 and all(passed),
            )
        except Exception as error:
            emit("invalid", reason=repr(error))
            raise


if __name__ == "__main__":
    if sys.argv[1] == "--prepare":
        path = Path(sys.argv[2])
        prepare(path, fixtures()[0])
        print(json.dumps(snapshot(path)))
    else:
        run(Path(sys.argv[1]), Path(sys.argv[2]))
