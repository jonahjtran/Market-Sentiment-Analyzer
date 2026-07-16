"""Pull ETF holdings files from fund providers and upload the raw CSVs to S3.

Holdings give us `CO_HOLDS_ETF` edges: every pair of names an ETF holds is a
(weak) peer/co-membership relationship. v1 targets the semiconductor / data
center ETFs whose members overlap the NVDA/AMD/TSM trigger universe.
"""

from __future__ import annotations

import time
from pathlib import Path

import requests

from src.ingestion.s3_client import key_for, object_exists, upload_file

# iShares/State Street expose a public CSV export per fund. These URLs are the
# "download holdings" links off each fund's product page; they occasionally
# change when a provider reworks its site, so keep them here as config.
ETF_HOLDINGS_URLS = {
    "SOXX": (
        "https://www.ishares.com/us/products/239705/"
        "ishares-phlx-semiconductor-etf/1467271812596.ajax"
        "?fileType=csv&fileName=SOXX_holdings&dataType=fund"
    ),
    "SMH": (
        "https://www.vaneck.com/us/en/investments/"
        "semiconductor-etf-smh/holdings/download/"
    ),
}

# Providers block the default requests UA; present a browser-like one.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

SCRATCH_DIR = Path("/tmp/etf_holdings")


def fetch_and_upload_holdings(etf: str, url: str) -> str | None:
    key_name = f"{etf}_holdings.csv"
    key = key_for("etf_holdings", key_name)
    if object_exists(key):
        print(f"[skip] {etf}: {key} already in S3")
        return key

    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[skip] {etf}: download failed ({exc})")
        return None

    if not resp.content.strip():
        print(f"[skip] {etf}: empty holdings file")
        return None

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    local_path = SCRATCH_DIR / key_name
    local_path.write_bytes(resp.content)

    key = upload_file(local_path, "etf_holdings", key_name=key_name)
    print(f"[ok] {etf}: uploaded {key} ({len(resp.content):,} bytes)")
    return key


def main() -> None:
    for etf, url in ETF_HOLDINGS_URLS.items():
        fetch_and_upload_holdings(etf, url)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
