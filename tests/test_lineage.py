"""Independent small controls for disposable edge traversal and fixed-window selection."""

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_lineage import paired_interval, score, summarize  # noqa: E402
from evaluate_semantic import timestamp  # noqa: E402
from lineage_selector import components, respond  # noqa: E402


class LineageTests(unittest.TestCase):
    def setUp(self):
        self.task = dict(allowed=True, scope="s", topic="valve", checks=["seal"], day=5, as_of=6)
        self.pool = []
        for i in range(11):
            state = "blocked" if i == 10 else "clear"
            self.pool.append(
                dict(
                    evidence_id=str(i),
                    digest=state,
                    observed_at=timestamp(4),
                    source_actor=str(i),
                    source_locator=str(i),
                    preview=json.dumps(dict(state=state, topic="valve", check="seal")),
                )
            )
        self.store = Mock()
        self.store.get_evidence.return_value = SimpleNamespace(
            scope="s", recorded_at=timestamp(6), observed_at=timestamp(5)
        )
        self.edge = dict(
            child="0",
            parent="1",
            granted=True,
            principal="pilot",
            scope="s",
            recorded=6,
            effective=5,
        )

    def groups(self, edges, withheld=()):
        return components(self.store, self.task, self.pool, edges, set(withheld))

    def test_chain_refill_and_shared_origin_disagreement(self):
        edges = [{**self.edge, "child": str(i), "parent": str(i - 1)} for i in range(1, 11)]
        groups = self.groups(edges)
        self.assertEqual(len(set(groups.values())), 1)
        self.assertEqual(respond(self.pool, self.task, {})["decision"]["action"], "proceed")
        result = respond(self.pool, self.task, groups)
        self.assertEqual([r["evidence_id"] for r in result["context"]], ["0", "10"])
        self.assertEqual(result["decision"]["action"], "abstain")
        self.assertEqual(result["source_groups"], 1)
        self.assertEqual(result["independent_pairs"], [])
        later = [
            {**r, "observed_at": timestamp(5)} if r["evidence_id"] == "10" else r for r in self.pool
        ]
        self.assertEqual(respond(later, self.task, groups)["decision"]["action"], "stop")

    def test_invisible_relation_is_not_read(self):
        for change in (
            dict(granted=False),
            dict(scope="private"),
            dict(principal="other"),
            dict(recorded=7),
            dict(effective=6),
        ):
            self.assertEqual(self.groups([{**self.edge, **change}]), {})
        self.task["allowed"] = False
        self.assertEqual(self.groups([self.edge]), {})
        self.store.get_evidence.assert_not_called()

    def test_endpoints_on_each_hop(self):
        edges = [self.edge, {**self.edge, "child": "1", "parent": "2"}]
        for bad in ("missing", "revoked", "foreign", "late", "premature"):

            def read(access, rid):
                if rid != "1":
                    return SimpleNamespace(
                        scope="s", recorded_at=timestamp(1), observed_at=timestamp(1)
                    )
                if bad == "missing":
                    return None
                return SimpleNamespace(
                    scope="other" if bad == "foreign" else "s",
                    recorded_at=timestamp(7 if bad == "late" else 1),
                    observed_at=timestamp(6 if bad == "premature" else 1),
                )

            self.store.get_evidence.side_effect = read
            self.assertEqual(self.groups(edges, ["1"] if bad == "revoked" else []), {})
        self.assertEqual(self.groups([{**self.edge, "child": "not-in-pool"}]), {})

    def test_unknown_origins_and_regressions(self):
        out = respond(self.pool, self.task, {})
        key = dict(expected="proceed", origins={str(i): None for i in range(11)})
        a = score(out, key)
        self.assertIsNone(a["excess_proxy"])
        self.assertEqual(a["unknown_rows"], 8)
        b = score({**out, "decision": {"action": "abstain"}}, key)
        rows = [dict(family="one", scores=dict(A=a, B=b))]
        self.assertEqual(summarize(rows)["correct_lost"], 1)
        self.assertEqual(paired_interval(rows, "correct"), [-1, -1, -1])
