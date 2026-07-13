"""Read 10-K filings out of S3 and extract disclosed inter-company relationships
as directed (source, relationship, target) triples.

This is the "parse relationships" half of the ingestion layer (PRD 4.2). It is
LLM-assisted rather than pure regex because supplier/customer disclosures are
written in prose and vary filing to filing. Triples land in a normalized shape
that Phase 2 (graph construction) loads straight into Neo4j.
"""

import json
import os
import re

from anthropic import Anthropic
from dotenv import load_dotenv

from src.ingestion.edgar_client import TICKERS
from src.ingestion.html_utils import html_to_text, relationship_windows
from src.ingestion.s3_client import list_objects, read_text

load_dotenv()

MODEL = "claude-sonnet-5"
MAX_TOKENS = 2000

# Edge types the parser is allowed to emit for filing-derived relationships.
VALID_RELATIONSHIPS = {"SUPPLIES_TO", "SUPPLIED_BY", "COMPETES_WITH"}

_client: Anthropic | None = None


def _anthropic() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_KEY"])
    return _client


def _ticker_from_key(key: str) -> str:
    """Infer the subject ticker from an S3 key like `filings/NVDA_10K.htm`."""
    return key.rsplit("/", 1)[-1].split("_", 1)[0].upper()


_EXTRACTION_PROMPT = """\
You are extracting disclosed inter-company relationships from an SEC 10-K filed
by {ticker}.

From the excerpts below, extract concrete relationships where {ticker} discloses
a specific other company as a supplier, customer, or competitor. Only include
named companies (not generic phrases like "our customers"). Ignore the company's
own subsidiaries.

Return a JSON array. Each element must be an object with exactly these keys:
- "source": ticker or company name of the relationship's source
- "relationship": one of "SUPPLIES_TO", "SUPPLIED_BY", "COMPETES_WITH"
- "target": ticker or company name of the relationship's target
- "confidence": a number from 0.0 to 1.0 for how clearly the filing states it
- "evidence": a short quote (<= 25 words) from the excerpt supporting it

Direction rules (edges are directed source -> target):
- If A supplies/sells to B, emit source=A, relationship="SUPPLIES_TO", target=B.
- If A buys from / depends on supplier B, emit source=B, "SUPPLIES_TO", target=A.
- For competitors, emit source={ticker}, "COMPETES_WITH", target=<other>.

Prefer stock tickers when the company is one of these known names, otherwise use
the full company name: {known}

Return ONLY the JSON array, no prose. Return [] if nothing qualifies.

EXCERPTS:
{excerpts}
"""


def _parse_json_array(raw: str) -> list[dict]:
    """Parse the model's reply into a list, tolerating stray code fences/prose."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def extract_relationships(ticker: str, text: str) -> list[dict]:
    """Run the LLM extraction over prepared filing text for one company."""
    excerpts = relationship_windows(text)
    prompt = _EXTRACTION_PROMPT.format(
        ticker=ticker, known=", ".join(TICKERS), excerpts=excerpts
    )
    message = _anthropic().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    rows = _parse_json_array(message.content[0].text)

    triples: list[dict] = []
    for row in rows:
        rel = str(row.get("relationship", "")).upper()
        if rel not in VALID_RELATIONSHIPS:
            continue
        source = str(row.get("source", "")).strip()
        target = str(row.get("target", "")).strip()
        if not source or not target or source == target:
            continue
        triples.append(
            {
                "source": source,
                "relationship": rel,
                "target": target,
                "confidence": row.get("confidence"),
                "evidence": row.get("evidence", ""),
            }
        )
    return triples


def parse_filing_from_s3(key: str) -> list[dict]:
    """Read one filing from S3 and return its relationship triples."""
    ticker = _ticker_from_key(key)
    text = html_to_text(read_text(key))
    triples = extract_relationships(ticker, text)
    for t in triples:
        t["source_doc"] = key
    print(f"[ok] {key}: {len(triples)} triples")
    return triples


def parse_all_filings() -> list[dict]:
    """Parse every filing currently under the `filings/` prefix in S3."""
    triples: list[dict] = []
    for key in list_objects("filings"):
        triples.extend(parse_filing_from_s3(key))
    return triples


if __name__ == "__main__":
    for triple in parse_all_filings():
        print(triple)
