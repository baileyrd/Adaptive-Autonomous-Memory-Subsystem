"""Deterministic, model-neutral retrieval and provenance packaging."""

import json
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from math import fsum, isfinite, sqrt
from typing import Literal

from .contracts import (
    BeliefRevision,
    Evidence,
    MemoryFormation,
    MemoryKind,
    require_text,
    utc_timestamp,
)
from .ranking import LexicalRanking, bm25_scores, tokens
from .representations import RepresentationProvider, RepresentationSpec
from .retrieval_routing import (
    RetrievalMode,
    RetrievalRoutingRequest,
    choose_retrieval_mode,
)
from .shadow_observer import ShadowObserver
from .storage import AccessContext, SQLiteMemoryStore, StoreIntegrityError
from .vector_index import RepresentationIndex

Entity = Literal["formation", "belief", "evidence"]
_PREVIEW_BYTES = 512
_TERM_CACHE_ENTRIES = 4096


def _tokens(text: str) -> frozenset[str]:
    return frozenset(tokens(text))


def _encoded_size(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode())


def _response(items: list[dict], max_items: int, max_bytes: int, retrieval=None) -> dict:
    result = {"items": [], "truncated": len(items) > max_items}
    if retrieval is not None:
        result["retrieval"] = retrieval
    for item in items[:max_items]:
        result["items"].append(item)
        # False occupies one extra byte, so the check is conservative.
        if _encoded_size(result) > max_bytes:
            result["items"].pop()
            result["truncated"] = True
            break
    return result


