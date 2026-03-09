"""
STEP 2 of the FlameIQ Quickstart — Produce a metrics file.

What this script does:
----------------------
This script benchmarks our TextCraft library and writes the results
as a FlameIQ v1 JSON file (benchmark.json).

Think of this as the "measurement step" — you are telling FlameIQ
"here is how fast my code is right now."

FlameIQ does NOT run your benchmarks for you. It reads the output.
Your job is to produce the metrics JSON. FlameIQ's job is to compare
it against the baseline and decide if something regressed.

The FlameIQ v1 schema requires:
  - schema_version: must be 1
  - metadata.commit: the git SHA of this run (for traceability)
  - metadata.branch: the git branch
  - metadata.environment: a label (ci, local, staging, etc.)
  - metrics: your actual measurements

Run this script:
    python benchmarks/step2_produce_metrics.py
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

# Make sure Python can find the textcraft package
sys.path.insert(0, str(Path(__file__).parent.parent))

from textcraft.processor import clean, summarise, word_frequency

# ── The text we will benchmark against ───────────────────────────────────────
# We repeat it 50 times so the benchmark runs on a realistic data size.
# A benchmark on 3 words is meaningless — you want real-world-sized input.
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

# How many times to call each function.
# More iterations = more stable numbers.
# 200 iterations is a good balance of speed and accuracy.
RUNS = 200


def get_git_info() -> tuple[str, str]:
    """Get the current git commit SHA and branch name.

    Why do we store this?
    Because when FlameIQ reports a regression, you want to know
    EXACTLY which commit introduced it. The commit SHA is your
    traceability link back to the code.
    """
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
        return "unknown", "unknown"


def measure(fn, *args, runs: int = RUNS) -> dict[str, float]:
    """Call fn(*args) for `runs` iterations and compute latency stats.

    Why percentiles (p50, p95, p99) instead of just the mean?
    ──────────────────────────────────────────────────────────
    The mean can be misleading. If 199 out of 200 calls take 2ms
    and 1 call takes 200ms, the mean looks fine (~3ms) but your
    users are occasionally experiencing 200ms responses.

    p95 means: "95% of calls completed within this time."
    p99 means: "99% of calls completed within this time."

    FlameIQ tracks p95 and p99 by default because regressions often
    show up in the tail (slow calls) before they affect the mean.
    """
    timings = []
    for _ in range(runs):
        start = time.perf_counter()
        fn(*args)
        end = time.perf_counter()
        timings.append((end - start) * 1000)  # convert seconds → milliseconds

    timings.sort()
    n = len(timings)

    return {
        "mean": round(statistics.mean(timings), 4),
        "p50":  round(timings[n // 2], 4),           # median — 50% of calls
        "p95":  round(timings[int(n * 0.95)], 4),    # 95th percentile
        "p99":  round(timings[int(n * 0.99)], 4),    # 99th percentile
    }


def main() -> None:
    print("=" * 60)
    print("  TextCraft Benchmark — Fast (Correct) Implementation")
    print("=" * 60)
    print()

    # ── Run all three functions ───────────────────────────────────────────────
    print("Measuring clean() ...")
    clean_stats = measure(clean, SAMPLE_TEXT)
    print(f"  mean={clean_stats['mean']}ms  p95={clean_stats['p95']}ms  p99={clean_stats['p99']}ms")

    print("Measuring word_frequency() ...")
    freq_stats = measure(word_frequency, SAMPLE_TEXT)
    print(f"  mean={freq_stats['mean']}ms  p95={freq_stats['p95']}ms  p99={freq_stats['p99']}ms")

    print("Measuring summarise() ...")
    summ_stats = measure(summarise, SAMPLE_TEXT)
    print(f"  mean={summ_stats['mean']}ms  p95={summ_stats['p95']}ms  p99={summ_stats['p99']}ms")

    # ── Throughput: calls per second ─────────────────────────────────────────
    # Throughput tells you how much work the function can do per second.
    # A drop in throughput means the function is slower overall.
    print("Measuring throughput ...")
    start = time.perf_counter()
    for _ in range(RUNS):
        clean(SAMPLE_TEXT)
    elapsed = time.perf_counter() - start
    throughput = round(RUNS / elapsed, 2)
    print(f"  {throughput} calls/sec")

    # ── Memory ───────────────────────────────────────────────────────────────
    # We measure the size of word_frequency()'s output dict as a proxy
    # for memory usage. In a real project you would use tracemalloc.
    result = word_frequency(SAMPLE_TEXT)
    memory_mb = round(sys.getsizeof(result) / (1024 * 1024), 6)
    print(f"  memory_mb={memory_mb}")

    # ── Build the FlameIQ v1 metrics snapshot ─────────────────────────────────
    # This is the exact shape FlameIQ expects.
    # The "custom" block lets you track any metric beyond the built-in ones.
    commit, branch = get_git_info()

    snapshot = {
        "schema_version": 1,
        "metadata": {
            "commit":      commit,
            "branch":      branch,
            "environment": "local",
        },
        "metrics": {
            "latency": clean_stats,          # latency of clean()
            "throughput": throughput,         # clean() calls per second
            "memory_mb":  memory_mb,          # output size proxy
            "custom": {
                # You can track any additional metrics here.
                # FlameIQ will apply thresholds to these too if configured.
                "word_frequency_p95_ms": freq_stats["p95"],
                "summarise_p95_ms":      summ_stats["p95"],
            },
        },
    }

    # ── Write to disk ─────────────────────────────────────────────────────────
    out = Path("benchmark.json")
    out.write_text(json.dumps(snapshot, indent=2))

    print()
    print("=" * 60)
    print(f"  ✓ Metrics written to {out}")
    print(f"  commit:      {commit}")
    print(f"  branch:      {branch}")
    print(f"  latency p95: {clean_stats['p95']} ms")
    print(f"  throughput:  {throughput} calls/sec")
    print("=" * 60)
    print()
    print("Next step:")
    print("  flameiq validate benchmark.json")
    print("  flameiq baseline set --metrics benchmark.json")


if __name__ == "__main__":
    main()
