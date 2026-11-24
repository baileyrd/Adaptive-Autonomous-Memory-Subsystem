"""Isolated neural-memory profiling must not affect product behavior."""

import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from scripts.profile_neural_memory import (
    STAGES,
    checked_result,
    execute_stage,
    profile,
    verify_model,
)


class MemoryAttributionTests(unittest.TestCase):
    def test_baseline_runs_in_a_real_isolated_process(self):
        report = profile(["baseline"])
        self.assertTrue(report["pid_isolated"])
        self.assertEqual([row["stage"] for row in report["results"]], ["baseline"])
        self.assertGreater(report["results"][0]["peak_rss_kib"], 0)
        self.assertFalse(report["hashes_verified"])

    def test_stage_order_and_input_rejection(self):
        with self.assertRaises(ValueError):
            profile(["baseline", "baseline"])
        with self.assertRaises(ValueError):
            profile(["unknown"])
        with self.assertRaises(ValueError):
            profile([])
        with self.assertRaises(ValueError):
            profile(["onnx_session"])
        with self.assertRaises(ValueError):
            execute_stage("unknown", None, None)
        self.assertEqual(STAGES[0], "baseline")

    def test_strict_child_payload_checks(self):
        valid = {
            "stage": "baseline",
            "elapsed_ms": 1.0,
            "current_rss_kib": 900,
            "peak_rss_kib": 1000,
        }
        self.assertEqual(checked_result("baseline", valid), valid)
        for changed in (
            {"stage": "onnx_session"},
            {"peak_rss_kib": 0},
            {"current_rss_kib": -1},
            {"unexpected": "sensitive query"},
        ):
            with self.subTest(change=changed), self.assertRaises(ValueError):
                checked_result("baseline", {**valid, **changed})

    def test_model_pins_are_verified_before_optional_imports(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            (directory / "onnx").mkdir()
            (directory / "onnx/model.onnx").write_bytes(b"model")
            (directory / "tokenizer.json").write_bytes(b"tokens")
            pins = {
                name: sha256((directory / name).read_bytes()).hexdigest()
                for name in ("onnx/model.onnx", "tokenizer.json")
            }
            verify_model(directory, pins)
            with self.assertRaises(ValueError):
                verify_model(directory, {**pins, "extra": "x"})
            (directory / "tokenizer.json").write_bytes(b"other")
            with self.assertRaises(ValueError):
                verify_model(directory, pins)
            pins_file = directory / "pins.json"
            pins_file.write_text(json.dumps(pins))
            with self.assertRaises(ValueError):
                profile(["tokenizer_load"], directory, pins_file)


if __name__ == "__main__":
    unittest.main()
