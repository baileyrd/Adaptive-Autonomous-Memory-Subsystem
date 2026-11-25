"""Run exactly one forced-choice decision in a new interpreter; no retrieval or labels."""

import json
import os
import resource
import sys
from time import process_time_ns


def main() -> None:
    """Read one fully rendered prompt on stdin and return the raw completion and cost."""
    start = process_time_ns()
    from llama_cpp import Llama, LlamaGrammar

    prompt = sys.stdin.read()
    model = Llama(
        model_path=sys.argv[1],
        n_ctx=2048,
        n_threads=1,
        n_threads_batch=1,
        seed=123,
        n_gpu_layers=0,
        verbose=False,
    )
    tokens = model.tokenize(prompt.encode(), special=True)
    if len(tokens) + 1 > 2048:
        raise ValueError("Prompt exceeds context")
    completion = model(
        tokens,
        max_tokens=1,
        temperature=0,
        seed=123,
        grammar=LlamaGrammar.from_string("root ::= [ABCDE]", verbose=False),
    )
    if completion["choices"][0]["text"] not in tuple("ABCDE"):
        raise ValueError(f"Invalid completion: {completion!r}")
    print(
        json.dumps(
            dict(
                raw=completion,
                pid=os.getpid(),
                rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                cpu_ns=process_time_ns() - start,
            )
        )
    )


if __name__ == "__main__":
    main()
