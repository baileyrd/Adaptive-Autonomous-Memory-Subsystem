"""Run the bounded #109 retrieval comparison using the existing offline replay."""

import argparse
import json
import platform
import random
import resource
import statistics
import subprocess
import tarfile
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from evaluate_retrieval import squad_groups
from evaluate_scifact import CLAIM_FILES, SCIFACT_SHA256, read_jsonl, scifact_groups, shard_of
from evaluate_semantic import timestamp
from fusion import ONNX_ARMS, InvalidRun, check_validity, open_encoder
from offline_experiment import replay
from onnx_encoder import OnnxSentenceEncoder, Variant, file_sha256, probe
from static_encoder import load_manifest

from aams.ranking import LexicalRanking

ROOT = Path(__file__).resolve().parent
VARIANTS = json.loads((ROOT / "onnx_variant_pins.json").read_text())
STATIC = json.loads((ROOT / "static_embedder_pins.json").read_text())
CANDIDATES = ("bge-float", *VARIANTS, *STATIC)
ARMS = ("bm25", "bm25_guarded", *ONNX_ARMS)
SQUAD = {
    "dev": ("95aa6a52d5d6a735563366753ca50492a658031da74f301ac5238b03966972c9", 0),
    "train": ("3527663986b8295af4f7fcdff1ba1ff3f72d07d61a20f487cb238a6ef92fd955", 48),
}


def verified(path, digest):
    if file_sha256(path) != digest:
        raise InvalidRun(f"Corpus checksum mismatch: {path.name}")
    return path


def groups_for(workload, dataset):
    if workload in SQUAD:
        digest, first = SQUAD[workload]
        data = json.loads(verified(dataset, digest).read_bytes())
        # Pass the full prefix to preserve the original article/source IDs.
        groups, _ = squad_groups({"data": data["data"][: first + 12]}, 1)
        groups = groups[first:]
        for group in groups:
            group["tasks"] = group["tasks"][:10]
        return groups, digest
    if workload == "scifact":
        with tarfile.open(verified(dataset, SCIFACT_SHA256)) as archive:
            corpus = read_jsonl(archive, "data/corpus.jsonl")
            claims = [claim for name in CLAIM_FILES for claim in read_jsonl(archive, name)]
        claims.sort(key=lambda claim: claim["id"])
        documents = {doc["doc_id"] for doc in corpus}
        eligible = []
        for claim in claims:
            sources = {int(key) for key in claim["evidence"]}
            if sources <= documents and len({shard_of(key, 16) for key in sources}) == 1:
                eligible.append(claim)
        groups, _, _ = scifact_groups(corpus, eligible[:128], 16)
        return groups, SCIFACT_SHA256
    groups = json.loads((ROOT / "heldout_evidence_cases.json").read_bytes())
    return groups, file_sha256(ROOT / "heldout_evidence_cases.json")


def opened(candidate, directory):
    if candidate in VARIANTS:
        recipe = VARIANTS[candidate]
        encoder = OnnxSentenceEncoder(directory, variant=Variant(**recipe))
        probe(encoder)
        return encoder, recipe
    if candidate in STATIC:
        recipe = STATIC[candidate]
        manifest = load_manifest(directory)
        if (manifest.model, manifest.revision) != (recipe["model"], recipe["revision"]):
            raise InvalidRun("Static table does not match the selected model pin")
        return open_encoder(directory), {**recipe, "converted_files": manifest.files}
    encoder = OnnxSentenceEncoder(directory)
    probe(encoder)
    return encoder, json.loads((ROOT / "onnx_pins.json").read_text())


def audit_packet(packet, visible):
    found = []
    for item in packet["items"]:
        for citation in item["citations"]:
            identifier = citation["evidence_id"]
            if identifier not in visible:
                raise InvalidRun(f"Out-of-scope, future, or unknown citation: {identifier}")
            expected = visible[identifier]
            if any(key in citation and citation[key] != value for key, value in expected.items()):
                raise InvalidRun(f"Citation provenance mismatch: {identifier}")
            if len(citation) > 1 and not expected.keys() <= citation.keys():
                raise InvalidRun(f"Incomplete native provenance: {identifier}")
            found.append(identifier)
    return found


def interval(pairs):
    """Paired 95% percentile interval, resampling whole groups with equal probability."""
    by_group = {}
    for row in pairs:
        slot = by_group.setdefault(row["group"], [0, 0])
        slot[0] += int(row["win"]) - int(row["loss"])
        slot[1] += 1
    groups = list(by_group.values())
    if len(groups) < 2:
        return None
    rng = random.Random(0)
    values = []
    for _ in range(2000):
        selected = rng.choices(groups, k=len(groups))
        values.append(sum(i[0] for i in selected) / sum(i[1] for i in selected))
    values.sort()
    return [values[49], values[1949]]


