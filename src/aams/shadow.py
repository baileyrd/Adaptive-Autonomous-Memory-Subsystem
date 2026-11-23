"""Inert, scoped contracts for v0.7 shadow retrieval evaluation.

This module deliberately has no recall integration, persistence, or activation API.
"""

from dataclasses import dataclass
from enum import Enum


class ShadowMode(str, Enum):
    DISABLED = "disabled"
    OBSERVE_ONLY = "observe_only"


@dataclass(frozen=True)
class ShadowConfig:
    """Shadow evaluation requires explicit opt-in, never an activation permission."""

    mode: ShadowMode = ShadowMode.DISABLED
    max_observations: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ShadowMode):
            raise ValueError("invalid shadow mode")
        if isinstance(self.max_observations, bool) or not isinstance(self.max_observations, int):
            raise ValueError("max_observations must be an integer")
        if not 0 <= self.max_observations <= 1000:
            raise ValueError("max_observations out of bounds")
        if self.mode == ShadowMode.OBSERVE_ONLY and self.max_observations == 0:
            raise ValueError("enabled shadow requires a bounded observation budget")


@dataclass(frozen=True)
class ShadowIntent:
    """Only opaque identifiers; callers must enforce canonical scope authorization."""

    scope_id: str
    query_id: str
    candidate_version: str

    def __post_init__(self) -> None:
        for value in (self.scope_id, self.query_id, self.candidate_version):
            if not isinstance(value, str) or not 1 <= len(value) <= 128:
                raise ValueError("shadow identifiers must be nonempty bounded strings")
            if any(char.isspace() or ord(char) < 33 for char in value):
                raise ValueError("shadow identifiers must not contain whitespace or controls")


@dataclass(frozen=True)
class ShadowObservation:
    """Non-authoritative measurement. No memory content or serving result is retained."""

    intent: ShadowIntent
    proposed_mode: str
    elapsed_ms: float
    success: bool

    def __post_init__(self) -> None:
        if not isinstance(self.intent, ShadowIntent):
            raise ValueError("invalid shadow intent")
        if self.proposed_mode not in ("lexical", "hybrid"):
            raise ValueError("invalid proposed mode")
        if isinstance(self.elapsed_ms, bool) or not isinstance(self.elapsed_ms, (int, float)):
            raise ValueError("invalid elapsed_ms")
        if not 0 <= self.elapsed_ms <= 60000 or self.elapsed_ms != self.elapsed_ms:
            raise ValueError("elapsed_ms out of bounds")
        if not isinstance(self.success, bool):
            raise ValueError("success must be boolean")


def shadow_allowed(config: ShadowConfig, authorized: bool) -> bool:
    """Fail closed; the caller must supply the actual canonical authorization result."""
    return (
        isinstance(config, ShadowConfig)
        and config.mode == ShadowMode.OBSERVE_ONLY
        and config.max_observations > 0
        and authorized is True
    )
