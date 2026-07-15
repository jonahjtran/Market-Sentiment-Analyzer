"""Side-by-side demo server (PRD Phase 6).

Runs the graph-RAG answer (src/retrieval/reason.py) and the flat-RAG baseline
(src/retrieval/flat_rag.py) against the same question and serves both next to
each other for visual comparison. This is the "regular RAG fails, graph RAG
succeeds" deliverable (PRD Section 8).

Run: python -m src.demo.app
Then open http://localhost:5050
"""

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from neo4j import GraphDatabase

from src.retrieval import flat_rag, reason
from src.retrieval.subgraph import DEFAULT_HOPS

load_dotenv()

app = Flask(__name__, static_folder="static")

DEFAULT_QUESTIONS = [
    "How does NVDA's earnings affect AMD, TSMC, and data center REITs?",
    "AMD just reported strong data center growth. What does that mean for NVDA and Intel?",
    "TSMC raised capex guidance. How does that ripple out to AVGO and its supply chain?",
]

_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        )
    return _driver


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/questions")
def questions():
    return jsonify(DEFAULT_QUESTIONS)


@app.post("/api/compare")
def compare():
    body = request.get_json(force=True)
    ticker = (body.get("ticker") or "NVDA").strip().upper()
    question = (body.get("question") or "").strip()
    hops = int(body.get("hops") or DEFAULT_HOPS)

    if not question:
        return jsonify({"error": "question is required"}), 400

    graph_result = reason.answer(_get_driver(), ticker, question, hops)
    flat_result = flat_rag.answer(question)

    return jsonify(
        {
            "question": question,
            "ticker": ticker,
            "graph": {
                "answer": graph_result["answer"],
                "edges": graph_result["subgraph"]["edges"],
                "entities_reached": sorted(graph_result["subgraph"]["articles"].keys()),
            },
            "flat": {
                "answer": flat_result["answer"],
                "retrieved": flat_result["retrieved"],
            },
        }
    )


def run() -> None:
    app.run(debug=True, port=5050)


if __name__ == "__main__":
    run()
