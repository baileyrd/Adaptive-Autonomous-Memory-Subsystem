import json
import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _article(title: str, paragraphs: list[tuple[str, str]]) -> dict:
    return {
        "title": title,
        "paragraphs": [
            {
                "context": context,
                "qas": [{"question": question, "answers": [{"answer_start": 0}]}],
            }
            for context, question in paragraphs
        ],
    }


# Titles chosen so the stable hash split yields both partitions.
FIXTURE = {
    "data": [
        _article(
            title,
            [
                ("The harbor crane lifted steel containers.", "What lifted containers?"),
                ("Rainfall flooded the orchard near the river.", "Which orchard flooded?"),
                ("x " * 300 + "late answer about turbines", "What about turbines?"),
            ],
        )
        for title in ("alpha", "beta", "gamma", "delta")
    ]
}


class RetrievalBenchmarkTest(unittest.TestCase):
    def run_benchmark(
        self, payload: bytes, digest: str, *extra: str
    ) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "squad.json"
            path.write_bytes(payload)
            return subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "evaluate_retrieval.py"),
                    "--squad",
                    str(path),
                    "--expected-sha256",
                    digest,
                    "--questions-per-paragraph",
                    "1",
                    *extra,
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=60,
            )

    def test_grouped_benchmark_reports_all_baselines_without_leaks(self):
        payload = json.dumps(FIXTURE).encode()
        completed = self.run_benchmark(payload, sha256(payload).hexdigest())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        splits = [result[name] for name in ("design", "heldout") if name in result]
        self.assertEqual(sum(split["tasks"] for split in splits), 12)
        self.assertEqual(sum(split["articles"] for split in splits), 4)
        self.assertGreater(result["records_beyond_preview"], 0)
        for split in splits:
            profiles = split["profiles"]
            self.assertEqual(set(profiles), {"lexical", "hybrid", "guarded", "staged"})
            for profile in profiles.values():
                self.assertEqual(profile["scope_leaks"] + profile["time_leaks"], 0)
            best = max(profiles[key]["satisfied"] for key in ("lexical", "hybrid"))
            self.assertGreaterEqual(split["oracle_router"]["satisfied"], best)
            for comparison in split["versus_guarded"].values():
                low, high = comparison["ci95"]
                self.assertLessEqual(low, comparison["mean_delta"])
                self.assertLessEqual(comparison["mean_delta"], high)
                total = comparison["wins"] + comparison["losses"] + comparison["ties"]
                self.assertEqual(total, split["tasks"])

    def test_ranking_arms_are_compared_against_guarded_without_leaks(self):
        payload = json.dumps(FIXTURE).encode()
        completed = self.run_benchmark(payload, sha256(payload).hexdigest(), "--ranking", "bm25")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        for split in (result[name] for name in ("design", "heldout") if name in result):
            for arm in ("bm25", "bm25_hybrid"):
                profile = split["profiles"][arm]
                self.assertEqual(profile["scope_leaks"] + profile["time_leaks"], 0)
                self.assertIn(arm, split["versus_guarded"])
            best = max(split["profiles"][arm]["satisfied"] for arm in ("bm25", "bm25_hybrid"))
            self.assertGreaterEqual(split["oracle_bm25_router"]["satisfied"], best)

    def test_checksum_mismatch_is_rejected_before_processing(self):
        completed = self.run_benchmark(json.dumps(FIXTURE).encode(), "0" * 64)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("checksum", completed.stderr)

    def test_split_is_stable_and_bootstrap_resamples_whole_groups(self):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1])\n"
            "from evaluate_retrieval import article_split, grouped_interval\n"
            "assert article_split('alpha') == article_split('alpha')\n"
            "assert {article_split(t) for t in ('alpha','beta','gamma','delta')}"
            " == {'design', 'heldout'}\n"
            "assert grouped_interval({'a': [1, 1], 'b': [1]}) == [1.0, 1.0]\n"
            "assert grouped_interval({'a': [0, 0], 'b': [0]}) == [0.0, 0.0]\n"
            "low, high = grouped_interval({'a': [1, 1, 1], 'b': [-1], 'c': [0]})\n"
            "assert low < 0.4 < high, (low, high)\n"
        )
        subprocess.run([sys.executable, "-c", code, str(SCRIPTS)], check=True, timeout=30)


if __name__ == "__main__":
    unittest.main()
