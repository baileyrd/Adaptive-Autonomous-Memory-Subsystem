"""Shadow contracts must never grant activation or cross-scope visibility."""

import unittest
from dataclasses import FrozenInstanceError

from aams.shadow import (
    ShadowConfig,
    ShadowIntent,
    ShadowMode,
    ShadowObservation,
    shadow_allowed,
)


class ShadowContractTests(unittest.TestCase):
    def test_shadow_is_disabled_by_default(self):
        self.assertFalse(shadow_allowed(ShadowConfig(), True))
        enabled = ShadowConfig(ShadowMode.OBSERVE_ONLY, 5)
        self.assertFalse(shadow_allowed(enabled, False))
        self.assertTrue(shadow_allowed(enabled, True))
        self.assertFalse(shadow_allowed(enabled, 1))

    def test_invalid_shadow_configuration(self):
        invalid = [
            {"mode": "observe_only", "max_observations": 1},
            {"mode": ShadowMode.OBSERVE_ONLY, "max_observations": 0},
            {"mode": ShadowMode.DISABLED, "max_observations": -1},
            {"mode": ShadowMode.DISABLED, "max_observations": 1001},
            {"mode": ShadowMode.DISABLED, "max_observations": True},
        ]
        for options in invalid:
            with self.subTest(options=options), self.assertRaises(ValueError):
                ShadowConfig(**options)

    def test_bounded_opaque_identifiers_and_immutability(self):
        intent = ShadowIntent("scope1", "query1", "candidate1")
        observation = ShadowObservation(intent, "hybrid", 1.5, True)
        self.assertEqual(observation.intent, intent)
        with self.assertRaises(FrozenInstanceError):
            observation.success = False
        for invalid in ("", "with spaces", "a" * 129, "\n"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                ShadowIntent(invalid, "query", "candidate")

    def test_observation_rejects_invalid_mode_and_measurements(self):
        intent = ShadowIntent("scope", "query", "candidate")
        invalid = [
            ("activate", 1.0, True),
            ("lexical", -1, True),
            ("hybrid", float("nan"), True),
            ("hybrid", 60001, True),
            ("hybrid", True, True),
            ("hybrid", 1.0, 1),
        ]
        for mode, elapsed, success in invalid:
            with self.subTest(mode=mode, elapsed=elapsed), self.assertRaises(ValueError):
                ShadowObservation(intent, mode, elapsed, success)


if __name__ == "__main__":
    unittest.main()
