"""Compare lexical, fixture and optional pretrained local neural recall."""

import argparse
import json
import platform
import resource
import statistics
import tempfile
from hashlib import sha256
from math import ceil, log2
from pathlib import Path
from time import perf_counter_ns, process_time_ns

from aams.contracts import EpistemicState, Evidence, EvidenceStatus, MemoryFormation, MemoryKind
from aams.recall import CognitiveMemory, CognitiveNeed
from aams.representations import DeterministicFixtureProvider, RepresentationSpec
from aams.storage import AccessContext, SQLiteMemoryStore
from aams.vector_index import RepresentationIndex

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/semantic_recall.json"
ACCESS = AccessContext("evaluator", "lab", True)
K = 3


class SpacyTok2Vec:
    """Optional pretrained CPU encoder with mean pooling of contextual token vectors."""

    def __init__(self):
        import spacy

        spacy.require_cpu()
        self.nlp = spacy.load(
            "en_core_web_sm", exclude=["tagger", "parser", "attribute_ruler", "lemmatizer", "ner"]
        )
        if spacy.__version__ != "3.8.11" or self.nlp.meta["version"] != "3.8.0":
            raise ValueError("Install spaCy 3.8.11 and en_core_web_sm 3.8.0")
        self.spec = RepresentationSpec("spacy", "en_core_web_sm-tok2vec-mean", "3.8.0", 96)

    def encode(self, text):
        tensor = self.nlp(text).tensor
        if len(tensor) == 0:
            return (0.0,) * self.spec.dimensions
        return tuple(float(value) for value in tensor.mean(axis=0))


def timestamp(day):
    return f"2026-01-{day:02d}T00:00:00Z"


def seed(store, identifier, scope, day, text, *, origin=None):
    access = AccessContext("collector", scope, True)
    payload = text.encode()
    source = origin or ("a07" if identifier == "a09" else identifier)
    evidence = Evidence(
        identifier,
        scope,
        "station-" + source,
        "fixture:" + source,
        access.principal,
        timestamp(day),
        timestamp(day),
        EvidenceStatus.RECORDED,
        payload,
        "sha256:" + sha256(payload).hexdigest(),
    )
    formation = MemoryFormation(
        "f-" + identifier,
        scope,
        MemoryKind.EXPERIENCE,
        (identifier,),
        access.principal,
        timestamp(day),
        EpistemicState.OBSERVED,
    )
    store.ingest(access, identifier, formation, (evidence,))


def assess(queries, packets):
    recalls, ndcg = [], []
    complete = tasks = both = contradictions = scope_errors = time_errors = fallbacks = 0
    outcomes = []
    for query, packet in zip(queries, packets, strict=True):
        ids = [item["citations"][0]["evidence_id"] for item in packet["items"]]
        scope_errors += sum(value.startswith("p") for value in ids)
        time_errors += len(set(ids).intersection(query.get("forbidden", [])))
        fallbacks += packet.get("retrieval", {}).get("mode") == "lexical"
        relevant = query["relevant"]
        if relevant:
            recalls.append(len(set(ids).intersection(relevant)) / len(relevant))
            gains = [relevant.get(value, 0) for value in ids]
            ideal = sorted(relevant.values(), reverse=True)[:K]

            def dcg(scores):
                return sum((2**score - 1) / log2(rank + 2) for rank, score in enumerate(scores))

            ndcg.append(dcg(gains) / dcg(ideal))
        task = set(query["task"])
        if task:
            tasks += 1
            complete += task <= set(ids)
        if query.get("contradiction"):
            contradictions += 1
            both += task <= set(ids)
        outcomes.append({"query": query["text"], "ids": ids})
    return {
        "recall_at_3": round(statistics.mean(recalls), 4),
        "ndcg_at_3": round(statistics.mean(ndcg), 4),
        "tasks_complete": complete,
        "tasks": tasks,
        "contradictions_retained": both,
        "contradiction_tasks": contradictions,
        "cross_scope_disclosures": scope_errors,
        "historical_disclosures": time_errors,
        "hybrid_fallbacks": fallbacks,
        "outcomes": outcomes,
    }


def evaluate(path, mode, repetitions):
    fixture = json.loads(FIXTURE.read_text())
    store = SQLiteMemoryStore(path)
    for row in fixture["evidence"]:
        seed(store, *row)
    db_size = path.stat().st_size
    providers = {"fixture": DeterministicFixtureProvider, "neural": SpacyTok2Vec}
    provider = providers[mode]() if mode in providers else None
    index_ms, vectors = 0.0, 0
    if provider is not None:
        start = perf_counter_ns()
        snapshot = RepresentationIndex(store).rebuild(ACCESS, provider)
        index_ms = (perf_counter_ns() - start) / 1e6
        if snapshot.status != "fresh":
            raise RuntimeError("Expected a fresh batch")
        vectors = len(snapshot.vectors)
    index_bytes = path.stat().st_size - db_size
    engine = CognitiveMemory(store)
    needs = [
        CognitiveNeed(
            query=item["text"],
            max_items=K,
            recorded_as_of=timestamp(item["day"]) if "day" in item else None,
        )
        for item in fixture["queries"]
    ]

    def recall(need):
        return engine.recall(ACCESS, need, provider=provider)

    reference = [recall(need) for need in needs]
    wall, cpu = [], []
    for _ in range(repetitions):
        for need, expected in zip(needs, reference, strict=True):
            start, start_cpu = perf_counter_ns(), process_time_ns()
            result = recall(need)
            cpu.append((process_time_ns() - start_cpu) / 1e6)
            wall.append((perf_counter_ns() - start) / 1e6)
            if result != expected:
                raise RuntimeError("Nondeterministic fixture result")
    stale_fallback = None
    if provider is not None:
        seed(store, "extra", "lab", 3, "New post-index evidence.")
        stale_fallback = recall(needs[0])["retrieval"]["status"]
    return {
        "mode": mode,
        "environment": platform.platform(),
        "python": platform.python_version(),
        "provider": repr(provider.spec) if provider else None,
        "records": len(fixture["evidence"]),
        "timed_queries": len(wall),
        "median_ms": round(statistics.median(wall), 3),
        "p95_ms": round(sorted(wall)[ceil(0.95 * len(wall)) - 1], 3),
        "median_cpu_ms": round(statistics.median(cpu), 3),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "index_bytes": index_bytes,
        "index_build_ms": round(index_ms, 3),
        "vectors": vectors,
        "stale_fallback": stale_fallback,
        **assess(fixture["queries"], reference),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("lexical", "fixture", "neural"))
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("Use at least one repetition")
    with tempfile.TemporaryDirectory(prefix="aams-semantic-") as directory:
        result = evaluate(Path(directory) / "memory.db", args.mode, args.repetitions)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
