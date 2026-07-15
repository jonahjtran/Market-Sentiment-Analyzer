"""Flat RAG baseline (PRD Phase 5 — comparator for the graph RAG demo).

Chunks the same filings/transcripts used by the graph pipeline into a
ChromaDB collection with standard embeddings and answers questions via plain
vector similarity search — no entity graph, no relationship traversal. This
is the "regular RAG fails" side of the Phase 6 side-by-side demo: it can only
surface whatever chunks are semantically close to the question, so it has no
structural way to reach entities that aren't named in the trigger document's
own text (e.g. it can't discover TSM is NVDA's supplier unless a chunk about
NVDA happens to mention TSM by name).

Run:
  python -m src.retrieval.flat_rag build
  python -m src.retrieval.flat_rag query "How does NVDA's earnings affect AMD, TSMC, and data center REITs?"
"""

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
COLLECTION_NAME = "filings_and_transcripts"

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


def build_index() -> int:
    """Chunk every filing/transcript in S3 and load them into ChromaDB."""
    collection = _get_collection()

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for prefix in ("filings", "transcripts"):
        for key in list_objects(prefix):
            if key.endswith("/"):
                continue
            ticker = _ticker_from_key(key)
            if ticker not in TICKERS:
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
Answer the question using only the excerpts below, which were retrieved by \
semantic similarity search over SEC filings and earnings releases. These \
excerpts are not a curated relationship graph — they are just the passages \
whose text is closest in meaning to the question. If the excerpts don't \
contain enough information to answer part of the question, say so rather \
than speculating.

Excerpts:
{excerpts}

Question: {question}
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
