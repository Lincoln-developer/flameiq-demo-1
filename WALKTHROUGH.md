# FlameIQ Quickstart — Complete Walkthrough
## Understanding Your Project In and Out

---

## What is FlameIQ actually doing?

Before touching a single command, understand the mental model:

```
Your benchmark script          FlameIQ
──────────────────────         ──────────────────────────────────────
runs your code          →      reads the JSON output
measures how fast it is →      compares it to the stored baseline
writes metrics.json     →      reports which metrics regressed
                               exits 1 if regression, 0 if pass
```

FlameIQ is NOT a benchmarking framework. It does not time your code.
It reads the results of YOUR timing and makes a decision: pass or fail.

This separation is intentional. You control how you measure.
FlameIQ controls what happens after the measurement.

---

## The Project Structure

```
flameiq-demo/
│
├── textcraft/
│   ├── processor.py              ← FAST version (the correct code)
│   └── processor_regressed.py   ← SLOW version (the buggy code)
│
├── benchmarks/
│   ├── step2_produce_metrics.py           ← benchmarks the fast version
│   └── step4_produce_regressed_metrics.py ← benchmarks the slow version
│
├── flameiq.yaml    ← tells FlameIQ what thresholds to enforce
└── .flameiq/       ← FlameIQ stores baselines and history here (created by init)
```

---

## Step 1 — Install FlameIQ

```bash
pip install flameiq-core
```

Verify it worked:

```bash
flameiq --version
# flameiq-core, version 1.0.2
```

**What just happened?**
You installed a CLI tool called `flameiq` with six commands:
`init`, `run`, `baseline`, `compare`, `validate`, `report`.
That is the entire public surface of FlameIQ.

---

## Step 2 — Initialise FlameIQ in your project

```bash
cd flameiq-demo
flameiq init
```

**What just happened?**

FlameIQ created two things:

1. `flameiq.yaml` — your configuration file. This is where you define
   what metrics to track and how much change is acceptable.

2. `.flameiq/` — a local directory where FlameIQ stores:
   - `baselines/current.json` — the active baseline
   - `history.jsonl`          — a log of every run (one JSON object per line)

**Add `.flameiq/` to your `.gitignore`:**
```bash
echo ".flameiq/" >> .gitignore
```
Why? Because baselines are environment-specific. A baseline measured on
your laptop is not valid for CI. CI should set and compare its own baselines.

**The flameiq.yaml file explained:**
```yaml
thresholds:
  latency.p95:  10%   # if p95 latency increases by more than 10% → REGRESSION
  latency.p99:  15%   # wider tolerance for the very tail (p99)
  throughput:   -5%   # if throughput drops by more than 5% → REGRESSION
  memory_mb:     8%   # if memory increases by more than 8% → REGRESSION

baseline:
  strategy: rolling_median   # use the median of the last N runs as baseline
  rolling_window: 5          # look at the last 5 runs

statistics:
  enabled: false    # set to true for noisy CI environments
  confidence: 0.95  # 95% statistical confidence when enabled

provider: json      # we are feeding FlameIQ raw JSON files
```

The thresholds block is the most important part. It answers:
"How much degradation is acceptable before we fail the pipeline?"

---

## Step 3 — Produce your first metrics file

This step runs the FAST (correct) version of TextCraft and writes
the results to `benchmark.json`.

```bash
python benchmarks/step2_produce_metrics.py
```

You will see output like:
```
============================================================
  TextCraft Benchmark — Fast (Correct) Implementation
============================================================

Measuring clean() ...
  mean=2.1200ms  p95=2.4500ms  p99=2.8900ms
Measuring word_frequency() ...
  mean=3.8100ms  p95=4.1200ms  p99=4.5600ms
Measuring summarise() ...
  mean=4.0300ms  p95=4.3800ms  p99=4.9100ms
Measuring throughput ...
  412.30 calls/sec

============================================================
  ✓ Metrics written to benchmark.json
  commit:      abc1234
  branch:      main
  latency p95: 2.45 ms
  throughput:  412.30 calls/sec
============================================================
```

