"""Low-overlap, cross-domain retrieval check on SciFact (v0.8 follow-up to #79).

Expert-written scientific claims are matched to biomedical abstracts. Unlike SQuAD, the claims
were not written while reading their evidence. The corpus is split into hash shards, and each
shard becomes one scope. Claims whose evidence spans shards are excluded and counted. The
tarball is read in place after checksum verification, with no extraction.
"""

import argparse
import json
import resource
import tarfile
from hashlib import sha256
from pathlib import Path

from evaluate_retrieval import DAY, PREVIEW_BYTES, evaluate_groups, load_encoder, run_valid

from aams.ranking import LexicalRanking

SCIFACT_SHA256 = "11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be"
CLAIM_FILES = ("data/claims_train.jsonl", "data/claims_dev.jsonl")


def shard_of(doc_id: int, shards: int) -> int:
    return int(sha256(str(doc_id).encode()).hexdigest(), 16) % shards


def read_jsonl(archive: tarfile.TarFile, name: str) -> list[dict]:
    member = archive.extractfile(name)
    if member is None:
        raise ValueError(f"Missing {name}")
    return [json.loads(line) for line in member.read().splitlines() if line.strip()]


def scifact_groups(
    corpus: list[dict], claims: list[dict], shards: int
) -> tuple[list[dict], list[dict], int]:
    """Return replay groups, aligned task details and the number of excluded claims."""
    texts, offsets = {}, {}
    for doc in corpus:
        sentences = [doc["title"], *doc["abstract"]]
        texts[doc["doc_id"]] = "\n".join(sentences)
        offsets[doc["doc_id"]] = [
            len("\n".join(sentences[: index + 1]).encode()) + 1
            for index in range(len(doc["abstract"]))
        ]
    tasks: dict[int, list[tuple[dict, dict]]] = {shard: [] for shard in range(shards)}
    excluded = 0
    for claim in claims:
        evidence = {int(key): value for key, value in claim["evidence"].items()}
        homes = {shard_of(doc_id, shards) for doc_id in evidence}
        if not evidence or len(homes) != 1 or any(doc_id not in texts for doc_id in evidence):
            excluded += bool(evidence)
            continue
        first = min(
            offsets[doc_id][sentence]
            for doc_id, entries in evidence.items()
            for entry in entries
            for sentence in entry["sentences"]
        )
        ids = [f"doc-{doc_id}" for doc_id in sorted(evidence)]
        task = {
            "query": claim["claim"],
            "day": DAY,
            "opt_in": True,
            "relevant": ids,
            "required": ids,
            "contradiction": False,
        }
        tasks[homes.pop()].append((task, {"answer_beyond_preview": first >= PREVIEW_BYTES}))
    groups, details = [], []
    for shard, entries in tasks.items():
        if not entries:
            continue
        scope = f"shard-{shard}"
        records = [
            [f"doc-{doc_id}", scope, DAY, text, f"doc-{doc_id}"]
            for doc_id, text in sorted(texts.items())
            if shard_of(doc_id, shards) == shard
        ]
        decoy = entries[0][0]["query"]
        records += [
            [f"private-{shard}", f"private-{scope}", DAY, decoy, f"private-{shard}"],
            [f"future-{shard}", scope, DAY + 1, decoy, f"future-{shard}"],
        ]
        groups.append(
            {
                "domain": scope,
                "split": "heldout",
                "days": [DAY, DAY + 1],
                "records": records,
                "tasks": [task for task, _ in entries],
            }
        )
        details += [{"article": scope, "split": "heldout", **detail} for _, detail in entries]
    return groups, details, excluded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scifact", type=Path, required=True, help="SciFact data.tar.gz")
    parser.add_argument("--expected-sha256", default=SCIFACT_SHA256)
    parser.add_argument("--shards", type=int, default=16)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--encoder-dir", type=Path, help="Pinned ONNX encoder (adds ONNX arms)")
    args = parser.parse_args()
    if not 2 <= args.shards <= 256 or not 1 <= args.repetitions <= 20:
        parser.error("Use 2 to 256 shards and 1 to 20 repetitions")
    encoder = load_encoder(parser, args.encoder_dir, (LexicalRanking.BM25,))
    digest = sha256(args.scifact.read_bytes()).hexdigest()
    if digest != args.expected_sha256:
        parser.error("Dataset checksum mismatch")
    with tarfile.open(args.scifact) as archive:
        corpus = read_jsonl(archive, "data/corpus.jsonl")
        claims = [claim for name in CLAIM_FILES for claim in read_jsonl(archive, name)]
    groups, details, excluded = scifact_groups(corpus, claims, args.shards)
    result = {
        "workload": "scifact_sharded",
        "dataset_sha256": digest,
        "shards": args.shards,
        "excluded_cross_shard_claims": excluded,
        **run_valid(
            lambda: evaluate_groups(
                groups, details, args.repetitions, (LexicalRanking.BM25,), encoder=encoder
            )
        ),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
