"""Pull latest 10-K filings from SEC EDGAR and upload the raw documents to S3."""

import time
from pathlib import Path

import requests

from src.ingestion.s3_client import upload_file

SEC_USER_AGENT = "Market Sentiment Analyzer jonahjtran@gmail.com"
HEADERS = {"User-Agent": SEC_USER_AGENT}

TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{doc}"

TICKERS = [
    "NVDA", "AMD", "TSM", "AVGO", "ASML",
    "MSFT", "AMZN", "GOOGL", "ORCL",
    "DLR", "EQIX",
]

SCRATCH_DIR = Path("/tmp/edgar_10k")


def _load_ticker_to_cik() -> dict[str, int]:
    resp = requests.get(TICKER_CIK_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {row["ticker"]: row["cik_str"] for row in data.values()}


def _latest_10k_filing(cik: int) -> tuple[str, str] | None:
    resp = requests.get(SUBMISSIONS_URL.format(cik=cik), headers=HEADERS, timeout=30)
    resp.raise_for_status()
    recent = resp.json()["filings"]["recent"]
    for form, accession, doc in zip(
        recent["form"], recent["accessionNumber"], recent["primaryDocument"]
    ):
        if form == "10-K":
            return accession, doc
    return None


def fetch_and_upload_10k(ticker: str, cik: int) -> str | None:
    filing = _latest_10k_filing(cik)
    if filing is None:
        print(f"[skip] {ticker}: no 10-K found")
        return None
    accession, doc = filing
    accession_nodash = accession.replace("-", "")
    doc_url = ARCHIVE_URL.format(cik=cik, accession_nodash=accession_nodash, doc=doc)

    resp = requests.get(doc_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(doc).suffix or ".htm"
    local_path = SCRATCH_DIR / f"{ticker}_10K{suffix}"
    local_path.write_bytes(resp.content)

    key = upload_file(local_path, "filings", key_name=f"{ticker}_10K{suffix}")
    print(f"[ok] {ticker}: uploaded {key}")
    return key


def main() -> None:
    ticker_to_cik = _load_ticker_to_cik()
    for ticker in TICKERS:
        cik = ticker_to_cik.get(ticker)
        if cik is None:
            print(f"[skip] {ticker}: CIK not found")
            continue
        fetch_and_upload_10k(ticker, cik)
        time.sleep(0.2)  # stay well under SEC's rate limit


if __name__ == "__main__":
    main()
