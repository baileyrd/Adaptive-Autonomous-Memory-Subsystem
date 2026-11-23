"""Deterministic, model-neutral retrieval and provenance packaging."""

import json
from dataclasses import dataclass
from re import findall
from typing import Literal

from .contracts import MemoryKind, require_text, utc_timestamp
from .storage import AccessContext, SQLiteMemoryStore, StoreIntegrityError

Entity = Literal["formation", "belief", "evidence"]
_PREVIEW_BYTES = 512


def _tokens(text: str) -> set[str]:
    return set(findall(r"[^\W_]+", text.casefold()))


def _encoded_size(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode())


def _response(items: list[dict], max_items: int, max_bytes: int) -> dict:
    result = {"items": [], "truncated": len(items) > max_items}
    for item in items[:max_items]:
        result["items"].append(item)
        # False occupies one extra byte, so the check is conservative.
        if _encoded_size(result) > max_bytes:
            result["items"].pop()
            result["truncated"] = True
            break
    return result


@dataclass(frozen=True, slots=True)
class CognitiveNeed:
    query: str = ""
    entity: Entity | None = None
    identifier: str | None = None
    kinds: tuple[MemoryKind, ...] = ()
    recorded_as_of: str | None = None
    effective_at: str | None = None
    max_items: int = 10
    max_depth: int = 1
    max_bytes: int = 16384

    def __post_init__(self) -> None:
        if not isinstance(self.query, str) or len(self.query) > 1024:
            raise ValueError("Query must contain at most 1024 characters")
        if self.identifier is not None:
            require_text(self.identifier)
            if self.entity not in ("formation", "belief", "evidence") or self.query:
                raise ValueError("Exact lookup requires an entity and no query")
        elif self.entity is not None:
            raise ValueError("An entity requires an exact identifier")
        if not isinstance(self.kinds, tuple) or any(
            not isinstance(kind, MemoryKind) for kind in self.kinds
        ):
            raise ValueError("Kinds must be a tuple of formation kinds")
        for value, lower, upper in (
            (self.max_items, 1, 100),
            (self.max_depth, 0, 1),
            (self.max_bytes, 128, 65536),
        ):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError("Invalid item, depth or byte budget")
        for field in ("recorded_as_of", "effective_at"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, utc_timestamp(value))


class CognitiveMemory:
    def __init__(self, store: SQLiteMemoryStore) -> None:
        self.store = store

    def recall(self, access: AccessContext, need: CognitiveNeed) -> dict:
        if need.identifier is not None:
            return self.explain(access, need)
        terms = _tokens(need.query)
        if not terms:
            return _response([], need.max_items, need.max_bytes)
        candidates = self.store.recall_candidates(
            access, recorded_as_of=need.recorded_as_of, effective_at=need.effective_at
        )
        ranked = []
        for entity, identifier in candidates:
            item = self._item(access, need, entity, identifier)
            if item is None:
                continue
            searchable = [identifier, item.get("proposition", ""), item.get("kind", "")]
            for citation in item["citations"]:
                searchable.extend((citation["preview"], citation["source_locator"]))
            matched = sorted(terms.intersection(_tokens(" ".join(searchable))))
            if matched:
                item["relevance"] = {"score": len(matched), "matched_terms": matched}
                ranked.append(item)
        ranked.sort(key=lambda item: (-item["relevance"]["score"], item["entity"], item["id"]))
        if need.max_depth == 0:
            for item in ranked:
                item["citations"] = []
        return _response(ranked, need.max_items, need.max_bytes)

    def explain(self, access: AccessContext, need: CognitiveNeed) -> dict:
        if need.identifier is None or need.entity is None:
            raise ValueError("Explanation requires an exact target")
        item = self._item(access, need, need.entity, need.identifier)
        if item is None:
            return _response([], need.max_items, need.max_bytes)
        if need.max_depth == 0 and need.entity != "evidence":
            item["citations"] = []
        return _response([item], need.max_items, need.max_bytes)

    def _item(self, access: AccessContext, need: CognitiveNeed, entity: str, identifier: str):
        if entity == "evidence":
            if need.kinds:
                return None
            citation = self._citation(access, need, identifier, "original")
            return {"entity": entity, "id": identifier, **citation} if citation else None
        if entity == "formation":
            formation = self.store.get_formation(access, identifier)
            if (
                formation is None
                or (need.kinds and formation.kind not in need.kinds)
                or (need.recorded_as_of and formation.created_at > need.recorded_as_of)
                or (need.effective_at and formation.created_at > need.effective_at)
            ):
                return None
            item = {
                "kind": formation.kind.value,
                "state": formation.epistemic_state.value,
                "producer": formation.producer,
                "recorded_at": formation.created_at,
            }
            links = [("source", formation.evidence_ids)]
        else:
            if need.kinds:
                return None
            revision = self.store.get_belief(
                access,
                identifier,
                recorded_as_of=need.recorded_as_of,
                effective_at=need.effective_at,
            )
            if revision is None:
                return None
            proposal = revision.proposal
            item = {
                "revision_id": revision.revision_id,
                "parent_id": revision.parent_id,
                "recorded_at": revision.recorded_at,
                "valid_from": proposal.valid_from,
                "valid_until": proposal.valid_until,
                "state": proposal.state.value,
                "proposition": proposal.proposition,
                "rationale": proposal.rationale,
                "actor": revision.actor,
            }
            links = [("support", proposal.support_ids), ("refute", proposal.refute_ids)]
        citations = [
            citation
            for role, ids in links
            for evidence_id in ids
            if (citation := self._citation(access, need, evidence_id, role)) is not None
        ]
        return {
            "entity": entity,
            "id": identifier,
            **item,
            "contradictory_evidence": any(c["role"] == "refute" for c in citations),
            "citations": citations,
            "citations_truncated": need.max_depth == 0 and bool(citations),
        }

    def _citation(
        self, access: AccessContext, need: CognitiveNeed, evidence_id: str, role: str
    ) -> dict | None:
        record = self.store.get_evidence(access, evidence_id)
        if record is None:
            if role != "original":
                raise StoreIntegrityError("Canonical evidence link cannot be resolved")
            return None
        if (need.recorded_as_of and record.recorded_at > need.recorded_as_of) or (
            need.effective_at and record.observed_at > need.effective_at
        ):
            return None
        return {
            "evidence_id": evidence_id,
            "role": role,
            "source_actor": record.source_actor,
            "source_locator": record.source_locator,
            "producer": record.producer,
            "digest": record.digest,
            "observed_at": record.observed_at,
            "recorded_at": record.recorded_at,
            "status": record.status.value,
            "preview": record.payload[:_PREVIEW_BYTES].decode("utf-8", errors="replace"),
            "preview_truncated": len(record.payload) > _PREVIEW_BYTES,
        }
