"""Scope, request, and citation-scoring guards for the gap experiment."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_gap_requests import decision, replay, request_for


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

    def test_replay_rejects_unrelated_citation_for_correct_action(self):
        def unrelated_citation(task, readings):
            result = decision(task, readings)
            if result["action"] != "abstain":
                return {**result, "citations": [{"id": "unrelated", "digest": "sha256:unrelated"}]}
            return result

        with patch("evaluate_gap_requests.decision", side_effect=unrelated_citation):
            with self.assertRaisesRegex(ValueError, "Unsupported substantive action"):
                replay()
