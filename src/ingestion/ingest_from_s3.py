"""Orchestrate the read-from-S3 ingestion pass.

Reads the raw filings and ETF holdings that the uploaders (edgar_client,
earnings_client, etf_holdings) staged in S3, parses them into a single set of
normalized relationship triples, writes the result locally for inspection, and
stages it back to S3 under `processed/` for Phase 2 (graph construction).

Run the uploaders first, then:  python -m src.ingestion.ingest_from_s3
"""

import json
from pathlib import Path

from src.ingestion.etf_parser import parse_all_etf_holdings
from src.ingestion.relationship_parser import parse_all_filings
from src.ingestion.s3_client import put_text

OUTPUT_KEY = "processed/relationship_triples.json"
LOCAL_OUTPUT = Path("/tmp/ingest_from_s3/relationship_triples.json")


def run() -> list[dict]:
    filing_triples = parse_all_filings()
    etf_triples = parse_all_etf_holdings()
    triples = filing_triples + etf_triples

    payload = json.dumps(triples, indent=2)

    LOCAL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_OUTPUT.write_text(payload)

    key = put_text(OUTPUT_KEY, payload, content_type="application/json")

    by_type: dict[str, int] = {}
    for t in triples:
        by_type[t["relationship"]] = by_type.get(t["relationship"], 0) + 1

    print(f"\n[done] {len(triples)} triples "
          f"({len(filing_triples)} filing, {len(etf_triples)} ETF)")
    for rel, count in sorted(by_type.items()):
        print(f"    {rel}: {count}")
    print(f"[done] wrote {LOCAL_OUTPUT}")
    print(f"[done] staged s3://.../{key}")
    return triples


if __name__ == "__main__":
    run()
