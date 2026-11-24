"""Audit the published model experiment without optional inference or network access."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_model_decisions import (  # noqa: E402
    ARMS,
    BUDGET,
    CognitiveMemory,
    SQLiteMemoryStore,
    context_for,
    histories,
    obtain_context,
    prepare,
)


class ModelDecisionTest(unittest.TestCase):
    def test_published_actions_and_contexts(self):
        episodes, keys = histories()
        report = json.loads((ROOT / "docs/audit/model-decisions-results.json").read_text())
        self.assertEqual(set(report["arms"]), set(ARMS))
        self.assertEqual(len(episodes), 14)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            prepare(path, episodes)
            memory = CognitiveMemory(SQLiteMemoryStore(path))
            for arm, rows in report["arms"].items():
                for episode, row in zip(episodes, rows, strict=True):
                    task = episode["tasks"][0]
                    self.assertEqual(row["task_id"], task["id"])
                    self.assertEqual(row["expected"], keys[task["id"]])
                    self.assertEqual(row["success"], row["action"] == keys[task["id"]])
                    self.assertLessEqual(row["prompt_tokens"] + 1, 2048)
                    eligible = {
                        r["id"]
                        for r in episode["observations"]
                        if r["scope"] == task["scope"] and r["recorded"] <= 6 and r["observed"] <= 6
                    }
                    self.assertTrue(set(row["context"]) <= eligible)
                    if arm == "neural":
                        continue
                    if arm == "copy_diverse":
                        context, _ = obtain_context(memory, task, arm, BUDGET)
                    else:
                        context = context_for(memory, task, arm, BUDGET)
                    self.assertEqual([r["evidence_id"] for r in context], row["context"])
