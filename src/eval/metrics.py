"""Objective, market-data-free metrics for the graph-vs-flat comparison.

The headline metric is **answer-level entity recall**: of the neighbor
companies a correct multi-hop answer should surface, how many did the system
actually name in its answer? This is what a user sees, and it's computed the
same way for both systems, so it's a fair head-to-head.

A secondary **retrieval coverage** metric explains the *mechanism*: which
expected entities each system's retrieval layer even brought into view (graph =
the traversed subgraph's nodes; flat = the tickers of the chunks it retrieved).
Graph traversal reaches neighbors structurally; flat vector search reaches only
what is textually similar, so the coverage gap is where the recall gap is born.
"""

from __future__ import annotations

import re

from src.eval.test_set import ALIASES


def _alias_pattern(alias: str) -> re.Pattern:
    # Word-boundary, case-insensitive. Short all-caps tickers (AMD, TSM) must not
    # match inside longer words; multi-word names ("Taiwan Semiconductor") match
    # as a phrase.
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", re.IGNORECASE)


def mentioned_entities(text: str, candidates: list[str]) -> set[str]:
    """Return the subset of `candidates` (tickers) named anywhere in `text`."""
    if not text:
        return set()
    hits = set()
    for ticker in candidates:
        for alias in ALIASES.get(ticker, [ticker]):
            if _alias_pattern(alias).search(text):
                hits.add(ticker)
                break
    return hits


def entity_recall(text: str, expected: list[str]) -> dict:
    """Fraction of `expected` neighbor tickers named in `text`."""
    found = mentioned_entities(text, expected)
    return {
        "recall": len(found) / len(expected) if expected else 0.0,
        "found": sorted(found),
        "missed": sorted(set(expected) - found),
    }


def coverage(reached: set[str], expected: list[str]) -> dict:
    """Fraction of `expected` tickers the retrieval layer surfaced at all."""
    found = set(reached) & set(expected)
    return {
        "coverage": len(found) / len(expected) if expected else 0.0,
        "found": sorted(found),
    }
