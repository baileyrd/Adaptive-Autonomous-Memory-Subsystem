"""Peak RSS for one phase of one arm, in a fresh process (#84 memory gate). Eval-only.

Run four times with `python -I`, once per arm and phase, each with its own `--db`:
`build` ingests the workload and builds the arm's representation index, and `serve` reopens
that database and answers every task once through `bm25_guarded` recall. The baseline uses
the fixture provider and never imports onnxruntime. Prints `{"peak_rss_kib": ...}`.
"""

import argparse
import json
import resource
import sys
import tarfile
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `python -I` drops the script dir.

from evaluate_retrieval import SQUAD_SHA256, squad_groups  # noqa: E402
from evaluate_scifact import CLAIM_FILES, SCIFACT_SHA256, read_jsonl, scifact_groups  # noqa: E402
from evaluate_semantic import seed, timestamp  # noqa: E402

from aams.ranking import LexicalRanking  # noqa: E402
from aams.recall import CognitiveMemory, CognitiveNeed  # noqa: E402
from aams.representations import DeterministicFixtureProvider, RepresentationProvider  # noqa: E402
from aams.retrieval_routing import RetrievalMode  # noqa: E402
from aams.storage import AccessContext, SQLiteMemoryStore  # noqa: E402
from aams.vector_index import RepresentationIndex  # noqa: E402

CHECKSUMS = {"squad": SQUAD_SHA256, "scifact": SCIFACT_SHA256}
TOP_K = 3


def load_groups(workload: str, raw: bytes, path: Path, max_articles: int | None) -> list[dict]:
    if workload == "squad":
        data = json.loads(raw)
        data["data"] = data["data"][:max_articles]
        return squad_groups(data, 5)[0]
    with tarfile.open(path) as archive:
        corpus = read_jsonl(archive, "data/corpus.jsonl")
        claims = [claim for name in CLAIM_FILES for claim in read_jsonl(archive, name)]
    return scifact_groups(corpus, claims, 16)[0]


def provider_for(arm: str, encoder_dir: Path | None) -> RepresentationProvider:
    if arm == "baseline":
        return DeterministicFixtureProvider()
    from onnx_encoder import OnnxSentenceEncoder, probe

    encoder = OnnxSentenceEncoder(encoder_dir)
    probe(encoder)
    return encoder


def build(store: SQLiteMemoryStore, groups: list[dict], provider: RepresentationProvider) -> None:
    index = RepresentationIndex(store)
    for group in groups:
        for identifier, scope, day, text, origin in group["records"]:
            seed(store, identifier, scope, day, text, origin=origin)
        built = index.rebuild(AccessContext("fixture", group["domain"], True), provider)
        if built.status != "fresh":
            raise RuntimeError(f"Index rebuild returned {built.status}")


def serve(store: SQLiteMemoryStore, groups: list[dict], provider: RepresentationProvider) -> None:
    memory = CognitiveMemory(store, lexical_ranking=LexicalRanking.BM25)
    for group in groups:
        access = AccessContext("fixture", group["domain"])
        for task in group["tasks"]:
            need = CognitiveNeed(
                task["query"], max_items=TOP_K, recorded_as_of=timestamp(task["day"])
            )
            opt_in = task["opt_in"]
            memory.recall(
                access,
                need,
                provider=provider if opt_in else None,
                requested_mode=RetrievalMode.HYBRID if opt_in else RetrievalMode.LEXICAL,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", choices=tuple(CHECKSUMS), required=True)
    parser.add_argument("--arm", choices=("baseline", "candidate"), required=True)
    parser.add_argument("--phase", choices=("build", "serve"), required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True, help="SQuAD JSON or SciFact tarball")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--max-articles", type=int, help="SQuAD only: first N articles")
    parser.add_argument("--encoder-dir", type=Path, help="Pinned ONNX encoder (candidate)")
    args = parser.parse_args()
    if (args.arm == "candidate") != (args.encoder_dir is not None):
        parser.error("--encoder-dir is required for, and only for, the candidate arm")
    if (args.phase == "build") == args.db.exists():
        parser.error("build needs a new --db; serve needs the database its build made")
    raw = args.data.read_bytes()
    if sha256(raw).hexdigest() != (args.expected_sha256 or CHECKSUMS[args.workload]):
        parser.error("Dataset checksum mismatch")
    groups = load_groups(args.workload, raw, args.data, args.max_articles)
    del raw
    provider = provider_for(args.arm, args.encoder_dir)
    phase = build if args.phase == "build" else serve
    phase(SQLiteMemoryStore(args.db), groups, provider)
    print(json.dumps({"peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))


if __name__ == "__main__":
    main()
