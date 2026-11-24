"""Isolated process attribution for optional ONNX retrieval dependencies (research only).

Runs each stage in a fresh Python child. No downloads, data ingestion or product changes.
Peak RSS is cumulative within each child; stage differences are NOT allocator accounting.
"""

import argparse
import json
import os
import resource
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns

STAGES = (
    "baseline",
    "numpy_import",
    "tokenizers_import",
    "tokenizer_load",
    "onnx_import",
    "onnx_session",
)
FILES = ("onnx/model.onnx", "tokenizer.json")


def resident_kib():
    """Current RSS on Linux; unavailable rather than guessed on other platforms."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def file_digest(path):
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_model(directory, pins):
    """Fail closed before opening model or tokenizer; no network access."""
    if not isinstance(pins, dict) or set(pins) != set(FILES):
        raise ValueError("Exactly two model pin entries required")
    for name in FILES:
        expected = pins[name]
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("Invalid sha256 pin")
        if file_digest(directory / name) != expected:
            raise ValueError("Model artifact checksum mismatch")


def execute_stage(stage, directory, pins):
    if stage not in STAGES:
        raise ValueError("Unknown attribution stage")
    if stage in ("tokenizer_load", "onnx_session"):
        if directory is None or pins is None:
            raise ValueError("Model path and pins required")
        verify_model(directory, pins)
    started = perf_counter_ns()
    if stage == "numpy_import":
        import numpy  # noqa: F401
    elif stage == "tokenizers_import":
        import tokenizers  # noqa: F401
    elif stage == "tokenizer_load":
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        if tokenizer is None:
            raise ValueError("Tokenizer failed to initialize")
    elif stage in ("onnx_import", "onnx_session"):
        import onnxruntime

        if stage == "onnx_session":
            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 1
            session = onnxruntime.InferenceSession(
                str(directory / "onnx/model.onnx"),
                options,
                providers=["CPUExecutionProvider"],
            )
            if not session.get_inputs():
                raise ValueError("Model has no inputs")
    return {
        "stage": stage,
        "elapsed_ms": round((perf_counter_ns() - started) / 1e6, 3),
        "current_rss_kib": resident_kib(),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def checked_result(stage, payload):
    """Validate output from a dedicated process, without accepting arbitrary keys."""
    if not isinstance(payload, dict) or payload.get("stage") != stage:
        raise ValueError("Mismatched stage result")
    if set(payload) != {"stage", "elapsed_ms", "current_rss_kib", "peak_rss_kib"}:
        raise ValueError("Unexpected stage output")
    if type(payload["elapsed_ms"]) not in (float, int) or payload["elapsed_ms"] < 0:
        raise ValueError("Invalid elapsed time")
    if type(payload["peak_rss_kib"]) is not int or payload["peak_rss_kib"] <= 0:
        raise ValueError("Invalid peak RSS")
    if payload["current_rss_kib"] is not None and (
        type(payload["current_rss_kib"]) is not int or payload["current_rss_kib"] <= 0
    ):
        raise ValueError("Invalid current RSS")
    return payload


def profile(stages, directory=None, pins_path=None):
    if not stages or len(stages) != len(set(stages)) or any(s not in STAGES for s in stages):
        raise ValueError("Stages must be distinct and recognized")
    pins = None
    if any(s in ("tokenizer_load", "onnx_session") for s in stages):
        if directory is None or pins_path is None:
            raise ValueError("Pinned artifacts required")
        pins = json.loads(pins_path.read_text())
        verify_model(directory, pins)
    results = []
    for stage in stages:
        command = [sys.executable, "-I", str(Path(__file__).resolve()), "--child", stage]
        if stage in ("tokenizer_load", "onnx_session"):
            command += ["--model-dir", str(directory), "--pins", str(pins_path)]
        completed = subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=90
        )
        results.append(checked_result(stage, json.loads(completed.stdout)))
    return {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "pid_isolated": True,
        "hashes_verified": pins is not None,
        "results": results,
        "note": "Process footprints are not additive or a causal allocation breakdown.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", nargs="+", choices=STAGES, default=list(STAGES))
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--pins", type=Path)
    parser.add_argument("--child", choices=STAGES, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        pins = json.loads(args.pins.read_text()) if args.pins is not None else None
        print(json.dumps(execute_stage(args.child, args.model_dir, pins)))
    else:
        print(json.dumps(profile(args.stages, args.model_dir, args.pins), indent=2))


if __name__ == "__main__":
    main()
