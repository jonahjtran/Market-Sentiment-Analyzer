"""Flat RAG baseline (PRD Phase 5, comparator for the graph RAG demo).

Chunks the same filings/transcripts/news used by the graph pipeline into a
ChromaDB collection with standard embeddings and answers questions via plain
vector similarity search, no entity graph, no relationship traversal. This
is the "regular RAG fails" side of the Phase 6 side-by-side demo: it can only
surface whatever chunks are semantically close to the question, so it has no
structural way to reach entities that aren't named in the trigger document's
own text (e.g. it can't discover TSM is NVDA's supplier unless a chunk about
NVDA happens to mention TSM by name).

Run:
  python -m src.retrieval.flat_rag build
  python -m src.retrieval.flat_rag query "How does NVDA's earnings affect AMD, TSMC, and data center REITs?"
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import chromadb
from anthropic import Anthropic
from dotenv import load_dotenv

from src.ingestion.edgar_client import TICKERS
from src.ingestion.html_utils import html_to_text
from src.ingestion.s3_client import list_objects, read_text

load_dotenv()

MODEL = "claude-sonnet-5"
MAX_TOKENS = 2000
TOP_K = 8

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200

CHROMA_DIR = Path("/tmp/flat_rag_chroma")
COLLECTION_NAME = "filings_transcripts_news"

_client: Anthropic | None = None


def _anthropic() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_KEY"])
    return _client


def _ticker_from_key(key: str) -> str:
    return key.rsplit("/", 1)[-1].split("_", 1)[0].upper()


def _chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def _get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(COLLECTION_NAME)


def _news_documents(key: str, ticker: str) -> list[tuple[str, str, dict]]:
    """Yield (id, document, metadata) tuples for a news JSON file.

    News is indexed per-article (title + description) so the baseline sees the
    same news the graph does, keying each document by article_url to mirror the
    Article node's source_doc. A short news blurb is one chunk, not many.
    """
    out = []
    for article in json.loads(read_text(key)):
        url = article.get("article_url")
        text = "\n".join(p for p in (article.get("title"), article.get("description")) if p).strip()
        if not url or not text:
            continue
        out.append((url, text, {"source_doc": url, "ticker": ticker}))
    return out


def build_index() -> int:
    """Chunk every filing/transcript/news item in S3 and load them into ChromaDB."""
    collection = _get_collection()

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for prefix in ("filings", "transcripts", "news"):
        for key in list_objects(prefix):
            if key.endswith("/"):
                continue
            ticker = _ticker_from_key(key)
            if ticker not in TICKERS:
                continue
            if prefix == "news":
                for doc_id, doc, meta in _news_documents(key, ticker):
                    ids.append(doc_id)
                    documents.append(doc)
                    metadatas.append(meta)
                continue
            text = html_to_text(read_text(key))
            for i, chunk in enumerate(_chunk_text(text)):
                ids.append(f"{key}::{i}")
                documents.append(chunk)
                metadatas.append({"source_doc": key, "ticker": ticker})

    if not ids:
        print("[warn] no chunks found")
        return 0

    # Chroma add() has a batch size ceiling; chunk the load to stay under it.
    batch = 500
    for i in range(0, len(ids), batch):
        collection.add(
            ids=ids[i : i + batch],
            documents=documents[i : i + batch],
            metadatas=metadatas[i : i + batch],
        )

    print(f"[done] indexed {len(ids)} chunks from {len({m['source_doc'] for m in metadatas})} documents")
    return len(ids)


_FLAT_RAG_PROMPT = """\
You are a markets analyst answering an investor's question using only the \
passages below, pulled from company filings, earnings releases, and news \
articles (internal \
research notes, do not describe how these were found, e.g. never mention \
"excerpts," "semantic similarity search," "retrieved passages," or similar \
backend/technical terms).

Passages:
{excerpts}

Question: {question}

Write a clear, conversational answer for a self-directed investor who is not \
a data engineer. Base your answer only on what these passages actually say, \
don't infer connections between companies that the passages themselves don't \
state. If the passages don't give you enough to answer part of the question, \
say so plainly rather than guessing, but phrase it naturally (e.g. "the \
available filings don't say how this affects X") rather than describing your \
retrieval process.
"""


def answer(question: str, k: int = TOP_K) -> dict:
    collection = _get_collection()
    results = collection.query(query_texts=[question], n_results=k)

    docs = results["documents"][0]
    metas = results["metadatas"][0]

    excerpts = "\n\n".join(
        f"[{m['ticker']} | {m['source_doc']}]\n{d}" for d, m in zip(docs, metas)
    )

    resp = _anthropic().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": _FLAT_RAG_PROMPT.format(excerpts=excerpts, question=question)}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")

    return {
        "question": question,
        "retrieved": [{"source_doc": m["source_doc"], "ticker": m["ticker"]} for m in metas],
        "answer": text,
    }


def run() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("build", "query"):
        print('Usage: python -m src.retrieval.flat_rag build')
        print('       python -m src.retrieval.flat_rag query "question"')
        sys.exit(1)

    if sys.argv[1] == "build":
        build_index()
        return

    if len(sys.argv) < 3:
        print('Usage: python -m src.retrieval.flat_rag query "question"')
        sys.exit(1)

    result = answer(sys.argv[2])
    print(f"Q: {result['question']}\n")
    print("Retrieved chunks from:")
    for r in result["retrieved"]:
        print(f"  [{r['ticker']}] {r['source_doc']}")
    print()
    print(result["answer"])


if __name__ == "__main__":
    run()
