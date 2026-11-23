"""Model-neutral, disposable representation contracts.

A representation is an index artifact. It cannot assert facts or alter canonical evidence.
The fixture encoder below is deterministic test machinery, NOT a neural model.
"""

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite, sqrt
from typing import Protocol, runtime_checkable

from .contracts import require_text, utc_timestamp


@dataclass(frozen=True, slots=True)
class RepresentationSpec:
    provider_id: str
    model_id: str
    model_version: str
    dimensions: int

    def __post_init__(self) -> None:
        require_text(self.provider_id, self.model_id, self.model_version)
        if type(self.dimensions) is not int or not 1 <= self.dimensions <= 65536:
            raise ValueError("Representation dimensions must be a positive bounded integer")


@dataclass(frozen=True, slots=True)
class DerivedVector:
    source_id: str
    scope: str
    source_digest: str
    generated_at: str
    spec: RepresentationSpec
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        require_text(self.source_id, self.scope)
        if (
            type(self.source_digest) is not str
            or len(self.source_digest) != 71
            or not self.source_digest.startswith("sha256:")
        ):
            raise ValueError("Expected an algorithm-qualified SHA-256 source digest")
        digest_hex = self.source_digest[7:]
        if any(c not in "0123456789abcdef" for c in digest_hex):
            raise ValueError("Expected a lowercase SHA-256 source digest")
        object.__setattr__(self, "generated_at", utc_timestamp(self.generated_at))
        if not isinstance(self.spec, RepresentationSpec):
            raise ValueError("Missing representation specification")
        if type(self.values) is not tuple or len(self.values) != self.spec.dimensions:
            raise ValueError("Vector dimension mismatch")
        if any(type(value) is not float or not isfinite(value) for value in self.values):
            raise ValueError("Vectors must contain only finite float values")


@runtime_checkable
class RepresentationProvider(Protocol):
    """Encoding boundary; no network, authority, or persistence implied."""

    @property
    def spec(self) -> RepresentationSpec: ...

    def encode(self, text: str) -> tuple[float, ...]: ...


class DeterministicFixtureProvider:
    """Test-only byte-bucket representation; NOT semantic or neural."""

    def __init__(self, dimensions: int = 16) -> None:
        self._spec = RepresentationSpec("aams-test", "byte-buckets", "1", dimensions)

    @property
    def spec(self) -> RepresentationSpec:
        return self._spec

    def encode(self, text: str) -> tuple[float, ...]:
        if type(text) is not str:
            raise ValueError("Expected text input")
        counts = [0.0] * self.spec.dimensions
        for byte in text.encode("utf-8"):
            counts[byte % self.spec.dimensions] += 1.0
        norm = sqrt(sum(value * value for value in counts))
        return tuple(value / norm for value in counts) if norm else tuple(counts)


def create_derived_vector(
    provider: RepresentationProvider,
    *,
    source_id: str,
    scope: str,
    source_payload: bytes,
    text: str,
    generated_at: str,
) -> DerivedVector:
    """Validate a provider result while tying it to source bytes and an authorized scope.

    Callers remain responsible for retrieving source bytes through authorized canonical APIs.
    """
    if not isinstance(provider, RepresentationProvider):
        raise ValueError("Expected a representation provider")
    if type(source_payload) is not bytes or type(text) is not str:
        raise ValueError("Source payload and text must be canonical bytes and text")
    values = provider.encode(text)
    return DerivedVector(
        source_id=source_id,
        scope=scope,
        source_digest="sha256:" + sha256(source_payload).hexdigest(),
        generated_at=generated_at,
        spec=provider.spec,
        values=values,
    )
