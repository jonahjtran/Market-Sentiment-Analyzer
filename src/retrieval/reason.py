"""Graph RAG reasoning/synthesis step (PRD Phase 4 — Approach A core).

Takes the N-hop subgraph + supporting articles from subgraph.py and hands
them to the LLM to reason about sentiment propagation. The LLM — not a
precomputed formula — judges which relationships matter and the likely
direction/magnitude of impact (PRD 4.4, 6.3). Graph structure still bounds
what the LLM sees: it only reasons over edges and articles that were
actually retrieved from Neo4j, not free-associated from text.

Run: python -m src.retrieval.reason NVDA "How does NVDA's earnings affect AMD, TSMC, and data center REITs?" [hops]
"""

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
You are reasoning about how sentiment from a trigger event propagates through \
a company relationship graph. You are given the {hops}-hop neighborhood of \
{ticker} in that graph (real, disclosed relationships only — not inferred) \
and the scored articles/filings attached to entities in that neighborhood.

Relationships (source -[type]-> target, confidence = extraction confidence, \
not impact strength):
{edges}

Articles per entity (score is -1.0 very negative to 1.0 very positive; None \
means the document wasn't sentiment-scored, e.g. a 10-K):
{articles}

Question: {question}

Reason about which of these relationships are actually relevant to the \
question, and for each relevant entity give a directional call (up/down/\
neutral) with a qualitative strength (strong direct effect / moderate / weak \
indirect effect). Explicitly consider cases where the relationship implies an \
inverse effect (e.g. a competitor's strong results can mean share loss, not \
shared upside) rather than assuming all propagation is positive-correlated. \
Cite the specific relationship and article evidence backing each call. If the \
retrieved subgraph doesn't contain enough information to answer part of the \
question, say so rather than speculating beyond it.
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
