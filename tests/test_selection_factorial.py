"""Check committed offline results through the normal replay entry point."""

import json
import subprocess
import sys
import unittest
from pathlib import Path


class SelectionFactorialTest(unittest.TestCase):
    def test_replay_matches_every_published_decision(self):
        root = Path(__file__).resolve().parents[1]
        report = json.loads(
            subprocess.check_output(
                [sys.executable, str(root / "scripts/evaluate_selection_factorial.py")], timeout=120
            )
        )
        published = [
            json.loads(line)
            for line in (root / "docs/audit/selection-factorial-decisions.jsonl")
            .read_text()
            .splitlines()
        ]
        for row in [*report["rows"], *published]:
            row.pop("elapsed_ms")
        self.assertEqual(report.pop("rows"), published)
        expected = json.loads((root / "docs/audit/selection-factorial-results.json").read_text())
        for item in (report, expected):
            for arm in item["summary"].values():
                arm.pop("median_ms")
        self.assertEqual(report, expected)
