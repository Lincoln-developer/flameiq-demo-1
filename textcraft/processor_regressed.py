"""TextCraft — REGRESSED version of processor.py.

This file simulates THREE realistic performance regressions introduced
by a careless refactor. Each regression is a real mistake that happens
in production code — not an artificial slowdown.

Regression 1 — clean()
    The original uses re.sub() which benefits from Python's internal
    regex cache. The regressed version calls re.compile() explicitly
    on every single invocation, bypassing the cache entirely.
    Additionally, it processes the text character by character using
    a Python loop instead of letting the C-level regex engine do it.
    This is realistic: developers sometimes "optimise" by being explicit,
    not realising the cache exists.

Regression 2 — word_frequency()
    The original uses collections.Counter which is implemented in C.
    The regressed version replaces it with a pure Python nested loop
    that rebuilds the frequency map from scratch on every word,
    doing repeated full-dict scans — O(n²) instead of O(n).
    This is realistic: Counter is not always known to junior developers.

Regression 3 — summarise()
    The original sorts once and slices.
    The regressed version re-sorts the entire frequency map 100 times
    on every call, simulating a bug where a sort is inside a loop
    that was accidentally not cached.
    This is realistic: accidental repeated computation inside loops
    is one of the most common performance bugs in Python.
"""

from __future__ import annotations

import re


def clean(text: str) -> str:
    """Remove punctuation, normalise whitespace, lowercase.

    REGRESSED: two compiles on every call + character-by-character loop.
    """
    text = text.lower()

    # Regression: recompile regex on every call (bypasses Python's cache)
    punct_re = re.compile(r"[^\w\s]")
    space_re = re.compile(r"\s+")

    # Regression: character-by-character rebuild instead of re.sub()
    cleaned = []
    for char in text:
        if not punct_re.match(char):
            cleaned.append(char)
    text = "".join(cleaned)

    # Still uses re.sub for whitespace but with a freshly compiled pattern
    text = space_re.sub(" ", text).strip()
    return text


def word_frequency(text: str) -> dict[str, int]:
    """Return a word frequency map for the given text.

    REGRESSED: O(n²) nested loop instead of Counter.
    """
    words = clean(text).split()
    freq: dict[str, int] = {}

    for word in words:
        # Regression: rebuild count from scratch for every word
        # by scanning the entire word list again — O(n²)
        count = 0
        for w in words:
            if w == word:
                count += 1
        freq[word] = count

    return freq


def summarise(text: str, top_n: int = 5) -> list[str]:
    """Return the top N most frequent words in the text.

    REGRESSED: re-sorts the full frequency map 100 times on every call.
    """
    freq = word_frequency(text)

    # Regression: sort is inside a loop — result is thrown away
    # 99 times and only the last iteration is used.
    # This simulates a caching bug where an expensive operation
    # is repeated unnecessarily.
    sorted_words: list[str] = []
    for _ in range(100):
        sorted_words = sorted(freq, key=lambda w: freq[w], reverse=True)

    return sorted_words[:top_n]
