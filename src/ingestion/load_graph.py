"""Load parsed triples and articles into Neo4j (PRD Phase 2 — Graph Construction).

Reads the normalized triples and Article records produced by ingest_from_s3.py
(either the local scratch copy or the `processed/` objects in S3) and MERGEs
them into Neo4j as `Entity` nodes connected by typed, directed edges, plus
`Article` nodes (filings + scored earnings releases) pointing to the Entity
they were filed by via `ABOUT`.

Run: python -m src.ingestion.load_graph
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from src.ingestion.s3_client import read_text

load_dotenv()

# Filing-derived triples name companies in free text ("Intel Corporation",
# "Intel", "Intel Corp.") while Article nodes are keyed by ticker. Left
# unnormalized, MERGE (which matches on exact name) splits one real company
# into several Entity nodes and orphans them from their articles/edges.
# Strip common corporate suffixes so name variants collapse onto one node.
_CORP_SUFFIXES_RE = re.compile(
    r",?\s+(inc\.?|incorporated|corp\.?|corporation|co\.?|company|"
    r"ltd\.?|limited|llc|l\.l\.c\.?|plc|group|holdings?|"
    r"n\.v\.?|s\.a\.?)\.?\s*$",
    re.IGNORECASE,
)


def canonical_name(name: str) -> str:
    """Collapse company name variants to one canonical string.

    Tickers (all-caps, no spaces, already the canonical form used by
    Article nodes) pass through untouched. Strips corporate suffixes
    repeatedly (e.g. "Foo Holdings, Inc." -> "Foo") and normalizes case.
    """
    name = name.strip()
    if name.isupper() and " " not in name:
        return name
    prev = None
    while prev != name:
        prev = name
        name = _CORP_SUFFIXES_RE.sub("", name).strip()
    return name

LOCAL_TRIPLES = Path("/tmp/ingest_from_s3/relationship_triples.json")
S3_TRIPLES_KEY = "processed/relationship_triples.json"

LOCAL_ARTICLES = Path("/tmp/ingest_from_s3/articles.json")
S3_ARTICLES_KEY = "processed/articles.json"

# Must match the edge types in PRD 4.2. Kept as an explicit allowlist because
# relationship type is interpolated into the Cypher query string below (Cypher
# has no parameter binding for relationship types) — untrusted values must
# never reach that string.
VALID_RELATIONSHIPS = {
    "SUPPLIES_TO",
    "SUPPLIED_BY",
    "COMPETES_WITH",
    "CO_HOLDS_ETF",
    "SECTOR_PEER",
}

_MERGE_QUERY_TEMPLATE = """
UNWIND $rows AS row
MERGE (a:Entity {{name: row.source}})
MERGE (b:Entity {{name: row.target}})
MERGE (a)-[r:{rel_type}]->(b)
SET r.confidence = row.confidence,
    r.evidence = row.evidence,
    r.source_doc = row.source_doc
"""

_ARTICLE_MERGE_QUERY = """
UNWIND $rows AS row
MERGE (a:Article {source_doc: row.source_doc})
ON CREATE SET a.date_added = row.date_added
SET a.doc_type = row.doc_type,
    a.ticker = row.ticker,
    a.sentiment_score = row.sentiment_score,
    a.summary = row.summary
MERGE (e:Entity {name: row.ticker})
MERGE (a)-[:ABOUT]->(e)
"""


def load_triples() -> list[dict]:
    if LOCAL_TRIPLES.exists():
        return json.loads(LOCAL_TRIPLES.read_text())
    return json.loads(read_text(S3_TRIPLES_KEY))


def load_articles() -> list[dict]:
    if LOCAL_ARTICLES.exists():
        return json.loads(LOCAL_ARTICLES.read_text())
    return json.loads(read_text(S3_ARTICLES_KEY))


def write_triples(driver, triples: list[dict]) -> None:
    by_type: dict[str, list[dict]] = {}
    for t in triples:
        rel = t["relationship"]
        if rel not in VALID_RELATIONSHIPS:
            raise ValueError(f"Unknown relationship type: {rel!r}")
        t = {**t, "source": canonical_name(t["source"]), "target": canonical_name(t["target"])}
        by_type.setdefault(rel, []).append(t)

    with driver.session() as session:
        for rel_type, rows in by_type.items():
            query = _MERGE_QUERY_TEMPLATE.format(rel_type=rel_type)
            session.run(query, rows=rows)
            print(f"[done] merged {len(rows)} {rel_type} edges")


def write_articles(driver, articles: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    articles = [{**a, "ticker": canonical_name(a["ticker"]), "date_added": now} for a in articles]
    with driver.session() as session:
        session.run(_ARTICLE_MERGE_QUERY, rows=articles)
    print(f"[done] merged {len(articles)} Article nodes")


def run() -> None:
    triples = load_triples()
    articles = load_articles()
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        write_triples(driver, triples)
        write_articles(driver, articles)
    finally:
        driver.close()
    print(f"[done] loaded {len(triples)} triples and {len(articles)} articles into Neo4j")


if __name__ == "__main__":
    run()
