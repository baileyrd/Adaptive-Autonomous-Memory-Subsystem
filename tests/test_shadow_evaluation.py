import json
import subprocess
import sys
import unittest
from pathlib import Path


class ShadowReplayTest(unittest.TestCase):
    def test_synthetic_replay_preserves_serving_and_refuses_improvement(self):
        script = Path(__file__).resolve().parents[1] / "scripts/evaluate_shadow.py"
        completed = subprocess.run(
            [sys.executable, str(script), "--repetitions", "2"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["workload"], "synthetic_held_out")
        self.assertEqual(result["task_pairs"], 8)
        self.assertEqual(result["alternate_pairs"], 0)
        self.assertTrue(result["serving_packets_identical"])
        self.assertTrue(result["zero_observed_leaks"])
        self.assertFalse(result["meaningful_improvement"])
        self.assertEqual(result["contradiction_regressions"], 0)
