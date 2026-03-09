"""TextCraft — a simple text processing library.

This is the library we are benchmarking with FlameIQ.
It has three functions: clean, word_frequency, and summarise.
"""

from __future__ import annotations

import re
from collections import Counter


def clean(text: str) -> str:
    """Remove punctuation, normalise whitespace, lowercase.

    This is a fast, single-pass implementation.
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def word_frequency(text: str) -> dict[str, int]:
    """Return a word frequency map for the given text."""
    words = clean(text).split()
    return dict(Counter(words))


def summarise(text: str, top_n: int = 5) -> list[str]:
    """Return the top N most frequent words in the text."""
    freq = word_frequency(text)
    sorted_words = sorted(freq, key=lambda w: freq[w], reverse=True)
    return sorted_words[:top_n]
