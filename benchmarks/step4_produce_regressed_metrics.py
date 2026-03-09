r"""
STEP 4 of the FlameIQ Quickstart — Simulate a regression and compare.

What this script does:
----------------------
This script benchmarks the REGRESSED version of TextCraft and writes
the results to current.json.

You will then run:
    flameiq compare --metrics current.json --fail-on-regression

And FlameIQ will compare current.json against the baseline you set
in Step 3 and report which metrics regressed.

The regression we introduced:
──────────────────────────────
In textcraft/processor_regressed.py, the clean() function was
"refactored" in a way that recompiles two regex patterns on every
single call:

    BEFORE (fast):
        re.sub(r"[^\w\s]", "", text)
        # Python's re module caches compiled patterns automatically.
        # The pattern is compiled once and reused on every call.

    AFTER (regressed):
        punct_re = re.compile(r"[^\w\s]")   # compiled fresh every call
        space_re = re.compile(r"\s+")         # compiled fresh every call

This is one of the most common Python performance mistakes.
It is completely invisible in code review — the logic is identical,
the output is identical, the tests pass. Only a performance benchmark
catches it.

FlameIQ's job is to catch exactly this.

Run this script:
    python benchmarks/step4_produce_regressed_metrics.py
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Note: we import from processor_REGRESSED — the slow version
from textcraft.processor_regressed import clean, summarise, word_frequency

SAMPLE_TEXT = """
FlameIQ is a deterministic, CI-native performance regression engine.
It makes performance a first-class, enforceable engineering signal.
Performance regressions are rarely caught in code review.
They accumulate silently across hundreds of commits.
A three millisecond latency increase here, a two percent throughput drop there,
until they become expensive production incidents.
FlameIQ brings the same engineering discipline to performance that type checkers
bring to correctness: automated, deterministic, and CI-enforced.
No SaaS platform required. No cloud account. No vendor dependency.
Fully offline. Fully air-gap compatible. Fully deterministic.
""" * 50

RUNS = 50   # reduced from 200 — regressions are severe enough for 50 runs


def get_git_info() -> tuple[str, str]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return commit, branch
    except Exception:
        return "regressed", "feature/refactor-clean"


def measure(fn, *args, runs: int = RUNS) -> dict[str, float]:
    timings = []
    for _ in range(runs):
        start = time.perf_counter()
        fn(*args)
        end = time.perf_counter()
        timings.append((end - start) * 1000)

    timings.sort()
    n = len(timings)

    return {
        "mean": round(statistics.mean(timings), 4),
        "p50":  round(timings[n // 2], 4),
        "p95":  round(timings[int(n * 0.95)], 4),
        "p99":  round(timings[int(n * 0.99)], 4),
    }


def main() -> None:
    print("=" * 60)
    print("  TextCraft Benchmark — REGRESSED Implementation")
    print("  (regex recompiled on every call)")
    print("=" * 60)
    print()

    print("Measuring clean() [regressed: char-by-char loop + regex recompile] ...")
    clean_stats = measure(clean, SAMPLE_TEXT)
    print(f"  mean={clean_stats['mean']}ms  p95={clean_stats['p95']}ms  p99={clean_stats['p99']}ms")

    print("Measuring word_frequency() [regressed: O(n²) nested loop] ...")
    freq_stats = measure(word_frequency, SAMPLE_TEXT)
    print(f"  mean={freq_stats['mean']}ms  p95={freq_stats['p95']}ms  p99={freq_stats['p99']}ms")

    print("Measuring summarise() [regressed: re-sorts 100 times per call] ...")
    summ_stats = measure(summarise, SAMPLE_TEXT)
    print(f"  mean={summ_stats['mean']}ms  p95={summ_stats['p95']}ms  p99={summ_stats['p99']}ms")

    print("Measuring throughput [regressed] ...")
    start = time.perf_counter()
    for _ in range(RUNS):
        clean(SAMPLE_TEXT)
    elapsed = time.perf_counter() - start
    throughput = round(RUNS / elapsed, 2)
    print(f"  {throughput} calls/sec")

    result = word_frequency(SAMPLE_TEXT)
    memory_mb = round(sys.getsizeof(result) / (1024 * 1024), 6)

    commit, branch = get_git_info()

    snapshot = {
        "schema_version": 1,
        "metadata": {
            "commit":      commit,
            "branch":      branch,
            "environment": "local",
        },
        "metrics": {
            "latency":    clean_stats,
            "throughput": throughput,
            "memory_mb":  memory_mb,
            "custom": {
                "word_frequency_p95_ms": freq_stats["p95"],
                "summarise_p95_ms":      summ_stats["p95"],
            },
        },
    }

    out = Path("current.json")
    out.write_text(json.dumps(snapshot, indent=2))

    print()
    print("=" * 60)
    print(f"  ✓ Regressed metrics written to {out}")
    print(f"  commit:      {commit}")
    print(f"  latency p95: {clean_stats['p95']} ms")
    print(f"  throughput:  {throughput} calls/sec")
    print("=" * 60)
    print()
    print("Next step — let FlameIQ catch the regression:")
    print("  flameiq compare --metrics current.json --fail-on-regression")


if __name__ == "__main__":
    main()
