import json
import subprocess
import sys
import unittest
from pathlib import Path


class LearningEvaluationTest(unittest.TestCase):
    def test_fixed_fixture_and_process_restart(self):
        script = Path(__file__).resolve().parents[1] / "scripts/evaluate_learning.py"
        child = subprocess.run(
            [sys.executable, str(script), "--repetitions", "3"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        results = json.loads(child.stdout)
        self.assertEqual(results["proposal_precision"], 0.5)
        self.assertAlmostEqual(results["proposal_recall"], 2 / 3)
        self.assertEqual(results["approvals"], ["rain likely"])
        self.assertEqual(results["false_approvals"], 0)
        self.assertEqual(results["canonical_promotions"], 0)
        self.assertEqual(results["foreign_candidates_visible"], 0)
        self.assertEqual(results["baseline_tasks_complete"], 2)
        self.assertEqual(results["augmented_tasks_complete"], 3)
        records = results["restarted_records"]
        self.assertEqual(records["gauge clear"]["refutations"], ["gauge-z"])
        self.assertEqual(records["gauge clear"]["state"], "rejected")
        self.assertEqual(records["wind rising"]["support_groups"], 1)
        self.assertEqual(records["river rising"]["support_groups"], 0)
        self.assertTrue(all(item["versions"] == [1, 2] for item in records.values()))
