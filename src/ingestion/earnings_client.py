"""Pull the latest earnings release (8-K, Item 2.02 exhibit) from SEC EDGAR and
upload it to S3 under `transcripts/`.

SEC EDGAR does not host verbatim call transcripts (those are third-party and
deferred to v2). The closest free, legally-mandated source is the earnings
press release filed as Exhibit 99.1 of the quarterly 8-K. That exhibit carries
the results commentary we run sentiment scoring over in Phase 3.
"""

import time
from pathlib import Path

import requests

from src.ingestion.edgar_client import (
    HEADERS,
    TICKERS,
    load_ticker_to_cik,
    latest_filing,
)
from src.ingestion.s3_client import key_for, object_exists, upload_file

INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/index.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{doc}"

SCRATCH_DIR = Path("/tmp/edgar_earnings")


def _earnings_exhibit(cik: int, accession_nodash: str, primary_doc: str) -> str:
    """Pick the earnings-release exhibit (EX-99.x) from a filing's index.

    Falls back to the filing's primary document when no 99.x exhibit is found.
    """
    resp = requests.get(
        INDEX_URL.format(cik=cik, accession_nodash=accession_nodash),
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("directory", {}).get("item", [])
    for item in items:
        name = item.get("name", "").lower()
        if name.startswith(("ex99", "ex-99", "exhibit99")) and name.endswith(
            (".htm", ".html", ".txt")
        ):
            return item["name"]
    return primary_doc


def fetch_and_upload_earnings(ticker: str, cik: int) -> str | None:
    # Foreign private issuers (e.g. TSM, ASML) don't file 8-Ks; their interim
    # earnings releases go out as 6-Ks instead.
    filing = latest_filing(cik, form="8-K")
    if filing is None:
        filing = latest_filing(cik, form="6-K")
    if filing is None:
        print(f"[skip] {ticker}: no 8-K or 6-K found")
        return None
    accession, primary_doc = filing
    accession_nodash = accession.replace("-", "")

    doc = _earnings_exhibit(cik, accession_nodash, primary_doc)

    suffix = Path(doc).suffix or ".htm"
    key_name = f"{ticker}_earnings{suffix}"
    key = key_for("transcripts", key_name)
    if object_exists(key):
        print(f"[skip] {ticker}: {key} already in S3")
        return key

    doc_url = ARCHIVE_URL.format(cik=cik, accession_nodash=accession_nodash, doc=doc)
    resp = requests.get(doc_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    local_path = SCRATCH_DIR / key_name
    local_path.write_bytes(resp.content)

    key = upload_file(local_path, "transcripts", key_name=key_name)
    print(f"[ok] {ticker}: uploaded {key}")
    return key


def main() -> None:
    ticker_to_cik = load_ticker_to_cik()
    for ticker in TICKERS:
        cik = ticker_to_cik.get(ticker)
        if cik is None:
            print(f"[skip] {ticker}: CIK not found")
            continue
        fetch_and_upload_earnings(ticker, cik)
        time.sleep(0.3)  # stay under SEC's 10 req/s limit (two calls per ticker)


if __name__ == "__main__":
    main()
