"""
FlameIQ Demo — Single-session benchmark.

WHY this approach:
------------------
On local machines (especially WSL2), run-to-run variance is high.
A baseline measured in one terminal session and a comparison measured
in another session can differ by 30-60% purely due to:
  - CPU frequency scaling
  - OS scheduler decisions
  - Python interpreter warmup
  - Memory cache state

To make the regression reliably visible, we measure BOTH the fast
and regressed implementations in the SAME Python process, back to back,
with a shared warmup phase. This eliminates session variance entirely.

The fast implementation becomes the baseline.
The regressed implementation becomes current.json.
FlameIQ then compares them — and since they were measured under
identical conditions, the regression is unmistakable.

Usage:
    python benchmarks/benchmark_both.py
    flameiq baseline set --metrics baseline_fast.json
    flameiq compare --metrics current_regressed.json --fail-on-regression
    flameiq report --metrics current_regressed.json --output report.html
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from textcraft.processor import (
    clean as fast_clean,
    summarise as fast_summarise,
    word_frequency as fast_word_frequency,
)
from textcraft.processor_regressed import (
    clean as slow_clean,
    summarise as slow_summarise,
    word_frequency as slow_word_frequency,
)

# ── Corpus ────────────────────────────────────────────────────────────────────
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

WARMUP_RUNS  = 20   # throw these away — let Python and the CPU warm up
MEASURE_RUNS = 100  # actual timed iterations


def measure(fn, *args, runs: int = MEASURE_RUNS) -> dict[str, float]:
    """Time fn(*args) for `runs` iterations. Returns latency stats in ms."""
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


def throughput(fn, *args, runs: int = MEASURE_RUNS) -> float:
    """Measure calls per second."""
    start = time.perf_counter()
    for _ in range(runs):
        fn(*args)
    elapsed = time.perf_counter() - start
    return round(runs / elapsed, 2)


def build_snapshot(
    label: str,
    clean_stats: dict,
    freq_stats: dict,
    summ_stats: dict,
    tput: float,
) -> dict:
    """Build a FlameIQ v1 metrics snapshot."""
    memory_mb = round(sys.getsizeof(fast_word_frequency(SAMPLE_TEXT)) / (1024 * 1024), 6)
    return {
        "schema_version": 1,
        "metadata": {
            "commit":      label,
            "branch":      "main" if label == "fast" else "feature/refactor",
            "environment": "local",
        },
        "metrics": {
            "latency":    clean_stats,
            "throughput": tput,
            "memory_mb":  memory_mb,
            "custom": {
                "word_frequency_p95_ms": freq_stats["p95"],
                "summarise_p95_ms":      summ_stats["p95"],
            },
        },
    }


def separator(title: str) -> None:
    print()
    print("=" * 62)
    print(f"  {title}")
    print("=" * 62)


def main() -> None:
    # ── Warmup — discard results ──────────────────────────────────────────────
    separator("Warming up (discarded)")
    print(f"  Running {WARMUP_RUNS} warmup iterations for each function...")
    for _ in range(WARMUP_RUNS):
        fast_clean(SAMPLE_TEXT)
        fast_word_frequency(SAMPLE_TEXT)
        fast_summarise(SAMPLE_TEXT)
        slow_clean(SAMPLE_TEXT)
        slow_word_frequency(SAMPLE_TEXT)
        slow_summarise(SAMPLE_TEXT)
    print("  ✓ Warmup complete")

    # ── Fast implementation ───────────────────────────────────────────────────
    separator("FAST Implementation (baseline)")
    print(f"  Measuring {MEASURE_RUNS} iterations each...\n")

    print("  clean() ...")
    fast_clean_stats = measure(fast_clean, SAMPLE_TEXT)
    print(f"    mean={fast_clean_stats['mean']}ms  "
          f"p95={fast_clean_stats['p95']}ms  "
          f"p99={fast_clean_stats['p99']}ms")

    print("  word_frequency() ...")
    fast_freq_stats = measure(fast_word_frequency, SAMPLE_TEXT)
    print(f"    mean={fast_freq_stats['mean']}ms  "
          f"p95={fast_freq_stats['p95']}ms  "
          f"p99={fast_freq_stats['p99']}ms")

    print("  summarise() ...")
    fast_summ_stats = measure(fast_summarise, SAMPLE_TEXT)
    print(f"    mean={fast_summ_stats['mean']}ms  "
          f"p95={fast_summ_stats['p95']}ms  "
          f"p99={fast_summ_stats['p99']}ms")

    print("  throughput ...")
    fast_tput = throughput(fast_clean, SAMPLE_TEXT)
    print(f"    {fast_tput} calls/sec")

    # ── Regressed implementation ──────────────────────────────────────────────
    separator("REGRESSED Implementation (current)")
    print(f"  Measuring {MEASURE_RUNS} iterations each...\n")
    print("  NOTE: this will take longer — the regressions are severe.\n")

    print("  clean() [char-by-char loop + regex recompile] ...")
    slow_clean_stats = measure(slow_clean, SAMPLE_TEXT)
    print(f"    mean={slow_clean_stats['mean']}ms  "
          f"p95={slow_clean_stats['p95']}ms  "
          f"p99={slow_clean_stats['p99']}ms")

    print("  word_frequency() [O(n²) nested loop] ...")
    slow_freq_stats = measure(slow_word_frequency, SAMPLE_TEXT)
    print(f"    mean={slow_freq_stats['mean']}ms  "
          f"p95={slow_freq_stats['p95']}ms  "
          f"p99={slow_freq_stats['p99']}ms")

    print("  summarise() [re-sorts 100 times per call] ...")
    slow_summ_stats = measure(slow_summarise, SAMPLE_TEXT)
    print(f"    mean={slow_summ_stats['mean']}ms  "
          f"p95={slow_summ_stats['p95']}ms  "
          f"p99={slow_summ_stats['p99']}ms")

    print("  throughput ...")
    slow_tput = throughput(slow_clean, SAMPLE_TEXT)
    print(f"    {slow_tput} calls/sec")

    # ── Write metrics files ───────────────────────────────────────────────────
    separator("Writing metrics files")

    fast_snapshot = build_snapshot(
        "fast", fast_clean_stats, fast_freq_stats, fast_summ_stats, fast_tput
    )
    slow_snapshot = build_snapshot(
        "regressed", slow_clean_stats, slow_freq_stats, slow_summ_stats, slow_tput
    )

    Path("baseline_fast.json").write_text(json.dumps(fast_snapshot, indent=2))
    Path("current_regressed.json").write_text(json.dumps(slow_snapshot, indent=2))

    # ── Summary ───────────────────────────────────────────────────────────────
    separator("Summary — Fast vs Regressed")

    def pct(baseline: float, current: float) -> str:
        change = ((current - baseline) / baseline) * 100
        sign = "+" if change >= 0 else ""
        return f"{sign}{change:.1f}%"

    print(f"  {'Metric':<30} {'Fast':>10} {'Regressed':>12} {'Change':>10}")
    print(f"  {'-'*30} {'-'*10} {'-'*12} {'-'*10}")
    print(f"  {'latency.mean (ms)':<30} "
          f"{fast_clean_stats['mean']:>10} "
          f"{slow_clean_stats['mean']:>12} "
          f"{pct(fast_clean_stats['mean'], slow_clean_stats['mean']):>10}")
    print(f"  {'latency.p95 (ms)':<30} "
          f"{fast_clean_stats['p95']:>10} "
          f"{slow_clean_stats['p95']:>12} "
          f"{pct(fast_clean_stats['p95'], slow_clean_stats['p95']):>10}")
    print(f"  {'word_frequency.p95 (ms)':<30} "
          f"{fast_freq_stats['p95']:>10} "
          f"{slow_freq_stats['p95']:>12} "
          f"{pct(fast_freq_stats['p95'], slow_freq_stats['p95']):>10}")
    print(f"  {'summarise.p95 (ms)':<30} "
          f"{fast_summ_stats['p95']:>10} "
          f"{slow_summ_stats['p95']:>12} "
          f"{pct(fast_summ_stats['p95'], slow_summ_stats['p95']):>10}")
    print(f"  {'throughput (calls/sec)':<30} "
          f"{fast_tput:>10} "
          f"{slow_tput:>12} "
          f"{pct(fast_tput, slow_tput):>10}")

    print()
    print("  ✓ baseline_fast.json     → set this as your FlameIQ baseline")
    print("  ✓ current_regressed.json → compare this against the baseline")
    print()
    print("  Next steps:")
    print("    flameiq baseline set --metrics baseline_fast.json")
    print("    flameiq compare --metrics current_regressed.json --fail-on-regression")
    print("    flameiq report --metrics current_regressed.json --output report.html")


if __name__ == "__main__":
    main()
