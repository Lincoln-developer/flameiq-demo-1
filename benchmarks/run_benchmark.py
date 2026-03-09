"""FlameIQ benchmark for TextCraft.

Runs each function N times, computes latency stats,
and writes a FlameIQ v1 metrics JSON file.

Usage:
    python benchmarks/run_benchmark.py
    python benchmarks/run_benchmark.py --output metrics.json
    python benchmarks/run_benchmark.py --commit abc123
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path

# Add project root to path so we can import textcraft
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from textcraft.processor import clean, summarise, word_frequency

# ── Sample corpus ─────────────────────────────────────────────────────────────
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
""" * 50  # repeat to make benchmarks meaningful

RUNS = 200  # number of timed iterations per function


def _get_commit() -> str:
    """Get current git SHA or return 'unknown'."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _get_branch() -> str:
    """Get current git branch or return 'unknown'."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def bench(fn, *args, runs: int = RUNS) -> dict[str, float]:
    """Run fn(*args) for `runs` iterations and return latency stats in ms."""
    timings = []
    for _ in range(runs):
        start = time.perf_counter()
        fn(*args)
        end = time.perf_counter()
        timings.append((end - start) * 1000)  # convert to ms

    timings.sort()
    n = len(timings)
    return {
        "mean": round(statistics.mean(timings), 4),
        "p50":  round(timings[n // 2], 4),
        "p95":  round(timings[int(n * 0.95)], 4),
        "p99":  round(timings[int(n * 0.99)], 4),
    }


def run_benchmarks() -> dict:
    """Run all benchmarks and return a FlameIQ v1 snapshot dict."""
    print("Running benchmarks...")

    print("  → clean()")
    clean_stats = bench(clean, SAMPLE_TEXT)

    print("  → word_frequency()")
    freq_stats = bench(word_frequency, SAMPLE_TEXT)

    print("  → summarise()")
    summ_stats = bench(summarise, SAMPLE_TEXT)

    # Throughput: how many clean() calls per second
    start = time.perf_counter()
    for _ in range(RUNS):
        clean(SAMPLE_TEXT)
    elapsed = time.perf_counter() - start
    throughput = round(RUNS / elapsed, 2)

    # Memory: rough estimate via sys.getsizeof on output
    import sys
    result = word_frequency(SAMPLE_TEXT)
    memory_mb = round(sys.getsizeof(result) / (1024 * 1024), 4)

    return {
        "schema_version": 1,
        "metadata": {
            "commit": _get_commit(),
            "branch": _get_branch(),
            "environment": "local",
        },
        "metrics": {
            "latency": clean_stats,
            "throughput": throughput,
            "memory_mb": memory_mb,
            "custom": {
                "word_frequency_p95_ms": freq_stats["p95"],
                "summarise_p95_ms":      summ_stats["p95"],
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="TextCraft FlameIQ benchmark")
    parser.add_argument(
        "--output", "-o",
        default="metrics.json",
        help="Output path for metrics JSON (default: metrics.json)",
    )
    args = parser.parse_args()

    snapshot = run_benchmarks()

    out = Path(args.output)
    out.write_text(json.dumps(snapshot, indent=2))

    print(f"\n✓ Metrics written to {out}")
    print(f"  commit:     {snapshot['metadata']['commit']}")
    print(f"  latency p95: {snapshot['metrics']['latency']['p95']} ms")
    print(f"  throughput:  {snapshot['metrics']['throughput']} calls/sec")


if __name__ == "__main__":
    main()
