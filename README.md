# QuantSandbox v2

A minimal, trustworthy quant research system focused on a unified research → backtest → report loop.

## Phase 1 Goals

- Build a standardized research dataset
- Compute a small set of classic factors
- Run unified factor validation (IC / group analysis / sample split)
- Run unified TopN backtests with consistent benchmark and cost handling
- Persist tasks, experiments, and report indexes

## Project Layout

- `app/` application code
- `data/` local runtime data, cache, db, reports
- `tests/` unit and integration tests
- `scripts/` developer helpers
- `docs/` architecture and contracts

## Quick Start

```bash
cd /root/project/quantsandbox_v2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

## Current Scope

This repository is intentionally small at the start. We optimize for correctness, consistency, and traceability before breadth.
