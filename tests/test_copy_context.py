"""#119: selection controls must preserve canonical visibility and frozen decision evidence."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cognitive_task_agent import decide  # noqa: E402
from copy_context_cases import RECIPE, cases  # noqa: E402
from copy_context_selector import copy_key, select_context  # noqa: E402
from evaluate_copy_context import checked_inputs, candidate_pool, obtain_context  # noqa: E402
from evaluate_cognitive_tasks import database_digest, prepare, validate_context  # noqa: E402
from aams.recall import CognitiveMemory  # noqa: E402
from aams.storage import SQLiteMemoryStore  # noqa: E402


class CopyContextTests(unittest.TestCase):
    def setUp(self):
        self.recipe = json.loads(RECIPE.read_text())

    def test_only_exact_declared_origin_content_and_time_groups_collapse(self):
        row = {
            "evidence_id": "a",
            "source_actor": "sensor",
            "source_locator": "source",
            "digest": "clear-digest",
            "observed_at": "2026-01-01",
            "preview": "clear",
        }
        duplicate = {**row, "evidence_id": "b", "recorded_at": "2026-01-04"}
        conflict = {**row, "evidence_id": "c", "digest": "blocked-digest", "preview": "blocked"}
        independent = {**row, "evidence_id": "d", "source_actor": "different-sensor"}
        changed_time = {**row, "evidence_id": "e", "observed_at": "2026-01-02"}
        rows = [row, duplicate, conflict, independent, changed_time]
        selected = select_context(rows, max_citations=8, max_bytes=8192)
        self.assertEqual([r["evidence_id"] for r in selected], ["a", "c", "d", "e"])
        self.assertEqual(copy_key(row), copy_key(duplicate))
        self.assertEqual(select_context(rows, max_citations=1, max_bytes=8192), [row])
        self.assertEqual(select_context(rows, max_citations=8, max_bytes=2), [])

    def test_no_adverse_preference_and_rank_order_unchanged(self):
        def row(identifier, preview):
            return {
                "evidence_id": identifier,
                "source_actor": identifier,
                "source_locator": identifier,
                "digest": identifier,
                "observed_at": "2026-01-01",
                "preview": preview,
            }

        rows = [row("positive", "clear"), row("negative", "blocked")]
        self.assertEqual(select_context(rows, max_citations=1, max_bytes=8192), rows[:1])
        self.assertEqual(select_context(rows[::-1], max_citations=1, max_bytes=8192), rows[-1:])

    def test_source_disjointness_and_input_pins(self):
        recipe, episodes = checked_inputs()
        self.assertEqual(len(episodes), 70)
        self.assertEqual(sum(len(e["tasks"]) for e in episodes if e["split"] == "heldout"), 112)
        for field in ("id", "source", "scope"):
            sets = [
                {r[field] for e in episodes if e["split"] == split for r in e["observations"]}
                for split in ("design", "heldout")
            ]
            self.assertFalse(sets[0] & sets[1])
        altered = {**recipe, "seed": -1}
        with patch("evaluate_copy_context.RECIPE") as path:
            path.read_bytes.return_value = json.dumps(altered).encode()
            with self.assertRaisesRegex(ValueError, "checksum"):
                checked_inputs()

    def test_opposing_same_origin_reports_survive_and_recovery_is_not_suppressed(self):
        episodes = [
            e
            for e in cases(self.recipe)
            if e["split"] == "design" and e["family"] in ("same_time_conflict", "recovery")
        ]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "memory.db"
            prepare(path, episodes)
            before = database_digest(path)
            memory = CognitiveMemory(SQLiteMemoryStore(path))
            for episode in episodes:
                task = episode["tasks"][-1]
                context, metadata = obtain_context(memory, task, "copy_diverse", self.recipe)
                validate_context(memory.store, task, context)
                self.assertFalse(metadata["candidate_window_truncated"])
                self.assertLessEqual(len(context), 8)
                self.assertLessEqual(len(json.dumps(context, sort_keys=True).encode()), 8192)
                action = decide({"topic": task["topic"], "checks": task["checks"]}, context)
                if episode["family"] == "same_time_conflict":
                    self.assertTrue(action["conflict_detected"])
                    self.assertEqual(action["action"], "abstain")
                else:
                    self.assertEqual(action["action"], "proceed")
            self.assertEqual(before, database_digest(path))

    def test_time_filtering_precedes_copy_grouping_and_bad_candidates_invalidate(self):
        episode = next(e for e in cases(self.recipe) if e["family"] == "temporal_history")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "memory.db"
            prepare(path, [episode])
            memory = CognitiveMemory(SQLiteMemoryStore(path))
            task = episode["tasks"][-1]
            context, _ = obtain_context(memory, task, "copy_diverse", self.recipe)
            self.assertFalse(
                any(r["evidence_id"].endswith(("-z-later", "-private", "-future")) for r in context)
            )
            validate_context(memory.store, task, context)
            pool, _ = candidate_pool(memory, task, self.recipe)
            bad = copy.deepcopy(pool)
            bad[0]["digest"] = "tampered"
            packet = {"items": [{"citations": bad}], "truncated": False}
            with patch.object(memory, "recall", return_value=packet):
                with self.assertRaisesRegex(ValueError, "provenance"):
                    candidate_pool(memory, task, self.recipe)

    def test_full_process_experiment_preserves_history_and_counts_without_required_gains(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "evaluate_copy_context.py")],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout[:500])
        report = json.loads(result.stdout)
        self.assertEqual(report["historical_reproduction"]["matched_frozen_decisions"], 144)
        for row in report["historical_reproduction"]["diagnostics"]:
            self.assertFalse(row["bounded_contains_failure"])
            self.assertTrue(row["full_contains_failure"])
            self.assertEqual(row["bounded_decision"]["action"], "proceed")
            self.assertEqual(row["dedup_after_truncation_decision"]["action"], "proceed")
            self.assertEqual(row["full_visible_decision"]["action"], "stop")
        tasks = None
        for arm in report["arms"].values():
            actual = [row["task_id"] for row in arm["rows"]]
            if tasks is not None:
                self.assertEqual(actual, tasks)
            tasks = actual
            self.assertEqual(len(actual), 140)
            self.assertTrue(arm["canonical_unchanged"])
            self.assertNotEqual(arm["pid"], arm["prepare_pid"])
            self.assertEqual(arm["summary"]["heldout"]["families"], 7)
        # No minimum gain: negative results must remain valid experiment outputs.
        self.assertIn("unsafe_proceed", report["paired_control_minus_structured"]["heldout"])


if __name__ == "__main__":
    unittest.main()
