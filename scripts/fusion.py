"""Eval-only dense and reciprocal-rank-fusion arms for #83/#84. Measure-only; not product code.

Both lists are built only from data recall itself would expose: the lexical list is a normal
recall packet, and dense candidates are restricted to the time-visible canonical citations that
recall's own citation path yields. Nothing here re-implements authorization or time filtering.
"""

from collections import defaultdict
from dataclasses import replace
from math import fsum

from aams.recall import CognitiveMemory, CognitiveNeed
from aams.representations import RepresentationProvider
from aams.retrieval_routing import RetrievalMode
from aams.storage import AccessContext
from aams.vector_index import RepresentationIndex

RRF_K = 60
DEPTH = 20
LIST_BYTES = 65536
ONNX_ARMS = ("bm25_guarded_onnx", "onnx", "rrf_onnx")


class InvalidRun(RuntimeError):
    """The experiment cannot produce a valid measurement; never report it as a result."""


def visible_citations(memory: CognitiveMemory, access: AccessContext, need: CognitiveNeed):
    """Evidence ID -> digest for every citation recall would show for this need."""
    eligible: dict[str, str] = {}
    for record, evidence in memory.store.scan_recall(
        access,
        recorded_as_of=need.recorded_as_of,
        effective_at=need.effective_at,
        kinds=need.kinds,
    ):
        for citation in memory._with_citations(need, record, evidence.get)["citations"]:
            eligible[citation["evidence_id"]] = citation["digest"]
    return eligible


def lexical_list(memory: CognitiveMemory, access: AccessContext, need: CognitiveNeed) -> list[str]:
    """Evidence IDs of a depth-20 lexical packet. Fails if the byte cap, not depth, cut it."""
    packet = memory.recall(
        access,
        replace(need, max_items=DEPTH, max_bytes=LIST_BYTES),
        requested_mode=RetrievalMode.LEXICAL,
    )
    if packet["truncated"] and len(packet["items"]) < DEPTH:
        raise InvalidRun("Lexical list shortened by the byte cap")
    cited = (c["evidence_id"] for item in packet["items"] for c in item["citations"])
    return list(dict.fromkeys(cited))


def dense_list(
    memory: CognitiveMemory,
    encoder: RepresentationProvider,
    access: AccessContext,
    need: CognitiveNeed,
) -> tuple[list[tuple[str, float]], str]:
    """(evidence ID, cosine) by descending cosine, ties by ID, over time-visible citations."""
    snapshot = RepresentationIndex(memory.store).snapshot(access, encoder.spec)
    if snapshot.status != "fresh":
        return [], snapshot.status
    eligible = visible_citations(memory, access, need)
    try:
        query = encoder.encode(need.query)
    except Exception as error:  # Any encoder failure voids the run; never a silent fallback.
        raise InvalidRun(f"Encoder failed on a dense query: {error}") from error
    scored = sorted(
        (-fsum(a * b for a, b in zip(query, vector.values)), vector.source_id)
        for vector in snapshot.vectors
        if eligible.get(vector.source_id) == vector.source_digest
    )
    ranked = [(source, -score) for score, source in scored[:DEPTH]]
    return ranked, "fresh" if ranked else "no_match"


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[str]:
    """Reciprocal rank fusion. Ranks start at 1; a missing rank contributes 0; ties by ID."""
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, identifier in enumerate(ranking, start=1):
            scores[identifier] += 1 / (k + rank)
    return sorted(scores, key=lambda identifier: (-scores[identifier], identifier))


def packet(identifiers: list[str], top_k: int, mode: str, status: str) -> dict:
    """Minimal recall-shaped packet so replay measures these arms like every other arm."""
    return {
        "items": [{"citations": [{"evidence_id": i}]} for i in identifiers[:top_k]],
        "retrieval": {"mode": mode, "status": status},
    }


def dense_arm(memory, encoder, access, need, top_k: int) -> dict:
    ranked, status = dense_list(memory, encoder, access, need)
    result = packet([source for source, _ in ranked], top_k, "dense", status)
    result["cosines"] = [[source, round(score, 6)] for source, score in ranked]
    return result


def rrf_arm(memory, encoder, access, need, top_k: int) -> dict:
    dense, status = dense_list(memory, encoder, access, need)
    fused = rrf([lexical_list(memory, access, need), [source for source, _ in dense]])
    return packet(fused, top_k, "fused", status)


def check_validity(rows: list[dict]) -> list[str]:
    """Route-aware allow-list. Any problem invalidates the whole run."""
    problems = []
    for row in rows:
        for arm in ONNX_ARMS:
            measured = row["measurements"].get(arm)
            if measured is None:
                continue
            if arm == "bm25_guarded_onnx" and not row["features"]["opt_in"]:
                valid = (
                    measured["status"] == "default_lexical"
                    and measured["mode"] == "lexical"
                    and measured["encoder_calls"] == 0
                )
            else:
                valid = measured["status"] in ("fresh", "no_match")
            if not valid:
                problems.append(f"{row['task']}:{arm}:{measured['mode']}/{measured['status']}")
    return problems
