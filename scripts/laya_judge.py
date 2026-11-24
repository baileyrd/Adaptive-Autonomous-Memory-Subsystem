"""Eval-only Laya relevance judge client for E1. Standard library only; not product code.

Reads query-passage pairs (JSONL from ``evaluate_laya_rerank.py prepare``), asks a local
Unsloth Decision API one yes/no question per pair, and appends judgments to a JSONL file.
Pairs already judged are skipped, so an interrupted run resumes where it stopped. The pairs
file carries no gold labels, so the judge never sees them.

    python laya_judge.py pairs.jsonl judgments.jsonl

The optional access token is read from the LAYA_API_KEY environment variable, never from
arguments or files.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

URL = "http://127.0.0.1:8888/v1/systemone"
MODEL = "laya-english"
QUESTION = "relevant"
INSTRUCTIONS = (
    "Does the passage answer the query, or contain evidence that directly supports or "
    "refutes the query's claim?"
)
ATTEMPTS = 3

Post = Callable[[dict], dict]


class JudgeError(RuntimeError):
    """The API returned something that cannot be recorded as a judgment."""


@dataclass(frozen=True, slots=True)
class Judgment:
    key: str
    p_yes: float
    model: str
    elapsed_ms: float


def build_request(query: str, passage: str, model: str = MODEL) -> dict:
    """One noul question over a JSON state; the wording is frozen by the prompt hash."""
    return {
        "model": model,
        "state": {"query": query, "passage": passage},
        "questions": {QUESTION: {"type": "noul", "instructions": INSTRUCTIONS}},
    }


def parse_answer(body: dict, expected_model: str) -> tuple[float, str]:
    """Return (probability of yes, served model), refusing anything malformed."""
    model = body.get("model")
    if not isinstance(model, str) or not model.startswith(expected_model):
        raise JudgeError(f"Served model {model!r} is not {expected_model!r}")
    answer = body.get("answers", {}).get(QUESTION, {})
    value = answer.get("noul")
    if answer.get("type") != "noul" or not isinstance(value, int | float):
        raise JudgeError(f"Malformed answer: {answer!r}")
    if not 0.0 <= value <= 1.0:
        raise JudgeError(f"Probability out of range: {value}")
    return float(value), model


def http_post(url: str, token: str | None, timeout: float) -> Post:
    """A JSON POST bound to one endpoint; the token only ever goes in the header."""

    def post(payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())

    return post


def judge(pair: dict, post: Post, model: str, sleep: Callable[[float], None]) -> Judgment:
    """Judge one pair, retrying transport errors with backoff; bad answers fail at once."""
    payload = build_request(pair["query"], pair["passage"], model)
    for attempt in range(1, ATTEMPTS + 1):
        start = time.perf_counter()
        try:
            body = post(payload)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == ATTEMPTS:
                raise JudgeError(f"API unreachable after {ATTEMPTS} attempts: {error}") from error
            sleep(2.0**attempt)
            continue
        elapsed = (time.perf_counter() - start) * 1000
        p_yes, served = parse_answer(body, model)
        return Judgment(pair["key"], p_yes, served, round(elapsed, 1))
    raise AssertionError("unreachable")


def judged_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as lines:
        return {json.loads(line)["key"] for line in lines if line.strip()}


def run(pairs: Path, output: Path, post: Post, model: str, sleep=time.sleep) -> int:
    """Append a judgment per unjudged pair, flushing each line; returns the number added."""
    done = judged_keys(output)
    added = 0
    with pairs.open(encoding="utf-8") as source, output.open("a", encoding="utf-8") as sink:
        for line in source:
            pair = json.loads(line)
            if pair["key"] in done:
                continue
            result = judge(pair, post, model, sleep)
            sink.write(json.dumps(asdict(result)) + "\n")
            sink.flush()
            done.add(pair["key"])
            added += 1
            if added % 100 == 0:
                print(f"{len(done)} judged, last {result.elapsed_ms} ms", file=sys.stderr)
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pairs", type=Path)
    parser.add_argument("judgments", type=Path)
    parser.add_argument("--url", default=URL)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    post = http_post(args.url, os.environ.get("LAYA_API_KEY"), args.timeout)
    try:
        added = run(args.pairs, args.judgments, post, args.model)
    except JudgeError as error:
        sys.exit(f"Stopped: {error}. Rerun the same command to resume.")
    print(f"Added {added} judgments to {args.judgments}")


if __name__ == "__main__":
    main()
