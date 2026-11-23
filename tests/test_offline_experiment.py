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

    def test_held_out_candidate_and_lexical_outage(self):
        script = Path(__file__).resolve().parents[1] / "scripts/evaluate_offline_candidate.py"
        run = subprocess.run(
            [sys.executable, str(script), "--repetitions", "3"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        result = json.loads(run.stdout)
        self.assertTrue(result["passes_fixture_research_gate"])
        self.assertFalse(result["beats_guarded_across_partitions"])
        self.assertEqual(result["calibration"]["paired_opt_in_tasks"], 4)
        self.assertEqual(result["calibration"]["brier_gain"], 0.1875)
        self.assertEqual(result["runtime_activation"], "disabled")
        for partition in result["partitions"].values():
            self.assertEqual(partition["outage"]["lexical_tasks"], 4)
            self.assertEqual(partition["outage"]["reported_provider_fallbacks"], 2)
            self.assertTrue(partition["outage"]["matches_lexical_quality"])
            self.assertEqual(partition["profiles"]["candidate"]["scope_leaks"], 0)
            self.assertEqual(partition["profiles"]["candidate"]["time_leaks"], 0)
            self.assertEqual(partition["contradiction_regressions"], 0)

    def test_split_rejects_cross_group_source_and_payload_copies(self):
        script = Path(__file__).resolve().parents[1] / "scripts"
        run = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import copy
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from offline_experiment import FIXTURE, load_groups
original = json.loads(FIXTURE.read_text())
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "fixture.json"
    for column in (3, 4):
        data = copy.deepcopy(original)
        data["groups"][2]["records"][0][column] = data["groups"][0]["records"][0][column]
        path.write_text(json.dumps(data))
        try:
            load_groups(path)
        except ValueError as error:
            if "Independent groups" not in str(error):
                raise
        else:
            raise RuntimeError("Accepted a cross-partition copy")
""",
                str(script),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
