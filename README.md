# flameiq-demo

A minimal demo project showing [FlameIQ](https://pypi.org/project/flameiq-core/)
catching a real performance regression in a Python library.

## What this demo does

1. Benchmarks **TextCraft** — a simple text processing library
2. Sets a baseline with the fast, correct implementation
3. Introduces a regression (careless refactor that recompiles regex on every call)
4. Runs FlameIQ to catch the regression automatically
5. Generates an HTML report showing exactly which metrics degraded

## Setup

```bash
# Clone the demo
git clone https://github.com/Lincoln-developer/flameiq-demo-v4
cd flameiq-demo

# Install FlameIQ from PyPI
pip install flameiq-core

# Verify install
flameiq --version
```

## Full Walkthrough

### Step 1 — Initialise FlameIQ

```bash
flameiq init
```

This creates `.flameiq/` and `flameiq.yaml` in the current directory.
(A pre-configured `flameiq.yaml` is already included in this repo.)

### Step 2 — Run the baseline benchmark

```bash
python benchmarks/run_benchmark.py --output metrics_baseline.json
```

You will see output like:

```
Running benchmarks...
  → clean()
  → word_frequency()
  → summarise()

✓ Metrics written to metrics_baseline.json
  commit:      abc1234
  latency p95: 2.45 ms
  throughput:  412.3 calls/sec
```

### Step 3 — Set the baseline

```bash
flameiq baseline set --metrics metrics_baseline.json
```

```
✓ Baseline set
  Commit:  abc1234
  Branch:  main
  Metrics: 7 value(s) stored
```

### Step 4 — Show the baseline

```bash
flameiq baseline show
```

### Step 5 — Simulate a regression

A careless developer refactors `clean()` and accidentally recompiles
the regex on every call. Run the regressed benchmark:

```bash
python benchmarks/run_benchmark_regressed.py --output metrics_regressed.json
```

### Step 6 — Compare against baseline

```bash
flameiq compare --metrics metrics_regressed.json --fail-on-regression
```

FlameIQ will output something like:

```
  Metric                   Baseline      Current       Change  Threshold  Status
  ──────────────────────────────────────────────────────────────────────────────
  latency.mean               2.1200       3.8900      +83.49%     ±10.0%  REGRESSION
  latency.p50                2.0500       3.7200      +81.46%     ±10.0%  REGRESSION
  latency.p95                2.4500       4.5100      +84.08%     ±10.0%  REGRESSION
  latency.p99                2.8900       5.2300      +80.97%     ±15.0%  REGRESSION
  memory_mb                  0.0001       0.0001       +0.00%      ±8.0%  PASS
  throughput               412.30        231.50      -43.84%     ±10.0%  REGRESSION

  ✗ REGRESSION — 5 metric(s) exceeded threshold.
```

Exit code will be `1`, failing the CI pipeline.

### Step 7 — Generate an HTML report

```bash
flameiq report --metrics metrics_regressed.json --output report.html
```

Open `report.html` in your browser to see the full visual diff.

### Step 8 — Validate a metrics file

```bash
flameiq validate metrics_baseline.json
```

### Step 9 — View history

```bash
flameiq baseline show
```

## Project Structure

```
flameiq-demo/
├── textcraft/
│   ├── __init__.py
│   ├── processor.py             ← fast, correct implementation
│   └── processor_regressed.py  ← slow, regressed implementation
├── benchmarks/
│   ├── run_benchmark.py         ← benchmark the fast version
│   └── run_benchmark_regressed.py  ← benchmark the regressed version
├── flameiq.yaml                 ← FlameIQ configuration
└── README.md
```

## What the regression is

In `processor_regressed.py`, `clean()` recompiles two regex patterns
on every single call:

```python
# FAST (correct)
def clean(text):
    text = re.sub(r"[^\w\s]", "", text)   # regex compiled and cached by Python
    ...

# SLOW (regressed)
def clean(text):
    punct_re = re.compile(r"[^\w\s]")     # recompiled every call!
    space_re = re.compile(r"\s+")          # recompiled every call!
    ...
```

This is a classic, easy-to-miss Python performance mistake.
FlameIQ catches it automatically.

## Links

- **FlameIQ on PyPI:** https://pypi.org/project/flameiq-core/
- **FlameIQ docs:** https://flameiq-core.readthedocs.io
- **FlameIQ source:** https://github.com/flameiq/flameiq-core
