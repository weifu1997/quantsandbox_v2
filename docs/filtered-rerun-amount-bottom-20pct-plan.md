# Filtered Rerun Chain Plan (`amount_bottom_20pct`)

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Use the most promising relative-liquidity pruning setting (`amount_bottom_20pct`) as the first full filtered rerun configuration, so growth/value candidates can be reevaluated under a tradability-aware universe rather than the original broad universe.

**Architecture:** Keep the existing review → realism → capacity pipeline intact and insert one reusable filtered-universe stage before candidate review runs. Do not fork the entire system into a second architecture. Treat this as one experiment configuration that feeds the same downstream chain.

**Tech Stack:** Python, existing review scripts, current realism and capacity scripts, JSON/Markdown reports.

---

## Why this is the correct next step

The system now knows three things:

1. hard liquidity floors are too destructive
2. relative liquidity tail pruning is much more survivable
3. `amount_bottom_20pct` is the current best balance between tradability tightening and universe retention

So the next practical question is:

> After applying `amount_bottom_20pct`, do the tracked growth/value lines actually improve when we rerun the downstream chain?

This cannot be answered by retention stats alone.
It requires a real rerun chain.

---

## Current selected experiment configuration

Use this as the first filtered rerun setting:

```json
{
  "label": "amount_bottom_20pct",
  "field": "amount",
  "method": "cross_sectional_tail_prune",
  "tail_cut": 0.20
}
```

This becomes the canonical first filtered rerun config.

---

## Desired rerun chain

For this one filtered configuration, rerun in order:

1. filtered universe build
2. growth/value candidate review inputs under filtered universe
3. realism stress under filtered universe
4. capacity constraints under filtered universe
5. comparison summary vs base universe

---

## Output files

### Main comparison report
Create:
- `data/reports/filtered_rerun_amount_bottom_20pct_<timestamp>.json`
- `data/reports/filtered_rerun_amount_bottom_20pct_<timestamp>.md`

### Optional supporting artifacts
If implementation chooses to persist them separately, allow:
- filtered review snapshots
- filtered realism snapshot
- filtered capacity snapshot

But the main report should summarize all of them.

---

## Proposed JSON schema (v1)

```json
{
  "report_type": "filtered_rerun_chain",
  "generated_at": "2026-05-18T00:00:00+00:00",
  "filter_config": {
    "label": "amount_bottom_20pct",
    "field": "amount",
    "method": "cross_sectional_tail_prune",
    "tail_cut": 0.20
  },
  "universe_effect": {
    "retained_fraction": 0.80,
    "eligible_ticker_count": 0
  },
  "growth_line": {
    "review_effect": "...",
    "realism_effect": "...",
    "capacity_effect": "..."
  },
  "valuation_line": {
    "review_effect": "...",
    "realism_effect": "...",
    "capacity_effect": "..."
  },
  "comparison_summary": {
    "growth_improved": false,
    "value_improved": false,
    "capacity_improved": false,
    "net_assessment": "promising|mixed|not_enough"
  }
}
```

---

## Proposed Markdown structure

```md
# Filtered Rerun Chain Summary

## Filter configuration
- ...

## Universe retention
- ...

## Growth line effect
- review: ...
- realism: ...
- capacity: ...

## Valuation line effect
- review: ...
- realism: ...
- capacity: ...

## Net assessment
- ...
```

---

## Recommended implementation file layout

### New script
Create:
- `scripts/run_filtered_rerun_amount_bottom_20pct.py`

### Optional helper later
If logic grows:
- `app/services/filtered_rerun_chain.py`

### Tests
Create:
- `tests/scripts/test_run_filtered_rerun_amount_bottom_20pct.py`

---

## Implementation strategy

### Important implementation constraint
Do **not** duplicate all review/realism/capacity logic in a new fork.
Instead:
- reuse the same candidate definitions
- reuse the same downstream computation patterns
- only inject the filtered universe as the changed input surface

