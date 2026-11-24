"""Index and reopened-serving diagnostics use real scoped storage without optional models."""

import json
import platform
import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import profile_retrieval_memory as probe
from aams.recall import CognitiveMemory
from aams.representations import DeterministicFixtureProvider
from aams.storage import SQLiteMemoryStore


GROUPS = [
    {
        "domain": "visible",
        "records": [
            ["allowed", "visible", 1, "harbor crane", "fixture"],
            ["future", "visible", 9, "harbor crane future", "fixture"],
            ["private", "hidden", 1, "harbor crane secret", "fixture"],
        ],
        "tasks": [{"query": "harbor crane", "day": 2}],
    }
]


class RetrievalMemoryTests(unittest.TestCase):
    def test_build_reopen_and_scoped_time_filtered_cold_and_warm_serving(self):
        with tempfile.TemporaryDirectory() as root:
            args = SimpleNamespace(
                data=Path(root) / "data",
                partition="dev",
                arm="guarded",
                stage="build",
                db=Path(root) / "memory.db",
                repetitions=2,
            )
            args.data.write_bytes(b"fixture")
            args.groups = Path(root) / "groups.json"
            args.groups.write_text(json.dumps(GROUPS))
            args.groups_sha256 = probe.file_sha256(args.groups)
            with (
                patch.dict(probe.DATASET_PINS, {"dev": probe.file_sha256(args.data)}),
                patch.object(
                    probe, "OnnxSentenceEncoder", side_effect=AssertionError("Optional import")
                ),
            ):
                built = probe.measure(args)
                self.assertGreater(built["database_bytes"], 0)
                with self.assertRaises(ValueError):
                    probe.measure(args)
                args.stage = "serve"
                served = probe.measure(args)
                self.assertEqual(served["requests"], 2)
                self.assertEqual(
                    set(served["snapshots"]),
                    {"workload_loaded", "provider_loaded", "cold_served", "warm_served"},
                )
                self.assertNotIn("harbor", json.dumps(served))
            memory = CognitiveMemory(SQLiteMemoryStore(args.db))
            with patch.object(memory, "recall", wraps=memory.recall) as recall:
                probe.recall_pass(memory, GROUPS, DeterministicFixtureProvider())
                access, need = recall.call_args.args
                packet = memory.recall(access, need, **recall.call_args.kwargs)
                self.assertEqual([item["id"] for item in packet["items"]], ["f-allowed"])

    def test_fresh_process_order_and_failure_propagation(self):
        platform.platform()  # Resolve stdlib uname before mocking subprocess.run.
        manifest = json.loads((Path(probe.__file__).parent / "onnx_variant_pins.json").read_text())[
            "minilm-l3-q8"
        ]
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            variant = root / "manifest.json"
            variant.write_text(json.dumps(manifest))
            args = SimpleNamespace(
                model=root, variant=variant, data=root / "data", partition="dev", repetitions=2
            )
            args.data.write_bytes(b"fixture")
            calls = []

            def child(command, **kwargs):
                self.assertIn("-I", command)
                self.assertTrue(kwargs["check"])
                if "--prepare" in command:
                    Path(command[command.index("--groups") + 1]).write_text(json.dumps(GROUPS))
                    return SimpleNamespace(stdout="")
                self.assertEqual(
                    command[command.index("--groups-sha256") + 1],
                    sha256(json.dumps(GROUPS).encode()).hexdigest(),
                )
                arm = command[command.index("--arm") + 1]
                stage = command[command.index("--stage") + 1]
                calls.append((arm, stage, command[command.index("--db") + 1]))
                row = {
                    "arm": arm,
                    "stage": stage,
                    "warm_ms": [1, 2],
                    "snapshots": {"end": {"peak_rss_kib": 100}},
                }
                return SimpleNamespace(stdout=json.dumps(row))

            with (
                patch.dict(probe.DATASET_PINS, {"dev": probe.file_sha256(args.data)}),
                patch.object(probe.subprocess, "run", side_effect=child),
            ):
                report = probe.run(args)
                self.assertEqual(
                    [(a, s) for a, s, _ in calls],
                    [(a, s) for a in probe.ARMS for s in probe.STAGES],
                )
                self.assertEqual(calls[1][2], calls[2][2])
                self.assertNotEqual(calls[1][2], calls[4][2])
                self.assertTrue(report["resource_screen"]["passes"])
            with (
                patch.dict(probe.DATASET_PINS, {"dev": probe.file_sha256(args.data)}),
                patch.object(
                    probe.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "child")
                ),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    probe.run(args)

    def test_bad_dataset_refused_before_child_or_encoder(self):
        with tempfile.TemporaryDirectory() as root:
            data = Path(root) / "bad.json"
            data.write_text("{}")
            with patch.object(probe.subprocess, "run") as child:
                with self.assertRaisesRegex(ValueError, "checksum"):
                    probe.run(SimpleNamespace(data=data, partition="dev"))
                child.assert_not_called()


if __name__ == "__main__":
    unittest.main()
