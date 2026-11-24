"""Eval-only Laya E1 scripts: judge client, reranking metrics and gates. No network or model."""

import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from evaluate_laya_rerank import (  # noqa: E402
    auc,
    ece,
    gates,
    oracle_judgments,
    pair_key,
    prepare_groups,
    rerank,
    score,
)
from laya_judge import JudgeError, build_request, judge, parse_answer, run  # noqa: E402
from offline_experiment import load_groups  # noqa: E402


def answer(p: float, model: str = "laya-english") -> dict:
    return {"model": model, "answers": {"relevant": {"type": "noul", "noul": p}}}


def task(workload: str, group: str, candidates: list[str], gold: str, **extra) -> dict:
    return {
        "workload": workload,
        "group": group,
        "task": 0,
        "query": group,
        "relevant": [gold],
        "required": [gold],
        "contradiction": False,
        "candidates": candidates,
        "keys": [f"{group}:{c}" for c in candidates],
        "truncated": [False] * len(candidates),
        **extra,
    }


class JudgeClientTest(unittest.TestCase):
    def test_request_has_one_noul_question_and_no_labels(self) -> None:
        request = build_request("q", "p")
        self.assertEqual(request["state"], {"query": "q", "passage": "p"})
        self.assertEqual(request["questions"]["relevant"]["type"], "noul")

    def test_parse_rejects_wrong_model_and_bad_probabilities(self) -> None:
        self.assertEqual(parse_answer(answer(0.25), "laya-english"), (0.25, "laya-english"))
        for body in (answer(0.5, "laya-multilingual"), answer(1.5), {"model": "laya-english"}):
            with self.assertRaises(JudgeError):
                parse_answer(body, "laya-english")

    def test_transport_errors_retry_then_stop(self) -> None:
        calls, sleeps = [], []

        def flaky(_: dict) -> dict:
            calls.append(1)
            if len(calls) < 3:
                raise urllib.error.URLError("down")
            return answer(0.9)

        result = judge(
            {"key": "k", "query": "q", "passage": "p"}, flaky, "laya-english", sleeps.append
        )
        self.assertEqual((result.p_yes, len(calls), sleeps), (0.9, 3, [2.0, 4.0]))

        def down(_: dict) -> dict:
            raise urllib.error.URLError("down")

        with self.assertRaises(JudgeError):
            judge({"key": "k", "query": "q", "passage": "p"}, down, "laya-english", lambda _: None)

    def test_run_resumes_without_rejudging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pairs, out = Path(directory) / "pairs.jsonl", Path(directory) / "out.jsonl"
            rows = [{"key": k, "query": "q", "passage": k} for k in ("a", "b", "c")]
            pairs.write_text("".join(json.dumps(r) + "\n" for r in rows))
            out.write_text(json.dumps({"key": "a", "p_yes": 0.1}) + "\n")
            seen = []

            def post(payload: dict) -> dict:
                seen.append(payload["state"]["passage"])
                return answer(0.5)

            self.assertEqual(run(pairs, out, post, "laya-english"), 2)
            self.assertEqual(seen, ["b", "c"])
            self.assertEqual(run(pairs, out, post, "laya-english"), 0)


class MetricsTest(unittest.TestCase):
    def test_rerank_breaks_ties_by_incoming_order(self) -> None:
        self.assertEqual(
            rerank(["x", "y", "z"], ["1", "2", "3"], {"1": 0.2, "2": 0.9, "3": 0.2}),
            ["y", "x", "z"],
        )

    def test_auc_and_ece_boundaries(self) -> None:
        self.assertEqual(auc([0.9, 0.1], [True, False]), 1.0)
        self.assertEqual(auc([0.5, 0.5], [True, False]), 0.5)
        self.assertIsNone(auc([0.5], [True]))
        self.assertEqual(ece([1.0, 0.0], [True, False]), 0.0)
        self.assertAlmostEqual(ece([0.8, 0.8], [False, False]), 0.8)
        self.assertIsNone(ece([], []))

    def test_score_and_gates_on_a_perfect_and_a_harmful_judge(self) -> None:
        tasks = (
            [task("squad_heldout", f"s{i}", ["n1", "n2", "n3", "g"], "g") for i in range(4)]
            + [task("scifact", f"f{i}", ["g", "n1", "n2", "n3"], "g") for i in range(4)]
            + [task("fixture_v06", "x", ["g", "n1", "n2", "n3"], "g", contradiction=True)]
        )
        perfect = score(tasks, oracle_judgments(tasks))
        self.assertEqual(perfect["squad_heldout"]["mean_delta"], 1.0)
        self.assertEqual(perfect["scifact"]["mean_delta"], 0.0)
        verdict = gates(perfect)
        self.assertTrue(verdict["squad_heldout_delta"])
        self.assertFalse(verdict["scifact_delta"])
        self.assertFalse(verdict["passed"])
        inverted = {k: 1.0 - v for k, v in oracle_judgments(tasks).items()}
        harmful = score(tasks, inverted)
        self.assertEqual(harmful["fixture_v06"]["contradiction_regressions"], 1)
        self.assertFalse(gates(harmful)["fixture_no_regression"])


class PrepareTest(unittest.TestCase):
    def test_fixture_candidates_match_baseline_and_stay_in_scope(self) -> None:
        groups = load_groups()
        tasks = prepare_groups("fixture_v06", groups, None)
        self.assertEqual(len(tasks), sum(len(g["tasks"]) for g in groups))
        for item in tasks:
            records = next(g for g in groups if g["domain"] == item["group"])["records"]
            in_scope = {r[0] for r in records if r[1] == item["group"]}
            self.assertLessEqual(set(item["candidates"]), in_scope)
            self.assertEqual(
                item["keys"][0], pair_key(item["query"], item["passages"][item["candidates"][0]])
            )


if __name__ == "__main__":
    unittest.main()
