"""Pull latest 10-K filings from SEC EDGAR and upload the raw documents to S3."""

import time
from pathlib import Path

import requests

from src.ingestion.s3_client import key_for, object_exists, upload_file

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


def load_ticker_to_cik() -> dict[str, int]:
    resp = requests.get(TICKER_CIK_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {row["ticker"]: row["cik_str"] for row in data.values()}


# Backwards-compatible alias (kept so existing callers keep working).
_load_ticker_to_cik = load_ticker_to_cik


def latest_filing(cik: int, form: str = "10-K") -> tuple[str, str] | None:
    """Return (accession, primary_document) for the most recent filing of `form`."""
    resp = requests.get(SUBMISSIONS_URL.format(cik=cik), headers=HEADERS, timeout=30)
    resp.raise_for_status()
    recent = resp.json()["filings"]["recent"]
    for filed_form, accession, doc in zip(
        recent["form"], recent["accessionNumber"], recent["primaryDocument"]
    ):
        if filed_form == form:
            return accession, doc
    return None


def _latest_10k_filing(cik: int) -> tuple[str, str] | None:
    return latest_filing(cik, form="10-K")


def fetch_and_upload_10k(ticker: str, cik: int) -> str | None:
    # Foreign private issuers (e.g. TSM, ASML) file an annual 20-F instead of
    # a 10-K, so fall back to that form before giving up.
    form = "10-K"
    filing = latest_filing(cik, form=form)
    if filing is None:
        form = "20-F"
        filing = latest_filing(cik, form=form)
    if filing is None:
        print(f"[skip] {ticker}: no 10-K or 20-F found")
        return None
    accession, doc = filing
    accession_nodash = accession.replace("-", "")

    suffix = Path(doc).suffix or ".htm"
    key_name = f"{ticker}_10K{suffix}"
    key = key_for("filings", key_name)
    if object_exists(key):
        print(f"[skip] {ticker}: {key} already in S3")
        return key

    doc_url = ARCHIVE_URL.format(cik=cik, accession_nodash=accession_nodash, doc=doc)
    resp = requests.get(doc_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    local_path = SCRATCH_DIR / key_name
    local_path.write_bytes(resp.content)

    key = upload_file(local_path, "filings", key_name=key_name)
    print(f"[ok] {ticker}: uploaded {key} (form {form})")
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
