"""Audit published outputs without executing the two selectors."""

import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lineage_cases import CONTROLS, fixtures  # noqa: E402


class LineageEvidenceTests(unittest.TestCase):
    def test_archive_and_recount(self):
        audit = ROOT / "docs/audit"
        data = json.loads((audit / "lineage-scorecards.json").read_bytes())
        for section in ("rows", "controls"):
            data[section] = list(
                map(json.loads, (audit / f"lineage-{section}.jsonl").read_bytes().splitlines())
            )
        raw = (json.dumps(data, sort_keys=True) + "\n").encode()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "03b120cd5d24342c852e2bd528fad0c48023c5c31908ef0adcb84f204c9913a9",
        )
        cases, keys = fixtures()
        baseline = {}
        totals = Counter()
        for e, r in zip(cases, data["rows"], strict=True):
            task = e["tasks"][0]
            self.assertEqual(e["id"], r["task"])
            source = {
                x["id"]: x
                for x in e["observations"]
                if task["allowed"]
                and x["id"] not in e["withheld"]
                and x["scope"] == task["scope"]
                and x["recorded"] <= task["as_of"]
                and x["observed"] <= task["day"]
            }
            self.assertEqual(set(source), {p["evidence_id"] for p in r["pool"]})
            for arm, out in r["responses"].items():
                ctx = out["context"]
                self.assertLessEqual(len(ctx), 8)
                self.assertLessEqual(len(json.dumps(ctx, sort_keys=True).encode()), 8192)
                self.assertEqual([c for c in r["pool"] if c in ctx], ctx)
                for c in ctx:
                    self.assertEqual(source[c["evidence_id"]]["text"], c["preview"])
                self.assertEqual(out["independent_pairs"], [])
                if e["family"] == "independent":
                    self.assertEqual(len(ctx), len(source))
                if e["family"] == "dispute":
                    self.assertEqual(
                        {json.loads(c["preview"])["state"] for c in ctx}, {"clear", "blocked"}
                    )
                if e["family"] == "revoked":
                    self.assertEqual(
                        (ctx, out["source_groups"], out["decision"]["action"]), ([], 0, "abstain")
                    )
            act = [r["responses"][arm]["decision"]["action"] for arm in "AB"]
            expected = keys[e["id"]]["expected"]
            totals.update(
                gain=act[0] == "proceed" and expected != "proceed" and act[1] == expected,
                loss=act[0] == expected and act[1] != expected,
                remaining=act[1] == "proceed" and expected != "proceed",
            )
            if e["family"] == "missing":
                baseline[e["id"]] = r["responses"]["B"]
        self.assertEqual(totals, dict(gain=8, loss=0, remaining=8))
        self.assertCountEqual(
            [(c["task"], c["overlay"]) for c in data["controls"]],
            [(i, mode) for i in baseline for mode in CONTROLS],
        )
        for c in data["controls"]:
            if c["overlay"] == "visible":
                self.assertEqual(c["response"]["decision"]["action"], "stop")
            else:
                self.assertEqual(c["response"], baseline[c["task"]])
                self.assertEqual(c["visible_components"], {})