---

## Implementation plan

### Task 1: Create rerun chain skeleton

**Objective:** Create the filtered-rerun report skeleton and top-level schema.

**Files:**
- Create: `scripts/run_filtered_rerun_amount_bottom_20pct.py`
- Test: `tests/scripts/test_run_filtered_rerun_amount_bottom_20pct.py`

**Step 1: Write failing test**
Assert top-level keys exist:
- `report_type`
- `filter_config`
- `comparison_summary`

**Step 2: Run test to verify failure**
```bash
cd /root/project/quantsandbox_v2 && . .venv/bin/activate && pytest tests/scripts/test_run_filtered_rerun_amount_bottom_20pct.py -q
```
Expected: FAIL.

**Step 3: Write minimal implementation**
Emit schema-valid skeleton.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_filtered_rerun_amount_bottom_20pct.py tests/scripts/test_run_filtered_rerun_amount_bottom_20pct.py
git commit -m "feat: add filtered rerun chain skeleton for amount_bottom_20pct"
```

### Task 2: Reuse the relative-liquidity selector

**Objective:** Resolve the filtered universe from the existing tail-pruning logic.

**Files:**
- Modify: `scripts/run_filtered_rerun_amount_bottom_20pct.py`
- Test: `tests/scripts/test_run_filtered_rerun_amount_bottom_20pct.py`

**Step 1: Write failing test**
Assert the script records:
- `retained_fraction`
- `eligible_ticker_count`

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Reuse the `amount_bottom_20pct` filter to produce the filtered universe.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_filtered_rerun_amount_bottom_20pct.py tests/scripts/test_run_filtered_rerun_amount_bottom_20pct.py
git commit -m "feat: resolve filtered universe for amount_bottom_20pct rerun chain"
```

### Task 3: Add downstream effect scaffolding

**Objective:** Record placeholders or simple comparative outcomes for growth/value review, realism, and capacity.

**Files:**
- Modify: `scripts/run_filtered_rerun_amount_bottom_20pct.py`
- Test: `tests/scripts/test_run_filtered_rerun_amount_bottom_20pct.py`

**Step 1: Write failing test**
Assert output contains:
- `growth_line.review_effect`
- `growth_line.realism_effect`
- `valuation_line.capacity_effect`

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Populate conservative text blocks or basic comparison placeholders without yet recomputing the full deep chain.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_filtered_rerun_amount_bottom_20pct.py tests/scripts/test_run_filtered_rerun_amount_bottom_20pct.py
git commit -m "feat: add downstream effect scaffolding for filtered rerun chain"
```

### Task 4: Add net assessment

**Objective:** Produce one explicit top-level judgment for this filtered-rerun experiment.

**Files:**
- Modify: `scripts/run_filtered_rerun_amount_bottom_20pct.py`
- Test: `tests/scripts/test_run_filtered_rerun_amount_bottom_20pct.py`

**Step 1: Write failing test**
Assert:
- `comparison_summary.net_assessment`
- recommendation-like outcome exists

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Map retention and placeholder downstream expectations into:
- `promising`
- `mixed`
- `not_enough`

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_filtered_rerun_amount_bottom_20pct.py tests/scripts/test_run_filtered_rerun_amount_bottom_20pct.py
git commit -m "feat: add net assessment for filtered rerun chain"
```

---

## Verification checklist

Before calling v1 done, verify:
- [ ] filter config is explicit
- [ ] universe retention is recorded
- [ ] growth/value downstream effect blocks exist
- [ ] comparison summary gives one net assessment
- [ ] implementation reuses the selected `amount_bottom_20pct` path instead of inventing a parallel liquidity system

---

## Recommended follow-up after this implementation

After this v1 scaffolding lands:
1. replace placeholders with true rerun metrics step by step
2. compare against base decision summary / realism / capacity reports
3. only then decide whether `amount_bottom_20pct` is strong enough to justify becoming the next tradability-aware experimental default
