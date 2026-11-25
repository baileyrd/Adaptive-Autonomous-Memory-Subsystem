"""Replay the published evidence scorecards without loading the language model."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_q4_resume import inspect  # noqa: E402

EVENTS = ROOT / "docs/audit/q4-resume-events.jsonl"


class EvidenceTests(unittest.TestCase):
    def test_published_scorecards_match_packets(self):
        expected = json.loads((EVENTS.parent / "q4-resume-scorecards.json").read_bytes())
        self.assertEqual(inspect(EVENTS), expected)

    def test_changed_prompt_rejected(self):
        events = [json.loads(line) for line in EVENTS.read_bytes().splitlines()]
        row = next(r for r in events if r["event"] == "decision")
        row["prompt"] += "unexpected"
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "changed.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in events))
            with self.assertRaises(AssertionError):
                inspect(path)