def _unit(values: tuple[float, ...], dimensions: int) -> tuple[float, ...]:
    if len(values) != dimensions or any(type(v) is not float or not isfinite(v) for v in values):
        raise ValueError("Invalid query vector")
    peak = max(map(abs, values))
    if peak == 0:
        return ()
    scaled = tuple(value / peak for value in values)
    norm = sqrt(fsum(value * value for value in scaled))
    return tuple(value / norm for value in scaled)


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
    def __init__(
        self,
        store: SQLiteMemoryStore,
        *,
        shadow: ShadowObserver | None = None,
        lexical_ranking: LexicalRanking = LexicalRanking.BM25,
    ) -> None:
        """``lexical_ranking`` is host configuration, never a per-request caller input.

        BM25 is the default since v0.8. ``LexicalRanking.OVERLAP`` keeps the legacy ranker for
        compatibility and rollback.
        """
        if shadow is not None and type(shadow) is not ShadowObserver:
            raise ValueError("Expected a native ShadowObserver")
        if type(lexical_ranking) is not LexicalRanking:
            raise ValueError("Expected a supported lexical ranking")
        self.store = store
        self._shadow = shadow
        self._lexical_ranking = lexical_ranking
        self._term_cache: OrderedDict[tuple[str, str, str], Counter[str]] = OrderedDict()

    def recall(
        self,
        access: AccessContext,
        need: CognitiveNeed,
        *,
        provider: RepresentationProvider | None = None,
        requested_mode: RetrievalMode | None = None,
    ) -> dict:
        self.store.check_current()
        result = self._recall(access, need, provider, requested_mode)
        if self._shadow is not None and need.identifier is None and result["items"]:
            try:
                self._shadow.submit(
                    access,
                    short_query=len(need.query.split()) <= 4,
                    opt_in=requested_mode is RetrievalMode.HYBRID
                    or (requested_mode is None and provider is not None),
                )
            except Exception:
                # Optional observation must never affect an already-authorized response.
                pass
        self.store.check_current()
        return result

    def _recall(self, access, need, provider, requested_mode) -> dict:
        mode = requested_mode
        if mode is None:
            mode = RetrievalMode.HYBRID if provider is not None else RetrievalMode.LEXICAL
        exact = need.identifier is not None
        request = RetrievalRoutingRequest(mode, exact_lookup=exact)
        decision = choose_retrieval_mode(request)
        if exact:
            exact_result = self.explain(access, need)
            if requested_mode is None:
                return exact_result
            exact_result["retrieval"] = self._routing_metadata(decision, decision.reason.value)
            if _encoded_size(exact_result) > need.max_bytes:
                exact_result["items"] = []
                exact_result["truncated"] = True
            return exact_result

        terms = _tokens(need.query)
        scores, status = {}, decision.reason.value
        if terms and mode is RetrievalMode.HYBRID:
            spec, snapshot = self._semantic_snapshot(access, provider)
            decision = choose_retrieval_mode(
                RetrievalRoutingRequest(
                    mode,
                    provider_ready=spec is not None,
                    index_fresh=snapshot is not None and snapshot.status == "fresh",
                )
            )
            status = snapshot.status if snapshot is not None else decision.reason.value
            if decision.mode is RetrievalMode.HYBRID:
                scores, status = self._semantic_scores(need.query, provider, spec, snapshot)
        ranked = self._rank(access, need, terms, scores) if terms else []
        if scores and not any(item["relevance"]["semantic_score"] > 0 for item in ranked):
            ranked = self._rank(access, need, terms, {})
            status = "no_match"
        retrieval = None
        if requested_mode is not None:
            retrieval = self._routing_metadata(decision, status)
        elif terms and provider is not None:
            retrieval = {"mode": "hybrid" if status == "fresh" else "lexical", "status": status}
        return _response(ranked, need.max_items, need.max_bytes, retrieval)

    @staticmethod
    def _routing_metadata(decision, status):
        return {
            "mode": "hybrid"
            if decision.mode is RetrievalMode.HYBRID and status == "fresh"
            else "lexical",
            "status": status,
            "policy": decision.policy_version,
        }

    def _semantic_snapshot(self, access, provider):
        try:
            spec = provider.spec if provider is not None else None
        except Exception:
            return None, None
        if not isinstance(spec, RepresentationSpec):
            return None, None
        return spec, RepresentationIndex(self.store).snapshot(access, spec)

    def _semantic_scores(self, query, provider, spec, snapshot):
        try:
            query_values = _unit(provider.encode(query), spec.dimensions)
            if provider.spec != spec:
                return {}, "incompatible"
        except Exception:
            return {}, "provider_unavailable"
        if not query_values:
            return {}, "no_match"
        scores = {}
        for candidate in snapshot.vectors:
            unit = _unit(candidate.values, spec.dimensions)
            score = min(1.0, fsum(a * b for a, b in zip(query_values, unit)))
            if score >= 0.35:
                scores[candidate.source_id] = (candidate.source_digest, score)
        return scores, "fresh" if scores else "no_match"

    def _rank(self, access, need, terms, scores):
        candidates = self.store.scan_recall(
            access,
            recorded_as_of=need.recorded_as_of,
            effective_at=need.effective_at,
            kinds=need.kinds,
        )
        full_text = self._lexical_ranking is LexicalRanking.BM25
        entries = []
        for record, evidence in candidates:
            item = self._with_citations(need, record, evidence.get)
            searchable = [item["id"], item.get("proposition", ""), item.get("kind", "")]
            payloads = []
            semantic_score, source = 0.0, None
            for citation in item["citations"]:
                source_id = citation["evidence_id"]
                searchable.append(citation["source_locator"])
                if full_text:
                    payloads.append(self._payload_terms(evidence[source_id]))
                else:
                    searchable.append(citation["preview"])
                digest, score = scores.get(source_id, (None, 0.0))
                if digest == citation["digest"] and score > semantic_score:
                    semantic_score, source = score, source_id
            words = Counter(tokens(" ".join(searchable)))
            for terms_of_payload in payloads:
                words.update(terms_of_payload)
            entries.append((item, words, semantic_score, source))
        weights = bm25_scores(terms, [words for _, words, _, _ in entries]) if full_text else ()
        peak = max(weights, default=0.0) or 1.0
        ranked = []
        for position, (item, words, semantic_score, source) in enumerate(entries):
            matched = sorted(terms.intersection(words))
            if not matched and not semantic_score:
                continue
            lexical = weights[position] / peak if full_text else len(matched) / len(terms)
            relevance = {
                "score": round(weights[position], 12) if full_text else len(matched),
                "matched_terms": matched,
            }
            if full_text:
                relevance["ranker"] = LexicalRanking.BM25.value
            if scores:
                relevance.update(
                    score=round((lexical + semantic_score) / 2, 12),
                    lexical_matches=len(matched),
                    semantic_score=round(semantic_score, 12),
                )
                if need.max_depth and source is not None:
                    relevance["semantic_source"] = source
            item["relevance"] = relevance
            if need.max_depth == 0:
                item["citations"] = []
            ranked.append(item)
        ranked.sort(key=lambda item: (-item["relevance"]["score"], item["entity"], item["id"]))
        return ranked

    def _payload_terms(self, record: Evidence) -> Counter[str]:
        """Token counts of immutable evidence, cached by identity and content digest.

        Only records already returned by an authorized scan reach this cache, so it never
        widens what a request can read. The bound keeps memory use fixed.
        """
        key = (record.scope, record.evidence_id, record.digest)
        cached = self._term_cache.get(key)
        if cached is not None:
            self._term_cache.move_to_end(key)
            return cached
        cached = Counter(tokens(record.payload.decode("utf-8", errors="replace")))
        self._term_cache[key] = cached
        if len(self._term_cache) > _TERM_CACHE_ENTRIES:
            self._term_cache.popitem(last=False)
        return cached

    def explain(self, access: AccessContext, need: CognitiveNeed) -> dict:
        self.store.check_current()
        if need.identifier is None or need.entity is None:
            raise ValueError("Explanation requires an exact target")
        item = self._item(access, need, need.entity, need.identifier)
        self.store.check_current()
        if item is None:
            return _response([], need.max_items, need.max_bytes)
        if need.max_depth == 0 and need.entity != "evidence":
            item["citations"] = []
        return _response([item], need.max_items, need.max_bytes)

    def _item(self, access: AccessContext, need: CognitiveNeed, entity: str, identifier: str):
        if entity == "evidence":
            if need.kinds:
                return None
            evidence = self.store.get_evidence(access, identifier)
            citation = self._citation(need, evidence, "original")
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
            record = formation
        else:
            if need.kinds:
                return None
            record = self.store.get_belief(
                access,
                identifier,
                recorded_as_of=need.recorded_as_of,
                effective_at=need.effective_at,
            )
            if record is None:
                return None
        return self._with_citations(
            need, record, lambda evidence_id: self.store.get_evidence(access, evidence_id)
        )

    def _with_citations(
        self,
        need: CognitiveNeed,
        record: MemoryFormation | BeliefRevision,
        load_evidence: Callable[[str], Evidence | None],
    ) -> dict:
        if isinstance(record, MemoryFormation):
            entity, identifier = "formation", record.formation_id
            item = {
                "kind": record.kind.value,
                "state": record.epistemic_state.value,
                "producer": record.producer,
                "recorded_at": record.created_at,
            }
            links = [("source", record.evidence_ids)]
        else:
            entity, identifier = "belief", record.belief_id
            proposal = record.proposal
            item = {
                "revision_id": record.revision_id,
                "parent_id": record.parent_id,
                "recorded_at": record.recorded_at,
                "valid_from": proposal.valid_from,
                "valid_until": proposal.valid_until,
                "state": proposal.state.value,
                "proposition": proposal.proposition,
                "rationale": proposal.rationale,
                "actor": record.actor,
            }
            links = [("support", proposal.support_ids), ("refute", proposal.refute_ids)]
        citations = [
            citation
            for role, ids in links
            for evidence_id in ids
            if (citation := self._citation(need, load_evidence(evidence_id), role)) is not None
        ]
        return {
            "entity": entity,
            "id": identifier,
            **item,
            "contradictory_evidence": any(c["role"] == "refute" for c in citations),
            "citations": citations,
            "citations_truncated": need.max_depth == 0 and bool(citations),
        }

    @staticmethod
    def _citation(need: CognitiveNeed, record: Evidence | None, role: str) -> dict | None:
        if record is None:
            if role != "original":
                raise StoreIntegrityError("Canonical evidence link cannot be resolved")
            return None
        if (need.recorded_as_of and record.recorded_at > need.recorded_as_of) or (
            need.effective_at and record.observed_at > need.effective_at
        ):
            return None
        return {
            "evidence_id": record.evidence_id,
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
