"""Unscored reproduction of the frozen selector's multi-parent limitation (#125)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from aams.recall import CognitiveMemory
from aams.storage import SQLiteMemoryStore
from evaluate_cognitive_tasks import prepare
from evaluate_copy_context import candidate_pool
from evaluate_lineage import WINDOW
from lineage_cases import fixtures
from lineage_selector import components, respond


class MultiParentProbe(unittest.TestCase):
    def test_report_citing_two_independent_inspections(self) -> None:
        """Use the same three records in both arms; only their visible links differ."""
        episode = next(e for e in fixtures()[0] if e["family"] == "independent")
        records = episode["observations"][:3]
        # In this probe the first two are independent inspections. The third summarizes both.
        first, second, report = (row["id"] for row in records)
        task = episode["tasks"][0]
        links = [
            dict(
                child=report,
                parent=parent,
                granted=True,
                principal="pilot",
                scope=task["scope"],
                recorded=4,
                effective=3,
            )
            for parent in (first, second)
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            prepare(path, [{**episode, "observations": records}])
            store = SQLiteMemoryStore(path)
            pool, truncated = candidate_pool(CognitiveMemory(store), task, WINDOW)
            self.assertFalse(truncated)
            self.assertEqual(len({(r["digest"], r["observed_at"]) for r in pool}), 1)
            baseline = respond(pool, task, {})
            linked = respond(pool, task, components(store, task, pool, links, set()))
        self.assertEqual([r["evidence_id"] for r in baseline["context"]], [first, second, report])
        self.assertEqual([r["evidence_id"] for r in linked["context"]], [first])
        self.assertEqual((baseline["source_groups"], linked["source_groups"]), (3, 1))
        self.assertEqual([r["decision"]["action"] for r in (baseline, linked)], ["proceed"] * 2)
