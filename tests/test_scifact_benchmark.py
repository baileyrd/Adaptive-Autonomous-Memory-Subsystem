import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluate_scifact.py"

CORPUS = [
    {"doc_id": 1, "title": "Kinase inhibition", "abstract": ["Drug X blocks kinase Y.", "Done."]},
    {"doc_id": 2, "title": "Gut flora", "abstract": ["Microbes alter digestion in mice."]},
    {"doc_id": 3, "title": "Bone density", "abstract": ["Calcium intake raises density."]},
    {"doc_id": 4, "title": "Sleep", "abstract": ["Sleep loss impairs memory recall."]},
]
CLAIMS = [
    {"id": 1, "claim": "Drug X inhibits kinase Y.", "evidence": {"1": [{"sentences": [0]}]}},
    {"id": 2, "claim": "Microbes change digestion.", "evidence": {"2": [{"sentences": [0]}]}},
    {"id": 3, "claim": "Calcium improves bones.", "evidence": {"3": [{"sentences": [0]}]}},
    {"id": 4, "claim": "Sleep deprivation harms memory.", "evidence": {"4": [{"sentences": [0]}]}},
    {"id": 5, "claim": "Unlabeled claim.", "evidence": {}},
]


def _archive() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, rows in (
            ("data/corpus.jsonl", CORPUS),
            ("data/claims_train.jsonl", CLAIMS[:3]),
            ("data/claims_dev.jsonl", CLAIMS[3:]),
        ):
            payload = "\n".join(json.dumps(row) for row in rows).encode()
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


class SciFactBenchmarkTest(unittest.TestCase):
    def run_script(self, payload: bytes, digest: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.tar.gz"
            path.write_bytes(payload)
            return subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--scifact",
                    str(path),
                    "--expected-sha256",
                    digest,
                    "--shards",
                    "2",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

    def test_sharded_replay_reports_baselines_and_bm25_without_leaks(self):
        payload = _archive()
        completed = self.run_script(payload, sha256(payload).hexdigest())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["excluded_cross_shard_claims"], 0)
        heldout = result["heldout"]
        self.assertEqual(heldout["tasks"], 4)
        for arm in ("lexical", "guarded", "staged", "bm25", "bm25_guarded"):
            profile = heldout["profiles"][arm]
            self.assertEqual(profile["scope_leaks"] + profile["time_leaks"], 0)
        self.assertIn("bm25_guarded", heldout["versus_guarded"])

    def test_checksum_mismatch_is_rejected(self):
        completed = self.run_script(_archive(), "0" * 64)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("checksum", completed.stderr)


if __name__ == "__main__":
    unittest.main()
