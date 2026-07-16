"""Run the graph-RAG vs flat-RAG comparison and write a scored report.

For each question in the fixed test set (src/eval/test_set.py):
  1. Graph RAG, src.retrieval.reason.answer (N-hop subgraph + reasoning)
  2. Flat RAG, src.retrieval.flat_rag.answer (vector similarity + reasoning)
Both use the SAME reasoning model; the only difference is the retrieval layer,
so the comparison isolates "graph traversal vs flat vector search."

Then three scores per question:
  - entity recall  (answer-level, objective), src.eval.metrics
  - retrieval coverage (mechanism, objective), src.eval.metrics
  - LLM-as-judge  (blinded, position-randomized), src.eval.judge

Writes src/eval/results.json (consumed by the /eval web page) and prints a
summary table.

Run: python -m src.eval.run_eval
Prereqs: Neo4j populated, flat index built (`python -m src.retrieval.flat_rag build`).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from src.eval import judge as judge_mod
from src.eval.metrics import coverage, entity_recall, mentioned_entities
from src.eval.test_set import TEST_SET
from src.retrieval import flat_rag, reason

load_dotenv()

RESULTS_PATH = Path(__file__).parent / "results.json"


def _graph_reached(subgraph: dict, expected: list[str]) -> set[str]:
    """Which expected tickers the traversed subgraph actually contains."""
    names = {subgraph.get("center") or ""}
    for edge in subgraph.get("edges", []):
        names.add(edge["source"])
        names.add(edge["target"])
    names.update(subgraph.get("articles", {}).keys())
    # reached names may be tickers or company names, match via aliases
    return mentioned_entities(" \n ".join(n for n in names if n), expected)


def _flat_reached(retrieved: list[dict], expected: list[str]) -> set[str]:
    """Which expected tickers appear among the retrieved chunks' source tickers."""
    tickers = {r.get("ticker") for r in retrieved}
    return tickers & set(expected)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _with_retry(fn, *args, tries: int = 3):
    """Call a retrieval+reasoning fn, retrying if it returns an empty answer.

    An empty LLM synthesis is a transient generation failure (blank content
    block under rapid batching), not a legitimate 0-recall result, scoring it
    as one would misrepresent the system. Retry before accepting it.
    """
    result = fn(*args)
    for _ in range(tries - 1):
        if (result.get("answer") or "").strip():
            return result
        print("    [retry] empty answer, re-generating…")
        result = fn(*args)
    return result


def run() -> dict:
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )

    if flat_rag._get_collection().count() == 0:
        raise RuntimeError(
            "Flat index is empty, run `python -m src.retrieval.flat_rag build` first."
        )

    per_question = []
    try:
        for i, q in enumerate(TEST_SET):
            print(f"[{i + 1}/{len(TEST_SET)}] {q['id']} (trigger {q['trigger']})…")
            expected = q["expected"]

            graph_res = _with_retry(lambda: reason.answer(driver, q["trigger"], q["question"]))
            flat_res = _with_retry(lambda: flat_rag.answer(q["question"]))

            g_recall = entity_recall(graph_res["answer"], expected)
            f_recall = entity_recall(flat_res["answer"], expected)
            g_cov = coverage(_graph_reached(graph_res["subgraph"], expected), expected)
            f_cov = coverage(_flat_reached(flat_res["retrieved"], expected), expected)

            verdict = judge_mod.judge(
                q["question"],
                expected,
                graph_res["answer"],
                flat_res["answer"],
                graph_first=(i % 2 == 0),  # deterministic position randomization
            )

            per_question.append(
                {
                    "id": q["id"],
                    "trigger": q["trigger"],
                    "question": q["question"],
                    "expected": expected,
                    "why": q["why"],
                    "graph": {
                        "answer": graph_res["answer"],
                        "recall": g_recall,
                        "coverage": g_cov,
                        "judge": verdict["graph"],
                    },
                    "flat": {
                        "answer": flat_res["answer"],
                        "recall": f_recall,
                        "coverage": f_cov,
                        "judge": verdict["flat"],
                    },
                    "winner": verdict["winner"],
                    "rationale": verdict["rationale"],
                }
            )
    finally:
        driver.close()

    # ---- aggregate ----
    dims = ("entity_coverage", "correctness", "reasoning_depth")
    wins = {"graph": 0, "flat": 0, "tie": 0}
    for row in per_question:
        wins[row["winner"]] += 1

    summary = {
        "n": len(per_question),
        "entity_recall": {
            "graph": _mean([r["graph"]["recall"]["recall"] for r in per_question]),
            "flat": _mean([r["flat"]["recall"]["recall"] for r in per_question]),
        },
        "retrieval_coverage": {
            "graph": _mean([r["graph"]["coverage"]["coverage"] for r in per_question]),
            "flat": _mean([r["flat"]["coverage"]["coverage"] for r in per_question]),
        },
        "judge_scores": {
            "graph": {d: _mean([r["graph"]["judge"][d] for r in per_question]) for d in dims},
            "flat": {d: _mean([r["flat"]["judge"][d] for r in per_question]) for d in dims},
        },
        "wins": wins,
        # ties count as half a win for the graph win-rate
        "judge_win_rate_graph": (wins["graph"] + 0.5 * wins["tie"]) / len(per_question)
        if per_question
        else 0.0,
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "models": {"reason": reason.MODEL, "flat": flat_rag.MODEL, "judge": judge_mod.MODEL},
        "summary": summary,
        "questions": per_question,
    }

    RESULTS_PATH.write_text(json.dumps(report, indent=2))
    return report


def _print_summary(report: dict) -> None:
    s = report["summary"]
    print("\n" + "=" * 64)
    print(f"  GRAPH RAG vs FLAT RAG, {s['n']} multi-hop questions")
    print("=" * 64)

    def row(label, g, f, pct=True):
        fmt = (lambda x: f"{x * 100:5.1f}%") if pct else (lambda x: f"{x:5.2f}")
        print(f"  {label:<26} graph {fmt(g)}   flat {fmt(f)}")

    row("Entity recall (answer)", s["entity_recall"]["graph"], s["entity_recall"]["flat"])
    row("Retrieval coverage", s["retrieval_coverage"]["graph"], s["retrieval_coverage"]["flat"])
    print("  " + "-" * 60)
    for d in ("entity_coverage", "correctness", "reasoning_depth"):
        row(f"Judge · {d}", s["judge_scores"]["graph"][d], s["judge_scores"]["flat"][d], pct=False)
    print("  " + "-" * 60)
    print(f"  Judge wins                 graph {s['wins']['graph']}  ·  flat {s['wins']['flat']}  ·  tie {s['wins']['tie']}")
    print(f"  Graph win rate             {s['judge_win_rate_graph'] * 100:.0f}%")
    print("=" * 64)
    print(f"  Full report → {RESULTS_PATH}")


if __name__ == "__main__":
    _print_summary(run())
