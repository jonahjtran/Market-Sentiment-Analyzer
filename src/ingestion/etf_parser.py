"""Read ETF holdings CSVs out of S3 and emit `CO_HOLDS_ETF` co-membership edges.

An ETF holding two names is a weak, mechanical peer signal (PRD edge-weight
prior 0.2-0.3). A full ETF would produce O(n^2) pairs, so v1 restricts edges to
the intersection of each ETF's holdings with our tracked universe (edgar_client
.TICKERS) — that keeps the graph focused on the NVDA/AMD/TSM neighborhood and
bounded in size. Widen this in Phase 8 when scaling coverage.
"""

import csv
import io
from itertools import combinations

from src.ingestion.edgar_client import TICKERS
from src.ingestion.s3_client import list_objects, read_text

TRACKED = set(TICKERS)

# Rows that are cash/derivative lines rather than equity holdings.
_NON_EQUITY = {"", "-", "USD", "CASH", "CASH_USD"}


def _etf_from_key(key: str) -> str:
    """`etf-holdings/SOXX_holdings.csv` -> `SOXX`."""
    return key.rsplit("/", 1)[-1].split("_", 1)[0].upper()


def _find_header(lines: list[str]) -> int:
    """Locate the CSV column-header row (the one naming a Ticker column).

    Provider files prepend a block of fund-metadata lines before the table.
    """
    for i, line in enumerate(lines):
        cells = [c.strip().strip('"').lower() for c in line.split(",")]
        if "ticker" in cells:
            return i
    return -1


def extract_holdings_tickers(csv_text: str) -> list[str]:
    """Return the equity tickers listed in an ETF holdings CSV."""
    lines = csv_text.splitlines()
    header_idx = _find_header(lines)
    if header_idx == -1:
        return []

    reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])))
    ticker_col = next(
        (f for f in (reader.fieldnames or []) if f and f.strip().lower() == "ticker"),
        None,
    )
    if ticker_col is None:
        return []

    tickers: list[str] = []
    seen: set[str] = set()
    for row in reader:
        raw = (row.get(ticker_col) or "").strip().strip('"').upper()
        if raw in _NON_EQUITY or raw in seen:
            continue
        seen.add(raw)
        tickers.append(raw)
    return tickers


def parse_etf_from_s3(key: str) -> list[dict]:
    """Read one holdings file from S3 and return CO_HOLDS_ETF triples."""
    etf = _etf_from_key(key)
    holdings = extract_holdings_tickers(read_text(key))
    members = sorted(TRACKED.intersection(holdings))

    triples = [
        {
            "source": a,
            "relationship": "CO_HOLDS_ETF",
            "target": b,
            "confidence": 0.25,  # weak, mechanical prior (PRD 6.5)
            "evidence": f"Both held by {etf}",
            "etf": etf,
            "source_doc": key,
        }
        for a, b in combinations(members, 2)
    ]
    print(f"[ok] {key}: {len(members)} tracked members -> {len(triples)} triples")
    return triples


def parse_all_etf_holdings() -> list[dict]:
    """Parse every file currently under the `etf-holdings/` prefix in S3."""
    triples: list[dict] = []
    for key in list_objects("etf_holdings"):
        triples.extend(parse_etf_from_s3(key))
    return triples


if __name__ == "__main__":
    for triple in parse_all_etf_holdings():
        print(triple)