def compare(rows, packets, arm, baseline):
    pairs = []
    for row, observed in zip(rows, packets, strict=True):
        required = set(observed["required"])
        candidate = required.intersection(observed[arm])
        control = required.intersection(observed[baseline])
        pairs.append(
            {
                "group": row["group"],
                "task": observed["task"],
                "win": candidate == required and control != required,
                "loss": control == required and candidate != required,
                "recovered_ids": sorted(candidate - control),
                "lost_ids": sorted(control - candidate),
            }
        )
    wins = sum(p["win"] for p in pairs)
    losses = sum(p["loss"] for p in pairs)
    return {
        "queries": len(pairs),
        "groups": len({p["group"] for p in pairs}),
        "wins": wins,
        "losses": losses,
        "unchanged": len(pairs) - wins - losses,
        "delta": (wins - losses) / len(pairs),
        "grouped_95_interval": interval(pairs),
        "queries_with_recovered_required_ids": sum(bool(p["recovered_ids"]) for p in pairs),
        "queries_with_lost_required_ids": sum(bool(p["lost_ids"]) for p in pairs),
        "changes": [p for p in pairs if p["recovered_ids"] or p["lost_ids"]],
    }


def run(groups, encoder):
    packets = {}
    provenance = {}
    for group in groups:
        provenance[group["domain"]] = {
            identifier: (
                day,
                {
                    "source_actor": "station-" + origin,
                    "source_locator": "fixture:" + origin,
                    "producer": "collector",
                    "observed_at": timestamp(day).replace("Z", ".000000+00:00"),
                    "recorded_at": timestamp(day).replace("Z", ".000000+00:00"),
                    "digest": "sha256:" + sha256(text.encode()).hexdigest(),
                },
            )
            for identifier, scope, day, text, origin in group["records"]
            if scope == group["domain"]
        }

    def observe(group, ordinal, task, arm, packet):
        if arm not in ARMS:
            return
        domain = group["domain"]
        key = (domain, ordinal)
        observed = packets.setdefault(
            key, {"task": f"{domain}/{ordinal}", "required": sorted(task["required"])}
        )
        visible = {
            name: fields for name, (day, fields) in provenance[domain].items() if day <= task["day"]
        }
        found = audit_packet(packet, visible)
        if not set(task["required"]) <= visible.keys():
            raise InvalidRun("Evaluator required evidence is out of scope or time")
        observed[arm] = found

    build_ms = []
    with TemporaryDirectory(prefix="aams-109-") as directory:
        rows = replay(
            Path(directory) / "eval.sqlite",
            groups,
            1,
            rankings=(LexicalRanking.BM25,),
            encoder=encoder,
            build_ms=build_ms,
            observe_packet=observe,
        )
    if problems := check_validity(rows):
        raise InvalidRun(problems[0])
    records = list(packets.values())
    arms = [arm for arm in ARMS if arm in records[0]]
    quality = {
        arm: {
            "satisfied": sum(row["measurements"][arm]["satisfied"] for row in rows),
            "mean_recall_at_3": statistics.mean(row["measurements"][arm]["recall"] for row in rows),
            "contradictions_missed": sum(
                row["contradiction"] and not row["measurements"][arm]["satisfied"] for row in rows
            ),
        }
        for arm in arms
    }
    costs = {}
    for arm in arms:
        samples = sorted(row["measurements"][arm]["latency_ms"][0] for row in rows)
        costs[arm] = {
            "p50_ms": statistics.median(samples),
            "p95_ms": samples[(95 * len(samples) - 1) // 100],
        }
    return {
        "queries": len(rows),
        "quality": quality,
        "safety": {"audited_packets": len(rows) * len(arms), "violations": 0},
        "comparisons": {
            arm: {baseline: compare(rows, records, arm, baseline) for baseline in ARMS[:2]}
            for arm in arms[2:]
        },
        "costs": {
            "warm_replay_latency": costs,
            "whole_process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "candidate_index_build_ms_total": sum(build_ms),
        },
        "packets": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workload", choices=(*SQUAD, "scifact", "semantic"))
    parser.add_argument("candidate", choices=("baseline", *CANDIDATES))
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--model", type=Path)
    args = parser.parse_args()
    if (args.dataset is None) != (args.workload == "semantic"):
        parser.error("Provide --dataset for a public corpus only")
    if (args.model is None) != (args.candidate == "baseline"):
        parser.error("Provide --model for a candidate only")
    groups, corpus_hash = groups_for(args.workload, args.dataset)
    encoder, recipe = opened(args.candidate, args.model) if args.model else (None, None)
    output = {
        "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {name: version(name) for name in ("onnxruntime", "numpy", "tokenizers")}
        if args.candidate in (*VARIANTS, "bge-float")
        else {},
        "workload": args.workload,
        "candidate": args.candidate,
        "corpus_sha256": corpus_hash,
        "selection_sha256": sha256(json.dumps(groups, sort_keys=True).encode()).hexdigest(),
        "model_recipe": recipe,
        "spec": repr(encoder.spec) if encoder else None,
        **run(groups, encoder),
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
