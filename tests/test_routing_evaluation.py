import json
import subprocess
import sys
import unittest
from pathlib import Path


class RoutingEvaluationTest(unittest.TestCase):
    def test_held_out_workload_obeys_explicit_mode_and_falls_back(self):
        script = Path(__file__).resolve().parents[1] / "scripts/evaluate_routing.py"
        for strategy, false_routes in (("lexical", 0), ("hybrid", 3), ("routed", 0)):
            with self.subTest(strategy=strategy):
                run = subprocess.run(
                    [sys.executable, str(script), strategy, "--repetitions", "2"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                result = json.loads(run.stdout)
                self.assertEqual(result["false_hybrid_routes"], false_routes)
                self.assertEqual(result["scope_leaks"], 0)
                self.assertEqual(result["future_leaks"], 0)
                self.assertEqual(result["contradictions"], [1, 1])
                self.assertEqual(result["timed_queries"], 20)
                if strategy == "routed":
                    by_query = {row["query"]: row for row in result["outcomes"]}
                    self.assertEqual(by_query["archive backup"]["status"], "stale")
                    self.assertEqual(
                        by_query["sensor voltage spike"]["status"], "provider_unavailable"
                    )
                    self.assertEqual(by_query["confidential treasury"]["ids"], [])
