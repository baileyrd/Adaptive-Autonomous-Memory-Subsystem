"""Scope and request guards on toy records, separate from the frozen histories."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_gap_requests import decision, request_for


class GapRequestTests(unittest.TestCase):
    def setUp(self):
        self.task = dict(scope="a", query="toy", instrument="x", round=3, observation_id="r")

    def test_reading_requires_scope_round_and_id(self):
        receipt = dict(
            id="r",
            scope="a",
            producer="meter",
            digest="fixture",
            payload=dict(kind="accuracy_reading", instrument="x", round=3, status="pass"),
        )
        self.assertEqual(decision(self.task, [receipt])["action"], "enable")
        for change in (
            {"scope": "b"},
            {"id": "other"},
            {"payload": {**receipt["payload"], "round": 2}},
        ):
            self.assertEqual(decision(self.task, [{**receipt, **change}])["action"], "abstain")

    def test_request_names_exact_observation_and_authorized_basis(self):
        manifest = dict(
            id="m",
            digest="fingerprint",
            scope="a",
            producer="bench-clerk",
            payload=dict(
                kind="verification_task", query="toy", observation_id="r", instrument="x", round=3
            ),
        )
        request = request_for(self.task, manifest)
        self.assertEqual(request["basis"], {"id": "m", "digest": "fingerprint"})
        self.assertEqual(request["observation"]["id"], "r")
        self.assertEqual(request["could_change"]["fail_to"], "withhold")
        self.assertIsNone(request_for(self.task, {**manifest, "scope": "b"}))
