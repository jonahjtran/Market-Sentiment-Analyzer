"""Score sentiment on earnings releases (PRD Phase 3).

Pulls the earnings exhibit that earnings_client.py staged in S3 under
`transcripts/<TICKER>_earnings*`, runs it through an LLM to produce a sentiment
score + short summary, and returns it as Article-node metadata (PRD 4.3) for
load_graph.py to load into Neo4j. Scoring happens once here, at ingestion, 
never recomputed at query time.

News articles staged by polygon_news_client.py are scored the same way
(score_all_news) so every Article node, filing, earnings, or news, carries a
sentiment score produced by one consistent scorer, not a mix of vendor scores.

Run: python -m src.ingestion.score_sentiment [TICKER]   (all tracked tickers if omitted)
"""

from __future__ import annotations

import json
import os
import re
import sys

from anthropic import Anthropic
from dotenv import load_dotenv

from src.ingestion.edgar_client import TICKERS
from src.ingestion.html_utils import html_to_text
from src.ingestion.s3_client import get_metadata, list_objects, read_text

load_dotenv()

MODEL = "claude-sonnet-5"
MAX_TOKENS = 2000
MAX_CHARS = 40_000

_SCORING_PROMPT = """\
You are scoring the market sentiment of an earnings release filed by {ticker}.

Read the release below and produce:
- "score": a number from -1.0 (very negative) to 1.0 (very positive) reflecting
  the near-term market sentiment implied by the results and commentary
- "summary": a 2-4 sentence plain-English summary of the key results and
  outlook drivers behind that score

Return only a JSON object with exactly these keys: "score", "summary".

Earnings release:
---
{text}
---
"""

_NEWS_SCORING_PROMPT = """\
You are scoring the near-term market sentiment of a news article about {ticker}.

Read the headline and summary below and produce:
- "score": a number from -1.0 (very negative) to 1.0 (very positive) reflecting
  the likely near-term sentiment for {ticker} implied by the article
- "summary": a 1-2 sentence plain-English takeaway grounded in the headline,
  leading with what happened so a reader gets the gist without the raw article

Return only a JSON object with exactly these keys: "score", "summary".

Article:
---
{text}
---
"""

_client: Anthropic | None = None


def _anthropic() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_KEY"])
    return _client


def _parse_json_object(raw: str) -> dict:
    """Parse the model's reply into a dict, tolerating stray code fences/prose."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model reply: {raw[:200]!r}")
    return json.loads(match.group(0))


def _transcript_key(ticker: str) -> str | None:
    keys = [k for k in list_objects("transcripts") if k.split("/")[-1].startswith(f"{ticker}_earnings")]
    return keys[0] if keys else None


def score_transcript(ticker: str) -> dict:
    key = _transcript_key(ticker)
    if key is None:
        raise FileNotFoundError(f"No transcript found in S3 for {ticker}")

    text = html_to_text(read_text(key))[:MAX_CHARS]

    resp = _anthropic().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": _SCORING_PROMPT.format(ticker=ticker, text=text)}],
    )
    text_blocks = [block.text for block in resp.content if block.type == "text"]
    result = _parse_json_object("".join(text_blocks))

    return {
        "ticker": ticker,
        "source_doc": key,
        # Real filed form (8-K vs 6-K), read back from upload-time metadata
        # rather than assumed, since a filer may have fallen back to 6-K.
        "doc_type": get_metadata(key).get("form", "unknown"),
        "sentiment_score": result["score"],
        "summary": result["summary"],
    }


def score_all_transcripts() -> list[dict]:
    """Score every tracked ticker that has an earnings release in S3."""
    articles = []
    for ticker in TICKERS:
        try:
            articles.append(score_transcript(ticker))
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            print(f"[skip] {ticker}: {exc}")
    return articles


def _news_key(ticker: str) -> str | None:
    keys = [k for k in list_objects("news") if k.split("/")[-1] == f"{ticker}_news.json"]
    return keys[0] if keys else None


def score_news_article(ticker: str, article: dict) -> dict | None:
    """Score one Polygon news article into an Article-node record.

    Returns None for articles missing a stable URL (used as the Article's unique
    source_doc key) or any usable text to score.
    """
    source_doc = article.get("article_url")
    text = "\n".join(p for p in (article.get("title"), article.get("description")) if p).strip()
    if not source_doc or not text:
        return None

    resp = _anthropic().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "user", "content": _NEWS_SCORING_PROMPT.format(ticker=ticker, text=text[:MAX_CHARS])}
        ],
    )
    text_blocks = [block.text for block in resp.content if block.type == "text"]
    result = _parse_json_object("".join(text_blocks))

    return {
        "ticker": ticker,
        "source_doc": source_doc,
        "doc_type": "news",
        "sentiment_score": result["score"],
        "summary": result["summary"],
    }


def score_ticker_news(ticker: str) -> list[dict]:
    """Score every staged news article for one ticker."""
    key = _news_key(ticker)
    if key is None:
        raise FileNotFoundError(f"No news file found in S3 for {ticker}")

    articles = json.loads(read_text(key))
    scored = []
    for article in articles:
        try:
            record = score_news_article(ticker, article)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"[skip] {ticker} news article: {exc}")
            continue
        if record is not None:
            scored.append(record)
    return scored


def score_all_news() -> list[dict]:
    """Score every tracked ticker that has staged news in S3."""
    articles = []
    for ticker in TICKERS:
        try:
            articles.extend(score_ticker_news(ticker))
        except FileNotFoundError as exc:
            print(f"[skip] {ticker}: {exc}")
    return articles


if __name__ == "__main__":
    if len(sys.argv) > 1:
        results = [score_transcript(sys.argv[1])]
    else:
        results = score_all_transcripts()

    for r in results:
        print(f"[done] {r['ticker']} ({r['doc_type']}): score={r['sentiment_score']}")
        print(f"    {r['summary']}")
