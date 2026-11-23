import json
import subprocess
import sys
import unittest
from pathlib import Path


class OfflineReplayTest(unittest.TestCase):
    def test_temporary_controlled_replay(self):
        script = Path(__file__).resolve().parents[1] / "scripts/offline_experiment.py"
        for partition in ("train", "test_a", "test_b"):
            result = subprocess.run(
                [sys.executable, str(script), "--split", partition, "--repetitions", "2"],
                text=True,
                capture_output=True,
                check=True,
                timeout=30,
            )
            measured = json.loads(result.stdout)
            for mode in ("lexical", "hybrid", "guarded"):
                self.assertEqual(measured[mode]["tasks"], 4)
                self.assertEqual(measured[mode]["scope_leaks"], 0)
                self.assertEqual(measured[mode]["time_leaks"], 0)
            self.assertEqual(measured["observational_counterfactual"], "NOT ESTABLISHED")
