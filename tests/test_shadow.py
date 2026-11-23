"""Shadow contracts must never grant activation or cross-scope visibility."""

import pytest

from aams.shadow import (
    ShadowConfig,
    ShadowIntent,
    ShadowMode,
    ShadowObservation,
    shadow_allowed,
)


def test_shadow_is_disabled_by_default():
    assert not shadow_allowed(ShadowConfig(), True)
    assert not shadow_allowed(ShadowConfig(ShadowMode.OBSERVE_ONLY, 5), False)
    assert shadow_allowed(ShadowConfig(ShadowMode.OBSERVE_ONLY, 5), True)
    assert not shadow_allowed(ShadowConfig(ShadowMode.OBSERVE_ONLY, 5), 1)


@pytest.mark.parametrize(
    "config",
    [
        {"mode": "observe_only", "max_observations": 1},
        {"mode": ShadowMode.OBSERVE_ONLY, "max_observations": 0},
        {"mode": ShadowMode.DISABLED, "max_observations": -1},
        {"mode": ShadowMode.DISABLED, "max_observations": 1001},
        {"mode": ShadowMode.DISABLED, "max_observations": True},
    ],
)
def test_invalid_shadow_configuration(config):
    with pytest.raises(ValueError):
        ShadowConfig(**config)


def test_bounded_opaque_identifiers_and_immutability():
    intent = ShadowIntent("scope1", "query1", "candidate1")
    observation = ShadowObservation(intent, "hybrid", 1.5, True)
    assert observation.intent == intent
    with pytest.raises(AttributeError):
        observation.success = False
    for invalid in ("", "with spaces", "a" * 129, "\\n"):
        with pytest.raises(ValueError):
            ShadowIntent(invalid, "query", "candidate")


def test_observation_rejects_invalid_mode_and_measurements():
    intent = ShadowIntent("scope", "query", "candidate")
    for mode, elapsed, success in [
        ("activate", 1.0, True),
        ("lexical", -1, True),
        ("hybrid", float("nan"), True),
        ("hybrid", 60001, True),
        ("hybrid", True, True),
        ("hybrid", 1.0, 1),
    ]:
        with pytest.raises(ValueError):
            ShadowObservation(intent, mode, elapsed, success)
