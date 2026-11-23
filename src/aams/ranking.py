"""Pure lexical scoring functions. No I/O, storage access or authorization.

Callers must pass only the authorized, time-visible candidates of one request. Corpus
statistics are then derived from data the principal may already read, so the scores
cannot reveal whether out-of-scope or later records exist.
"""

from collections import Counter
from collections.abc import Sequence
from enum import Enum
from math import log
from re import findall


class LexicalRanking(str, Enum):
    """Host-configured lexical ranker. ``BM25`` is the default; ``OVERLAP`` is legacy (v0.1–v0.7)."""

    OVERLAP = "overlap"
    BM25 = "bm25"


BM25_K1 = 1.2
BM25_B = 0.75


def tokens(text: str) -> list[str]:
    """Case-folded word tokens; the same tokenization as the overlap ranker."""
    return findall(r"[^\W_]+", text.casefold())


def bm25_scores(terms: frozenset[str], documents: Sequence[Counter[str]]) -> tuple[float, ...]:
    """Okapi BM25 of each document for the unique query ``terms``.

    IDF uses the non-negative ``log(1 + (N - df + 0.5) / (df + 0.5))`` form, so a matched
    term never lowers a score. A document scores zero only when it matches no term.
    """
    if not documents:
        return ()
    count = len(documents)
    lengths = [sum(document.values()) for document in documents]
    average = sum(lengths) / count or 1.0
    frequency = Counter(term for document in documents for term in terms if term in document)
    weights = {
        term: log(1 + (count - seen + 0.5) / (seen + 0.5)) for term, seen in frequency.items()
    }
    scores = []
    for document, length in zip(documents, lengths, strict=True):
        norm = BM25_K1 * (1 - BM25_B + BM25_B * length / average)
        scores.append(
            sum(
                weight * document[term] * (BM25_K1 + 1) / (document[term] + norm)
                for term, weight in weights.items()
                if term in document
            )
        )
    return tuple(scores)