**What just happened?**

The script ran each TextCraft function 200 times, measured how long
each call took, and computed latency statistics (mean, p50, p95, p99).

It then wrote `benchmark.json` — a FlameIQ v1 schema file:

```json
{
  "schema_version": 1,
  "metadata": {
    "commit": "abc1234",
    "branch": "main",
    "environment": "local"
  },
  "metrics": {
    "latency": {
      "mean": 2.12,
      "p50":  2.05,
      "p95":  2.45,
      "p99":  2.89
    },
    "throughput": 412.30,
    "memory_mb":  0.000124,
    "custom": {
      "word_frequency_p95_ms": 4.12,
      "summarise_p95_ms":      4.38
    }
  }
}
```

**Why p95 and p99?**
The mean hides tail latency. If 195 out of 200 calls take 2ms but
5 calls take 50ms, the mean looks fine (~3.2ms) but your users are
occasionally hitting 50ms responses. p95 catches those slow calls.

---

## Step 4 — Validate the metrics file

Before setting a baseline, always validate your metrics file:

```bash
flameiq validate benchmark.json
```

Expected output:
```
✓ Valid — 7 metrics found in benchmark.json
```

**What just happened?**

FlameIQ checked that `benchmark.json` conforms to the v1 schema:
- `schema_version` is present and equals 1
- `metadata` has the required fields
- `metrics` contains at least one value
- All values are numbers (not strings, not nulls)

If you had a typo in the JSON or passed the wrong file, this command
catches it before it corrupts your baseline.

---

## Step 5 — Set the baseline

You are on `main`, your code is correct and fast.
Tell FlameIQ: "this is the reference — compare everything against this."

```bash
flameiq baseline set --metrics benchmark.json
```

Expected output:
```
✓ Baseline set
  Strategy: last_successful
  Commit:   abc1234
  Metrics:  7 values stored
```

**What just happened?**

FlameIQ read `benchmark.json` and stored it as the active baseline in
`.flameiq/baselines/current.json`. It also appended an entry to
`.flameiq/history.jsonl`.

From this point on, every `flameiq compare` will measure the distance
between the current metrics and these stored values.

**Show the baseline:**
```bash
flameiq baseline show
```

---

## Step 6 — Introduce a regression

A developer "refactors" `clean()` and accidentally recompiles
the regex on every call. This is the regressed version in
`textcraft/processor_regressed.py`.

The two versions look nearly identical:

```python
# FAST — processor.py (correct)
def clean(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)   # Python caches this pattern
    text = re.sub(r"\s+", " ", text).strip()
    return text

# SLOW — processor_regressed.py (regressed)
def clean(text: str) -> str:
    text = text.lower()
    punct_re = re.compile(r"[^\w\s]")     # recompiled on EVERY call!
    space_re = re.compile(r"\s+")          # recompiled on EVERY call!
    text = punct_re.sub("", text)
    text = space_re.sub(" ", text).strip()
    return text
```

The output is identical. The tests pass. The code review looks clean.
But every single call now pays the cost of compiling two regex patterns.

Now run the regressed benchmark:

```bash
python benchmarks/step4_produce_regressed_metrics.py
```

This writes `current.json` with the slower numbers.

---

## Step 7 — Compare and catch the regression

```bash
flameiq compare --metrics current.json --fail-on-regression
```

Expected output:
```
  Metric                     Baseline    Current     Change    Threshold  Status
  ──────────────────────────────────────────────────────────────────────────────
  latency.mean                 2.1200      3.8900    +83.49%      ±10.0%  REGRESSION
  latency.p50                  2.0500      3.7200    +81.46%      ±10.0%  REGRESSION
  latency.p95                  2.4500      4.5100    +84.08%      ±10.0%  REGRESSION
  latency.p99                  2.8900      5.2300    +80.97%      ±15.0%  REGRESSION
  throughput                 412.3000    231.5000    -43.84%      ±10.0%  REGRESSION
  memory_mb                    0.0001      0.0001     +0.00%       ±8.0%  PASS
  custom.word_frequency_p95    4.1200      7.8900    +91.50%      ±10.0%  REGRESSION

  ✗ REGRESSION — 6 metric(s) exceeded threshold.
```

