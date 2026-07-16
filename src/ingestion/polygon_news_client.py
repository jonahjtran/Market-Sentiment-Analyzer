"""Pull recent news articles per ticker from Polygon.io and stage them in S3.

Extends the trigger-event sources beyond SEC filings/earnings (which are
annual/quarterly) with higher-frequency news. Each article lands as an
`Article` node in Neo4j (doc_type="news") via the same scoring + load path as
earnings releases (score_sentiment.score_all_news -> load_graph), so no graph
schema change is needed, news reuses the existing Article/ABOUT model.

Polygon's news feed is Benzinga + press releases; coverage is strong on the
large-cap tickers we track, thinner on small caps. The response also carries a
per-ticker `insights` sentiment (positive/negative/neutral), which we retain in
the raw payload for later cross-checking but do NOT use as the score, sentiment
is produced by our own LLM scorer so every Article is scored one consistent way.

Free tier: 5 requests/minute, so we sleep between tickers. One raw JSON file
per ticker is written to S3 under `news/<TICKER>_news.json`.

Run: python -m src.ingestion.polygon_news_client [--overwrite]
"""

from __future__ import annotations

import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

from src.ingestion.edgar_client import TICKERS
from src.ingestion.s3_client import key_for, object_exists, put_text

load_dotenv()

NEWS_URL = "https://api.polygon.io/v2/reference/news"

# How many recent articles to keep per ticker. Kept small for the thin slice:
# each article costs one LLM scoring call downstream, so this bounds cost.
ARTICLES_PER_TICKER = 5

# Free tier allows 5 requests/minute; 13s spacing stays comfortably under it.
RATE_LIMIT_SLEEP = 13


def _api_key() -> str:
    key = os.environ.get("POLYGON_API_KEY")
    if not key:
        raise RuntimeError(
            "POLYGON_API_KEY is not set, add it to .env (see .env.example)."
        )
    return key


def fetch_ticker_news(ticker: str, limit: int = ARTICLES_PER_TICKER) -> list[dict]:
    """Return the most recent `limit` news articles for `ticker` from Polygon."""
    resp = requests.get(
        NEWS_URL,
        params={"ticker": ticker, "limit": limit, "order": "desc", "sort": "published_utc"},
        # Bearer header keeps the key out of the URL/query string.
        headers={"Authorization": f"Bearer {_api_key()}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def fetch_and_upload_news(ticker: str, overwrite: bool = False) -> str | None:
    key = key_for("news", f"{ticker}_news.json")
    if not overwrite and object_exists(key):
        print(f"[skip] {ticker}: {key} already in S3")
        return key

    articles = fetch_ticker_news(ticker)
    if not articles:
        print(f"[skip] {ticker}: no news returned")
        return None

    put_text(key, json.dumps(articles, indent=2), content_type="application/json")
    print(f"[ok] {ticker}: uploaded {len(articles)} articles to {key}")
    return key


def main(overwrite: bool = False) -> None:
    for i, ticker in enumerate(TICKERS):
        fetch_and_upload_news(ticker, overwrite=overwrite)
        if i < len(TICKERS) - 1:
            time.sleep(RATE_LIMIT_SLEEP)  # respect free-tier 5 req/min


if __name__ == "__main__":
    main(overwrite="--overwrite" in sys.argv)
