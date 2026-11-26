"""Qualification gate and citation scoring checks without a model dependency."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_shipment_actor import assess, legend, response_text, run


class ShipmentActorTests(unittest.TestCase):
    def test_output_transport_removes_only_runtime_marker(self):
        payload = '{"action":"A","citations":["R1"]}'
        self.assertEqual(response_text(payload + " [end of text]\n\n"), payload)
        self.assertEqual(response_text(payload + " unexpected"), payload + " unexpected")

    def test_release_requires_two_distinct_current_citations(self):
        packet = {
            "R1": (2, "clear", "east"),
            "R2": (2, "clear", "west"),
            "R3": (1, "blocked", "north"),
            "R4": (2, "clear", "east"),
        }
        mapping = legend(0)
        for citations, supported in (
            (["R1", "R2"], True),
            (["R1", "R4"], False),
            (["R1", "R3"], False),
        ):
            with self.subTest(citations=citations):
                result = assess(
                    json.dumps(dict(action="A", citations=citations)), packet, mapping, "proceed"
                )
                self.assertEqual(result["scores"]["supported_correct"], supported)

    def test_conflict_receipts_and_missing_stop_attribution(self):
        packet = {"R1": (2, "clear", "east"), "R2": (2, "blocked", None)}
        both = '{"action":"C","citations":["R1","R2"]}'
        self.assertTrue(assess(both, packet, legend(0), "abstain")["supported"])
        incomplete = assess('{"action":"C","citations":["R1"]}', packet, legend(0), "abstain")
        self.assertEqual(incomplete["error_source"], "evidence_present_misused")
        missing = assess(both, {"R1": packet["R1"]}, legend(0), "stop")
        self.assertEqual(missing["error_source"], "packet_evidence_gap")
        self.assertTrue(missing["scores"]["missed_stop"])

    def test_failed_gate_never_opens_comparison(self):
        def fixed(rows, rotation, expected):
            packet = {f"R{i}": row for i, row in enumerate(rows, 1)}
            return assess('{"action":"A","citations":["R1"]}', packet, legend(rotation), expected)

        with patch(
            "evaluate_shipment_actor.held_out", side_effect=AssertionError("held out opened")
        ):
            result = run(fixed)
        self.assertFalse(result["qualified"])
        self.assertIsNone(result["comparison"])
        self.assertEqual(len(result["qualification"]), 18)
        self.assertEqual({r["rotation"] for r in result["qualification"]}, {0, 1, 2})
