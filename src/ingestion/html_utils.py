"""Lightweight HTML-to-text helpers for filing documents.

10-Ks and earnings exhibits are large HTML blobs. We strip them to plain text
and then narrow to the passages that actually discuss relationships, so the LLM
extraction step stays cheap and focused instead of ingesting whole filings.
"""

import html
import re

_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_IX_HEADER = re.compile(r"<ix:header\b.*?</ix:header>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n\s*")

# Terms that flag passages describing inter-company relationships.
RELATIONSHIP_KEYWORDS = (
    "customer",
    "supplier",
    "supply",
    "compet",  # compete / competes / competitor / competition / competitive
    "partner",
    "foundry",
    "manufactur",
    "vendor",
    "concentration",
    "rely on",
    "depend on",
)


def html_to_text(raw: str) -> str:
    """Strip HTML markup and collapse whitespace into readable plain text."""
    text = _IX_HEADER.sub(" ", raw)
    text = _SCRIPT_STYLE.sub(" ", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = _WS.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def relationship_windows(
    text: str, window: int = 1200, max_chars: int = 40_000
) -> str:
    """Extract passages around relationship keywords, capped at `max_chars`.

    Merges overlapping windows so we don't feed the LLM duplicated context.
    Returns the whole text (truncated) if no keyword hits are found.
    """
    lowered = text.lower()
    spans: list[tuple[int, int]] = []
    for kw in RELATIONSHIP_KEYWORDS:
        start = 0
        while True:
            idx = lowered.find(kw, start)
            if idx == -1:
                break
            spans.append((max(0, idx - window), min(len(text), idx + window)))
            start = idx + len(kw)

    if not spans:
        return text[:max_chars]

    spans.sort()
    merged: list[list[int]] = [list(spans[0])]
    for lo, hi in spans[1:]:
        if lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])

    out: list[str] = []
    total = 0
    for lo, hi in merged:
        chunk = text[lo:hi]
        if total + len(chunk) > max_chars:
            out.append(chunk[: max_chars - total])
            break
        out.append(chunk)
        total += len(chunk)
    return "\n\n[...]\n\n".join(out)
