# Minimal Patch Summary — Backtest Window Semantics

## Scope

This patch is intentionally narrow. It only changes:

1. backtest window metadata recording;
2. backtest coverage summary reporting;
3. long-window report output wiring;
4. direct unit-test coverage for the new metadata fields;
5. documentation of the cleanup / delivery boundary.

It does **not** change:

- mark-to-market PnL logic;
- factor computation logic;
- future return generation;
- rebalance date selection rules.

## Files in this patch

### Code changes

- `app/domain/data_contracts.py`
- `app/domain/backtest/engine.py`
- `scripts/build_research_realism_stress.py`
- `scripts/run_growth_v3_long_window_backtest.py`

### Tests

- `tests/unit/domain/test_backtest_engine.py`

### Documentation

- `docs/reports/backtest-window-cleanup-2026-05-27.md`

## What changed

### 1. Structured window metadata

Added:

- `BacktestWindow`
- `BacktestCoverageSummary`

These explicitly separate:

- requested window;
- effective rebalance window;
- data coverage window;
- tail truncation counts / dates.

### 2. Payload additions only

`run_topn_backtest(...)` now adds:

- `backtest_window`
- `backtest_coverage_summary`

No existing payload keys were renamed or removed.

### 3. Realism-stress dataset wiring

`build_research_realism_stress.py` now injects:

- `requested_start_date`
- `requested_end_date`
- `data_start_date`
- `data_end_date`

into dataset attrs so the backtest payload can report honest window semantics.

### 4. Long-window script promoted from tmp to scripts

Formalized:

- `scripts/run_growth_v3_long_window_backtest.py`

It now writes requested/effective/data windows and coverage summary into the long-window report output.

### 5. Direct tests for new semantics

Added focused unit coverage for:

- requested/effective/data window population;
- tail truncation reporting;
- attr-missing fallback behavior;
- backward-compatible payload shape.

## Validation

Executed:

```bash
.venv/bin/python -m pytest tests/unit/domain/test_backtest_engine.py tests/unit/domain/test_data_contracts.py -q
```

Result:

```text
28 passed
```

## Commit intent

Recommended commit message:

```text
feat: add explicit backtest window coverage metadata
```

Optional longer body:

- add BacktestWindow / BacktestCoverageSummary
- expose requested/effective/data window fields in backtest payload
- promote long-window report script from tmp to scripts
- add direct unit coverage for window semantics
- document cleanup boundary and backup location
