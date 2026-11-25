"""Model-free qualification checks suitable for default CI."""

import json
import sys
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_seal_room import oracle  # noqa: E402
from audit_seal_room import inspect  # noqa: E402
from evaluate_seal_room import run  # noqa: E402
from evaluate_seal_room import CASE_SHA, LABEL_SHA, check_sources, digest  # noqa: E402
from qualification_cases import LEGENDS, fixtures, render  # noqa: E402


class QualificationTests(unittest.TestCase):
    def test_synthetic_transport_and_audit_reject_corruption(self):
        real_run = subprocess.run
        pid = 0

        def transport(args, **kwargs):
            nonlocal pid
            if "-I" not in args:
                return real_run(args, **kwargs)
            pid += 1
            raw = dict(
                choices=[dict(text="A", finish_reason="length")],
                usage=dict(completion_tokens=1, total_tokens=100),
            )
            return subprocess.CompletedProcess(args, 0, json.dumps(dict(raw=raw, pid=pid)))

        with tempfile.TemporaryDirectory() as tmp:
            stream = Path(tmp) / "synthetic.jsonl"
            with (
                patch("evaluate_seal_room.preflight", return_value={"test": True}),
                patch("evaluate_seal_room.subprocess.run", side_effect=transport),
            ):
                run(Path("unused"), stream)
            result = inspect(stream)
            self.assertEqual(result["gate"]["paired_correct"], 0)
            self.assertEqual(result["gate"]["correct"], 4)
            events = list(map(json.loads, stream.read_text().splitlines()))
            events[2]["decoded"] = "invalid"
            stream.write_text("\n".join(map(json.dumps, events)))
            with self.assertRaisesRegex(ValueError, "adjudication"):
                inspect(stream)

    def test_design_pins_and_separation(self):
        cases, keys = fixtures()
        self.assertEqual([digest(cases), digest(keys)], [CASE_SHA, LABEL_SHA])
        self.assertEqual(sorted(Counter(k["action"] for k in keys.values()).values()), [2] * 5)
        self.assertTrue(all(a != b for a, b in zip(*LEGENDS, strict=True)))
        prior = b"".join(
            p.read_bytes()
            for p in (ROOT / "docs/audit").iterdir()
            if p.suffix in {".jsonl", ".json"} and not p.name.startswith("seal-room")
        )
        seen = set()
        for c in cases:
            identities = {
                c["id"],
                *(r["id"] for r in c["records"]),
                *(r["scope"] for r in c["records"]),
                *(r["source_actor"] for r in c["records"]),
                *(r["source_locator"] for r in c["records"]),
            }
            self.assertFalse(seen & identities)
            self.assertFalse(any(v.encode() in prior for v in identities))
            seen.update(identities)

    def test_denied_and_incomplete(self):
        cases, _ = fixtures()
        denied = next(c for c in cases if not c["request"]["allowed"])
        check_sources(denied, [])
        with self.assertRaises(ValueError):
            check_sources(cases[0], [])
        public = {"access": "denied", "goal": denied["request"]["goal"], "observations": []}
        self.assertEqual(oracle(public, []), ("abstain", set()))
        with self.assertRaises(ValueError):
            oracle(public, [{"evidence_id": "private"}])
        for legend in LEGENDS:
            msg = render(public, legend).split("<|im_start|>user\n")[1].split("<|im_end|>")[0]
            self.assertEqual(json.loads(msg), public)

    def test_conflict_requires_both_witnesses(self):
        obs = [
            {"role": "executor", "observed": "day5", "payload": {"constraints": [x]}}
            for x in ("a", "b")
        ]
        self.assertEqual(
            oracle({"access": "granted", "observations": obs}, [{"evidence_id": x} for x in "12"]),
            ("abstain", {"1", "2"}),
        )
