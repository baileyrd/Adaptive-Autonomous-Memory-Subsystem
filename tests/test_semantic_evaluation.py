import json
import subprocess
import sys
import unittest
from pathlib import Path


class SemanticEvaluationTest(unittest.TestCase):
    def test_offline_fixture_and_lexical_comparators(self):
        script = Path(__file__).resolve().parents[1] / "scripts/evaluate_semantic.py"
        results = {}
        for mode in ("lexical", "fixture"):
            run = subprocess.run(
                [sys.executable, str(script), mode, "--repetitions", "2"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            results[mode] = json.loads(run.stdout)
            measured = results[mode]
            self.assertEqual(measured["cross_scope_disclosures"], 0)
            self.assertEqual(measured["historical_disclosures"], 0)
            self.assertEqual(measured["contradictions_retained"], 1)
            self.assertEqual(measured["timed_queries"], 18)
        self.assertEqual(results["lexical"]["recall_at_3"], 0.6875)
        self.assertEqual(results["fixture"]["recall_at_3"], 0.75)
        self.assertEqual(results["fixture"]["vectors"], 22)
        self.assertEqual(results["fixture"]["stale_fallback"], "stale")
