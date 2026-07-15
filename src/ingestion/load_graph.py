"""Load parsed relationship triples into Neo4j (PRD Phase 2 — Graph Construction).

Reads the normalized triples produced by ingest_from_s3.py (either the local
scratch copy or the `processed/` object in S3) and MERGEs them into Neo4j as
`Entity` nodes connected by typed, directed edges.

Run: python -m src.ingestion.load_graph
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from src.ingestion.s3_client import read_text

load_dotenv()

LOCAL_TRIPLES = Path("/tmp/ingest_from_s3/relationship_triples.json")
S3_TRIPLES_KEY = "processed/relationship_triples.json"

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


def load_triples() -> list[dict]:
    if LOCAL_TRIPLES.exists():
        return json.loads(LOCAL_TRIPLES.read_text())
    return json.loads(read_text(S3_TRIPLES_KEY))


def write_triples(driver, triples: list[dict]) -> None:
    by_type: dict[str, list[dict]] = {}
    for t in triples:
        rel = t["relationship"]
        if rel not in VALID_RELATIONSHIPS:
            raise ValueError(f"Unknown relationship type: {rel!r}")
        by_type.setdefault(rel, []).append(t)

    with driver.session() as session:
        for rel_type, rows in by_type.items():
            query = _MERGE_QUERY_TEMPLATE.format(rel_type=rel_type)
            session.run(query, rows=rows)
            print(f"[done] merged {len(rows)} {rel_type} edges")


def run() -> None:
    triples = load_triples()
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        write_triples(driver, triples)
    finally:
        driver.close()
    print(f"[done] loaded {len(triples)} triples into Neo4j")


if __name__ == "__main__":
    run()
