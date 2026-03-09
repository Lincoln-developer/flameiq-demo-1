"""Benchmark for the REGRESSED version of TextCraft.

Produces a metrics.json that FlameIQ will compare against the baseline,
demonstrating how FlameIQ catches the performance regression.

Usage:
    python benchmarks/run_benchmark_regressed.py
    python benchmarks/run_benchmark_regressed.py --output metrics_regressed.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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

RUNS = 200


def _get_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "regressed"


def _get_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def bench(fn, *args, runs: int = RUNS) -> dict[str, float]:
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


def run_benchmarks() -> dict:
    print("Running benchmarks (regressed version)...")

    print("  → clean()  [regressed: recompiles regex every call]")
    clean_stats = bench(clean, SAMPLE_TEXT)

    print("  → word_frequency()  [regressed: manual loop instead of Counter]")
    freq_stats = bench(word_frequency, SAMPLE_TEXT)

    print("  → summarise()  [regressed: full re-sort every call]")
    summ_stats = bench(summarise, SAMPLE_TEXT)

    start = time.perf_counter()
    for _ in range(RUNS):
        clean(SAMPLE_TEXT)
    elapsed = time.perf_counter() - start
    throughput = round(RUNS / elapsed, 2)

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
    parser = argparse.ArgumentParser(description="TextCraft regressed benchmark")
    parser.add_argument("--output", "-o", default="metrics_regressed.json")
    args = parser.parse_args()

    snapshot = run_benchmarks()
    out = Path(args.output)
    out.write_text(json.dumps(snapshot, indent=2))

    print(f"\n✓ Regressed metrics written to {out}")
    print(f"  latency p95: {snapshot['metrics']['latency']['p95']} ms")
    print(f"  throughput:  {snapshot['metrics']['throughput']} calls/sec")


if __name__ == "__main__":
    main()