**Exit code: 1** — the pipeline fails.

**What FlameIQ is telling you:**
- latency.p95 went from 2.45ms → 4.51ms (+84%) — well above the 10% threshold
- throughput dropped from 412 → 231 calls/sec (-43%) — well above the 5% threshold
- memory_mb did not change — PASS
- The regression is in 6 out of 7 tracked metrics

This is exactly the information you need to go back, find the commit,
and revert the change before it reaches production.

---

## Step 8 — Generate an HTML report

```bash
flameiq report --metrics current.json --output report.html
```

Open `report.html` in your browser.

**What the report contains:**
- A full metric diff table (baseline vs current vs threshold)
- Regression highlights in red
- Trend history if you have multiple runs
- No internet connection required — fully self-contained HTML

---

## Step 9 — Fix the regression and advance the baseline

Once the developer reverts their change and `clean()` is fast again,
re-run the fast benchmark and update the baseline:

```bash
python benchmarks/step2_produce_metrics.py
flameiq baseline set --metrics benchmark.json
```

The new baseline replaces the old one. History is preserved in
`.flameiq/history.jsonl` — you can always look back.

---

## The Full Command Reference

```bash
flameiq init
# Creates flameiq.yaml and .flameiq/ in the current directory.

flameiq validate <metrics.json>
# Checks that a metrics file conforms to the v1 schema.
# Always run this before setting a baseline.

flameiq baseline set --metrics <metrics.json>
# Stores the metrics file as the active baseline.
# Run this on your stable branch after a passing CI run.

flameiq baseline show
# Prints the current active baseline to the terminal.

flameiq compare --metrics <current.json> [--fail-on-regression]
# Compares current.json against the stored baseline.
# Exits 0 if all metrics pass, 1 if any regression is detected.
# --fail-on-regression is what makes CI fail.

flameiq report --metrics <current.json> --output <report.html>
# Generates a self-contained HTML performance report.

flameiq run
# Runs the provider-specific benchmark and produces metrics.json.
# (Advanced — for when you want FlameIQ to drive the benchmark run)
```

---

## GitHub Actions CI Integration

```yaml
name: CI

on: [push, pull_request]

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install flameiq-core
          pip install -e .

      - name: Restore baseline cache
        uses: actions/cache@v4
        with:
          path: .flameiq/
          key: flameiq-${{ github.base_ref }}

      - name: Run benchmarks
        run: python benchmarks/step2_produce_metrics.py

      - name: Validate metrics
        run: flameiq validate benchmark.json

      - name: Set baseline (main branch only)
        if: github.ref == 'refs/heads/main'
        run: flameiq baseline set --metrics benchmark.json

      - name: Compare against baseline (PRs only)
        if: github.event_name == 'pull_request'
        run: flameiq compare --metrics benchmark.json --fail-on-regression

      - name: Generate report
        if: always()
        run: flameiq report --metrics benchmark.json --output report.html

      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: performance-report
          path: report.html
```

**How the CI flow works:**

- On `main`: run benchmarks → set baseline → cache it
- On PR: restore baseline from cache → run benchmarks → compare → fail if regression
- Always: generate HTML report and upload as CI artifact

---

## Summary — What You Built

You now have a complete performance regression gate:

1. **TextCraft** — a real Python library with benchmarkable functions
2. **Benchmark scripts** — measure latency, throughput, and memory
3. **FlameIQ baseline** — the reference measurement on fast code
4. **FlameIQ compare** — catches the regex regression automatically
5. **HTML report** — human-readable diff of every metric
6. **CI integration** — the gate runs on every pull request

The regex regression introduced an 84% latency increase.
FlameIQ caught it. Exit code 1. Pipeline failed. Regression blocked.

**That is FlameIQ working exactly as designed.**
