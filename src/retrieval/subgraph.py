"""N-hop subgraph retrieval (PRD Phase 4 — Graph RAG Query Layer).

Given a trigger entity (a ticker, supplied directly — not parsed from free
text and not inferred from "most recent article"), pulls the N-hop Entity
neighborhood plus every Article attached to every entity in that neighborhood.

Hop depth is fixed by the caller, not decided by the LLM (Approach A keeps the
LLM's judgment scoped to reasoning over the retrieved subgraph, not selecting
it — PRD 6.3). Articles are not hop-limited: they hang off whichever entities
the hop traversal reaches, and every scored Article for those entities is
returned so the LLM can weigh all of them itself, rather than the retrieval
layer picking a "latest" one.

Run: python -m src.retrieval.subgraph NVDA [hops]
"""

import os
import sys

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

load_dotenv()

DEFAULT_HOPS = 2

_SUBGRAPH_QUERY_TEMPLATE = """
MATCH (start:Entity {{name: $ticker}})
MATCH path = (start)-[*1..{hops}]-(neighbor:Entity)
WHERE neighbor <> start
UNWIND relationships(path) AS rel
RETURN DISTINCT
    startNode(rel).name AS source,
    type(rel) AS rel_type,
    endNode(rel).name AS target,
    rel.confidence AS confidence
"""

_ARTICLES_QUERY = """
MATCH (e:Entity) WHERE e.name IN $names
OPTIONAL MATCH (e)<-[:ABOUT]-(a:Article)
RETURN e.name AS entity, a.sentiment_score AS score, a.summary AS summary,
       a.source_doc AS source_doc, a.doc_type AS doc_type
"""


def get_subgraph(driver: Driver, ticker: str, hops: int = DEFAULT_HOPS) -> dict:
    if not isinstance(hops, int) or hops < 1:
        raise ValueError(f"hops must be a positive int, got {hops!r}")

    with driver.session() as session:
        edges = [
            dict(row)
            for row in session.run(
                _SUBGRAPH_QUERY_TEMPLATE.format(hops=hops), ticker=ticker
            )
        ]

        entity_names = {ticker}
        for edge in edges:
            entity_names.add(edge["source"])
            entity_names.add(edge["target"])

        articles: dict[str, list[dict]] = {name: [] for name in entity_names}
        for row in session.run(_ARTICLES_QUERY, names=list(entity_names)):
            if row["source_doc"] is None:
                continue
            articles[row["entity"]].append(
                {
                    "score": row["score"],
                    "summary": row["summary"],
                    "source_doc": row["source_doc"],
                    "doc_type": row["doc_type"],
                }
            )

    return {"center": ticker, "edges": edges, "articles": articles}


def run() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    hops = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_HOPS

    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        result = get_subgraph(driver, ticker, hops)
    finally:
        driver.close()

    print(f"center: {result['center']}")
    print(f"edges ({len(result['edges'])}):")
    for edge in result["edges"]:
        print(f"  {edge['source']} -{edge['rel_type']}-> {edge['target']} (confidence={edge['confidence']})")
    print("articles:")
    for entity, arts in result["articles"].items():
        print(f"  {entity}: {len(arts)} article(s)")
        for a in arts:
            print(f"    score={a['score']} doc_type={a['doc_type']} source={a['source_doc']}")


if __name__ == "__main__":
    run()
