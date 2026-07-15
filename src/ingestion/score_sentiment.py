"""Score sentiment on a trigger entity's earnings release (PRD Phase 3).

Pulls the earnings exhibit that earnings_client.py staged in S3 under
`transcripts/<TICKER>_earnings*`, runs it through an LLM to produce a sentiment
score + short summary, and stores that result on the entity's Neo4j node so it
can be retrieved by the RAG layer at query time (PRD 4.3, 4.4) rather than
recomputed per query.

Run: python -m src.ingestion.score_sentiment NVDA
"""

import json
import os
import sys

from anthropic import Anthropic
from dotenv import load_dotenv
from neo4j import GraphDatabase

from src.ingestion.html_utils import html_to_text
from src.ingestion.s3_client import list_objects, read_text

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

_client: Anthropic | None = None


def _anthropic() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_KEY"])
    return _client


def _transcript_key(ticker: str) -> str:
    keys = [k for k in list_objects("transcripts") if k.split("/")[-1].startswith(f"{ticker}_earnings")]
    if not keys:
        raise FileNotFoundError(f"No transcript found in S3 for {ticker}")
    return keys[0]


def score_transcript(ticker: str) -> dict:
    key = _transcript_key(ticker)
    text = html_to_text(read_text(key))[:MAX_CHARS]

    resp = _anthropic().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": _SCORING_PROMPT.format(ticker=ticker, text=text)}],
    )
    text_blocks = [block.text for block in resp.content if block.type == "text"]
    result = json.loads("".join(text_blocks))
    result["ticker"] = ticker
    result["source_doc"] = key
    return result


def write_score(driver, result: dict) -> None:
    with driver.session() as session:
        session.run(
            """
            MERGE (e:Entity {name: $ticker})
            SET e.sentiment_score = $score,
                e.sentiment_summary = $summary,
                e.sentiment_source_doc = $source_doc
            """,
            ticker=result["ticker"],
            score=result["score"],
            summary=result["summary"],
            source_doc=result["source_doc"],
        )


def run(ticker: str) -> None:
    result = score_transcript(ticker)
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        write_score(driver, result)
    finally:
        driver.close()
    print(f"[done] {ticker}: score={result['score']}")
    print(f"    {result['summary']}")


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    run(ticker)
