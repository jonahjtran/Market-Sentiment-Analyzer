"""Graph RAG reasoning/synthesis step (PRD Phase 4, Approach A core).

Takes the N-hop subgraph + supporting articles from subgraph.py and hands
them to the LLM to reason about sentiment propagation. The LLM, not a
precomputed formula, judges which relationships matter and the likely
direction/magnitude of impact (PRD 4.4, 6.3). Graph structure still bounds
what the LLM sees: it only reasons over edges and articles that were
actually retrieved from Neo4j, not free-associated from text.

Run: python -m src.retrieval.reason NVDA "How does NVDA's earnings affect AMD, TSMC, and data center REITs?" [hops]
"""

from __future__ import annotations

import os
import sys

from anthropic import Anthropic
from dotenv import load_dotenv
from neo4j import GraphDatabase

from src.retrieval.subgraph import DEFAULT_HOPS, get_subgraph

load_dotenv()

MODEL = "claude-sonnet-5"
MAX_TOKENS = 2000

_REASONING_PROMPT = """\
You are a markets analyst explaining to an investor how a company's news might \
ripple out to related companies, competitors, suppliers, and customers. You've \
been given a set of known business relationships for {ticker} and some recent \
company disclosures/earnings commentary to work from.

Known business relationships (internal research notes, do not quote this \
list or its format back to the reader; treat confidence as your own certainty \
about whether the relationship is real, not a measure of impact size):
{edges}

Recent disclosures and earnings commentary per company (internal research \
notes, a numeric score reflects how positive or negative the tone was, but \
never surface the raw number itself; translate it into plain language like \
"upbeat," "mixed," or "no notable news"):
{articles}

Question: {question}

Write a clear, conversational answer for a self-directed investor who is not \
a data engineer, never mention "graph," "database," "relationships graph," \
"nodes," "edges," "confidence scores," "subgraph," or similar backend/technical \
terms, and never print raw confidence or sentiment numbers. Instead, describe \
things the way a human analyst would: "X is a direct competitor of Y," "Z \
supplies key components to X," "the recent earnings call had an upbeat tone \
because...".

For each company you discuss, explain in plain terms whether the news is \
likely good, bad, or roughly neutral for them, how strong that effect seems \
(e.g. "this hits them directly," "this is a smaller, secondary effect"), and \
why, including cases where a competitor's good news is actually bad news for \
someone else (share loss, not shared upside), rather than assuming everything \
moves together. Ground each claim in the specific relationship or news item \
behind it, described in plain English, so the reader understands your \
reasoning without needing to know how you retrieved it. If you don't have \
enough information to say something meaningful about part of the question, \
say so plainly instead of guessing.

Write in plain prose. Do not use em dashes anywhere in your answer; use \
commas, periods, colons, or parentheses instead.
"""

_client: Anthropic | None = None


def _anthropic() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_KEY"])
    return _client


def _format_edges(edges: list[dict]) -> str:
    if not edges:
        return "(none)"
    return "\n".join(
        f"- {e['source']} -{e['rel_type']}-> {e['target']} (confidence={e['confidence']})"
        for e in edges
    )


def _format_articles(articles: dict[str, list[dict]]) -> str:
    lines = []
    for entity, arts in articles.items():
        if not arts:
            continue
        lines.append(f"{entity}:")
        for a in arts:
            lines.append(f"  - [{a['doc_type']}] score={a['score']}: {a['summary']}")
    return "\n".join(lines) if lines else "(none)"


def answer(driver, ticker: str, question: str, hops: int = DEFAULT_HOPS) -> dict:
    """Retrieve the subgraph around `ticker` and reason over it to answer `question`."""
    subgraph = get_subgraph(driver, ticker, hops)

    prompt = _REASONING_PROMPT.format(
        hops=hops,
        ticker=ticker,
        edges=_format_edges(subgraph["edges"]),
        articles=_format_articles(subgraph["articles"]),
        question=question,
    )

    resp = _anthropic().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")

    return {"ticker": ticker, "question": question, "subgraph": subgraph, "answer": text}


def run() -> None:
    if len(sys.argv) < 3:
        print('Usage: python -m src.retrieval.reason TICKER "question" [hops]')
        sys.exit(1)

    ticker = sys.argv[1]
    question = sys.argv[2]
    hops = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_HOPS

    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        result = answer(driver, ticker, question, hops)
    finally:
        driver.close()

    print(f"Q: {result['question']}\n")
    print(result["answer"])


if __name__ == "__main__":
    run()
