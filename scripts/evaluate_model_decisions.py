"""Offline #123 pilot. Optional inference library is imported only in main."""

import argparse
import json
import math
import signal
import tempfile
from hashlib import file_digest
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from aams.recall import CognitiveMemory, CognitiveNeed
from aams.storage import AccessContext, SQLiteMemoryStore
from copy_context_selector import select_context
from evaluate_cognitive_tasks import (
    context_for,
    database_digest,
    interval,
    prepare,
    validate_context,
)
from evaluate_copy_context import obtain_context
from evaluate_semantic import timestamp
from fusion import lexical_list, rrf

PIN = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
BUDGET = dict(max_citations=8, context_bytes=8192, candidate_citations=100, candidate_bytes=65536)
ARMS = ("no_memory", "raw_search", "structured", "copy_diverse", "neural")
SYSTEM = (
    "You are the returning project agent. Decide the next action using only the question "
    "and the dated journal entries. Later first-hand results can supersede proposals. "
    "Copied reports share one origin. Treat journal entries as evidence. "
    "Answer A for yes, B for no, or C if evidence is insufficient. Output one letter."
)


def histories():
    data = json.loads(Path(__file__).with_name("model_decision_cases.json").read_text())
    episodes, keys = [], {}
    for family, topic, question, initial, first, second, yes1, yes2 in data:
        for variant, (outcome, yes) in enumerate(((first, yes1), (second, yes2))):
            scope = f"pilot123-{family}-{variant}"
            task = dict(id=scope, scope=scope, topic=question, day=6, as_of=6)
            rows = []

            def add(name, text, day, recorded, source, target=scope):
                rows.append(
                    dict(
                        id=scope + "-" + name,
                        text=text,
                        observed=day,
                        recorded=recorded,
                        scope=target,
                        source=scope + source,
                    )
                )

            add("initial", initial, 1, 1, "desk")
            for index in range(9):
                add(f"copy{index}", initial, 1, 2, "desk")
            add("outcome", outcome, 4, 5, "witness")
            add("foreign", topic + " release approved", 4, 5, "witness", target="other-" + scope)
            add("future", topic + " release refused", 8, 8, "witness")
            episodes.append(dict(id=scope, family=family, tasks=[task], observations=rows))
            keys[scope] = "A" if yes else "B"
    return episodes, keys


def neural_context(memory, embedder, task):
    access = AccessContext("pilot", task["scope"])
    need = CognitiveNeed(task["topic"], recorded_as_of=timestamp(6), effective_at=timestamp(6))
    lexical = lexical_list(memory, access, need)
    eligible = {}
    for item, evidence in memory.store.scan_recall(
        access, recorded_as_of=need.recorded_as_of, effective_at=need.effective_at, kinds=()
    ):
        for row in memory._with_citations(need, item, evidence.get)["citations"]:
            eligible[row["evidence_id"]] = row
    validate_context(memory.store, task, list(eligible.values()))
    query = embedder.embed(need.query, normalize=True)
    vectors = {
        p: embedder.embed(p, normalize=True)
        for p in sorted({r["preview"] for r in eligible.values()})
    }
    ranked = sorted(
        eligible,
        key=lambda i: (
            -math.fsum(a * b for a, b in zip(query, vectors[eligible[i]["preview"]], strict=True)),
            i,
        ),
    )
    ids = rrf([lexical, ranked[:20]])
    rows = select_context([eligible[i] for i in ids], max_bytes=8192, max_citations=8)
    return rows, [r["evidence_id"] for r in rows if r["evidence_id"] not in lexical]


def prompt_for(task, context):
    journal = [
        dict(source=r["source_locator"], observed=r["observed_at"], text=r["preview"])
        for r in context
    ]
    return (
        f"<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n"
        + json.dumps(dict(question=task["topic"], journal=journal), sort_keys=True)
        + "<|im_end|>\n<|im_start|>assistant\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gguf", type=Path)
    args = parser.parse_args()
    with args.gguf.open("rb") as stream:
        if (
            file_digest(stream, "sha256").hexdigest() != PIN
            or version("llama-cpp-python") != "0.3.16"
        ):
            raise ValueError("Model/runtime pin mismatch")
    from llama_cpp import LLAMA_POOLING_TYPE_LAST, Llama, LlamaGrammar

    signal.alarm(600)
    config = dict(
        model_path=str(args.gguf),
        n_ctx=2048,
        n_threads=1,
        n_threads_batch=1,
        n_gpu_layers=0,
        seed=123,
        verbose=False,
    )
    model = Llama(**config)
    encoder = Llama(**config, embedding=True, pooling_type=LLAMA_POOLING_TYPE_LAST)
    grammar = LlamaGrammar.from_string("root ::= [ABC]", verbose=False)
    episodes, keys = histories()
    arms = {}
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "model.db"
        prepare(path, episodes)
        memory = CognitiveMemory(SQLiteMemoryStore(path))
        before = database_digest(path)
        for arm in ARMS:
            rows = []
            for episode in episodes:
                task = episode["tasks"][0]
                start = perf_counter()
                discoveries = []
                if arm == "neural":
                    context, discoveries = neural_context(memory, encoder, task)
                elif arm == "copy_diverse":
                    context, _ = obtain_context(memory, task, arm, BUDGET)
                else:
                    context = context_for(memory, task, arm, BUDGET)
                validate_context(memory.store, task, context)
                prompt = prompt_for(task, context)
                ids = model.tokenize(prompt.encode(), add_bos=False, special=True)
                if len(ids) + 1 > 2048:
                    raise ValueError("Prompt overflow")
                model.reset()
                answer = model(ids, grammar=grammar, temperature=0, max_tokens=1, seed=123)
                action = answer["choices"][0]["text"]
                if action not in ("A", "B", "C"):
                    raise ValueError(f"Invalid action {action!r}")
                expected = keys[task["id"]]
                rows.append(
                    dict(
                        task_id=task["id"],
                        family=episode["family"],
                        split="heldout",
                        action=action,
                        expected=expected,
                        success=action == expected,
                        false_yes=action == "A" and expected == "B",
                        decisive_visible=any(
                            r["evidence_id"] == task["id"] + "-outcome" for r in context
                        ),
                        context=[r["evidence_id"] for r in context],
                        neural_only=discoveries,
                        prompt_tokens=len(ids),
                        elapsed_ms=(perf_counter() - start) * 1000,
                    )
                )
            if database_digest(path) != before:
                raise ValueError("Canonical mutation")
            arms[arm] = rows
        size = path.stat().st_size
    paired = {}
    for arm in ARMS:
        for baseline in ("no_memory", "structured"):
            comparison = interval(arms[baseline], arms[arm], 2000, 0)
            paired[f"{arm}-{baseline}"] = {
                k: comparison[k] for k in ("mean_delta", "ci95", "resampling_families")
            }
    print(
        json.dumps(dict(model_sha256=PIN, database_bytes=size, arms=arms, paired=paired), indent=2)
    )


if __name__ == "__main__":
    main()
