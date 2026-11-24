"""Eval-only dense, reciprocal-rank-fusion and rerank arms (#83/#84, #105). Not product code.

Both lists are built only from data recall itself would expose: the lexical list is a normal
recall packet, and dense candidates are restricted to the time-visible canonical citations that
recall's own citation path yields. Nothing here re-implements authorization or time filtering.
"""

import struct
from collections import defaultdict
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from math import fsum
from pathlib import Path

from aams.recall import CognitiveMemory, CognitiveNeed
from aams.representations import RepresentationProvider
from aams.retrieval_routing import RetrievalMode
from aams.storage import AccessContext
from aams.vector_index import _WHERE, RepresentationIndex, _count

RRF_K = 60
DEPTH = 20
LIST_BYTES = 65536
# Historical names: the arms take any pinned encoder, ONNX or static, named by its spec.
ONNX_ARMS = ("bm25_guarded_onnx", "onnx", "rrf_onnx", "bm25_rerank", "bm25_fusion")
SEMANTIC_FLOOR = 0.35  # Mirrors recall's hybrid threshold.


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


def lexical_scored(
    memory: CognitiveMemory, access: AccessContext, need: CognitiveNeed
) -> dict[str, tuple[str, float]]:
    """Evidence ID -> (digest, lexical score) of the first 20 citations of recall's own lexical
    ranking. The score is the best BM25 score of any item citing that evidence.

    Records with no time-visible citation (a backdated formation citing later evidence) cannot
    take list slots: the packet deepens until it holds 20 cited IDs or recall has no more.
    Fails if the byte cap, not depth, cut a packet.
    """
    items = DEPTH
    while True:
        packet = memory.recall(
            access,
            replace(need, max_items=items, max_bytes=LIST_BYTES),
            requested_mode=RetrievalMode.LEXICAL,
        )
        if packet["truncated"] and len(packet["items"]) < items:
            raise InvalidRun("Lexical list shortened by the byte cap")
        cited: dict[str, tuple[str, float]] = {}
        for item in packet["items"]:
            score = float(item["relevance"]["score"])
            for citation in item["citations"]:
                cited.setdefault(citation["evidence_id"], (citation["digest"], score))
        if len(cited) >= DEPTH or not packet["truncated"]:
            return dict(list(cited.items())[:DEPTH])
        items *= 2


def lexical_cited(
    memory: CognitiveMemory, access: AccessContext, need: CognitiveNeed
) -> dict[str, str]:
    """Evidence ID -> digest of the first 20 citations of recall's own lexical ranking."""
    return {key: digest for key, (digest, _) in lexical_scored(memory, access, need).items()}


def lexical_list(memory: CognitiveMemory, access: AccessContext, need: CognitiveNeed) -> list[str]:
    """The first 20 cited evidence IDs of recall's own lexical ranking."""
    return list(lexical_cited(memory, access, need))


def open_encoder(directory: Path) -> RepresentationProvider:
    """Load and probe the pinned encoder; any failure is an invalid run, never a traceback.

    A directory holding a static manifest opens the stdlib static encoder; any other opens
    the pinned ONNX export.
    """
    from onnx_encoder import OnnxSentenceEncoder, probe
    from static_encoder import MANIFEST, StaticEmbeddingEncoder

    try:
        static = (directory / MANIFEST).exists()
        encoder = StaticEmbeddingEncoder(directory) if static else OnnxSentenceEncoder(directory)
        probe(encoder)
    except Exception as error:
        raise InvalidRun(f"Encoder failed to load or probe: {error}") from error
    return encoder


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


def cited_vectors(
    memory: CognitiveMemory, access: AccessContext, spec, cited: dict[str, str]
) -> tuple[dict[str, tuple[float, ...]], str]:
    """Stored vectors of the cited evidence only, with the index freshness rules of `snapshot`.

    Reads one scope's rows for the given IDs instead of the whole index. A vector counts only
    if its checksum holds and its digest equals the digest recall cited.
    """
    key = (access.scope, spec.provider_id, spec.model_id, spec.model_version, spec.dimensions)
    with closing(memory.store._connect()) as db, db:
        db.execute("BEGIN")
        batch = db.execute(
            "SELECT evidence_count FROM representation_batch WHERE " + _WHERE, key
        ).fetchone()
        if batch is None:
            return {}, "missing"
        if batch[0] != _count(db, access.scope):
            return {}, "stale"
        marks = ",".join("?" * len(cited))
        rows = db.execute(
            "SELECT evidence_id, digest, values_blob, checksum FROM representation_vector "
            f"WHERE {_WHERE} AND evidence_id IN ({marks})",
            (*key, *cited),
        ).fetchall()
    vectors = {}
    for evidence_id, digest, blob, checksum in rows:
        if sha256(blob).hexdigest() != checksum or digest != cited[evidence_id]:
            return {}, "corrupt"
        vectors[evidence_id] = struct.unpack(f"<{spec.dimensions}d", blob)
    return vectors, "fresh"


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


def rerank_arm(memory, encoder, access, need, top_k: int) -> dict:
    """BM25 guarded's top 20 citations, reordered by RRF of lexical and cosine rank.

    Only the query is encoded at serve time; candidate vectors come from the scope's index.
    Candidates without a vector keep their lexical credit. An all-zero query vector (no known
    token) leaves the lexical order unchanged and reports `no_match`.
    """
    cited = lexical_cited(memory, access, need)
    if not cited:
        return packet([], top_k, "fused", "no_match")
    vectors, status = cited_vectors(memory, access, encoder.spec, cited)
    if status != "fresh":
        return packet(list(cited), top_k, "fused", status)
    try:
        query = encoder.encode(need.query)
    except Exception as error:  # Any encoder failure voids the run; never a silent fallback.
        raise InvalidRun(f"Encoder failed on a rerank query: {error}") from error
    if not any(query):
        return packet(list(cited), top_k, "fused", "no_match")
    dense = sorted(vectors, key=lambda i: (-fsum(a * b for a, b in zip(query, vectors[i])), i))
    return packet(rrf([list(cited), dense]), top_k, "fused", "fresh")


def fusion_arm(memory, encoder, access, need, top_k: int) -> dict:
    """BM25 guarded's top 20 citations, reordered by recall's hybrid score rule.

    Score = (BM25 / list peak + cosine if >= 0.35 else 0) / 2, ties by ID. This is the
    `bm25_guarded_onnx` fusion restricted to the lexical candidates, so only their stored
    vectors are read and only the query is encoded. An all-zero query vector keeps the
    lexical order and reports `no_match`.
    """
    scored = lexical_scored(memory, access, need)
    if not scored:
        return packet([], top_k, "fused", "no_match")
    cited = {key: digest for key, (digest, _) in scored.items()}
    vectors, status = cited_vectors(memory, access, encoder.spec, cited)
    if status != "fresh":
        return packet(list(cited), top_k, "fused", status)
    try:
        query = encoder.encode(need.query)
    except Exception as error:  # Any encoder failure voids the run; never a silent fallback.
        raise InvalidRun(f"Encoder failed on a fusion query: {error}") from error
    if not any(query):
        return packet(list(cited), top_k, "fused", "no_match")
    peak = max(score for _, score in scored.values()) or 1.0

    def fused(key: str) -> float:
        vector = vectors.get(key)
        cosine = fsum(a * b for a, b in zip(query, vector)) if vector else 0.0
        return (scored[key][1] / peak + (cosine if cosine >= SEMANTIC_FLOOR else 0.0)) / 2

    ranked = sorted(cited, key=lambda key: (-fused(key), key))
    return packet(ranked, top_k, "fused", "fresh")


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
