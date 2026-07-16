"""Orchestrate the read-from-S3 ingestion pass.

Reads the raw filings, ETF holdings, and news that the uploaders (edgar_client,
earnings_client, etf_holdings, polygon_news_client) staged in S3, parses them
into a normalized set of relationship triples plus Article-node records
(filings + scored earnings releases + scored news), writes both locally for
inspection, and stages them back to S3 under `processed/` for Phase 2 (graph
construction).

Run the uploaders first, then:  python -m src.ingestion.ingest_from_s3
"""

import json
from pathlib import Path

from src.ingestion.etf_parser import parse_all_etf_holdings
from src.ingestion.relationship_parser import list_filing_articles, parse_all_filings
from src.ingestion.s3_client import put_text
from src.ingestion.score_sentiment import score_all_news, score_all_transcripts

TRIPLES_OUTPUT_KEY = "processed/relationship_triples.json"
LOCAL_TRIPLES_OUTPUT = Path("/tmp/ingest_from_s3/relationship_triples.json")

ARTICLES_OUTPUT_KEY = "processed/articles.json"
LOCAL_ARTICLES_OUTPUT = Path("/tmp/ingest_from_s3/articles.json")


def run() -> tuple[list[dict], list[dict]]:
    filing_triples = parse_all_filings()
    etf_triples = parse_all_etf_holdings()
    triples = filing_triples + etf_triples

    filing_articles = list_filing_articles()
    earnings_articles = score_all_transcripts()
    news_articles = score_all_news()
    articles = filing_articles + earnings_articles + news_articles

    LOCAL_TRIPLES_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_TRIPLES_OUTPUT.write_text(json.dumps(triples, indent=2))
    LOCAL_ARTICLES_OUTPUT.write_text(json.dumps(articles, indent=2))

    triples_key = put_text(
        TRIPLES_OUTPUT_KEY, json.dumps(triples, indent=2), content_type="application/json"
    )
    articles_key = put_text(
        ARTICLES_OUTPUT_KEY, json.dumps(articles, indent=2), content_type="application/json"
    )

    by_type: dict[str, int] = {}
    for t in triples:
        by_type[t["relationship"]] = by_type.get(t["relationship"], 0) + 1

    print(f"\n[done] {len(triples)} triples "
          f"({len(filing_triples)} filing, {len(etf_triples)} ETF)")
    for rel, count in sorted(by_type.items()):
        print(f"    {rel}: {count}")
    print(f"[done] {len(articles)} articles "
          f"({len(filing_articles)} filings, {len(earnings_articles)} scored earnings, "
          f"{len(news_articles)} scored news)")
    print(f"[done] wrote {LOCAL_TRIPLES_OUTPUT}, {LOCAL_ARTICLES_OUTPUT}")
    print(f"[done] staged s3://.../{triples_key}, s3://.../{articles_key}")
    return triples, articles


if __name__ == "__main__":
    run()
