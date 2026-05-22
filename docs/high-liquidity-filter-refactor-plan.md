# High-Liquidity Filter Refactor Plan

> **文档状态：历史方案**
> 
> 当前系统后续已转向 relative-liquidity tail pruning、filtered rerun 和 growth working config 路径；本文保留为当时探索“高流动性过滤重构”的历史方案背景。

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Raise the liquidity quality of the candidate research universe so the tracked growth/value candidates have a chance to survive realism and capacity constraints at more realistic capital scales.

**Architecture:** Do not redesign the whole research system. Add a stricter, explicit high-liquidity filter layer that can be reused by the tracked lines, then rerun the same review/realism/capacity chain on the filtered universe. This is a universe-quality intervention, not a new strategy family.

**Tech Stack:** Python, existing dataset builders, current review scripts, realism/capacity layers, JSON/Markdown reports.

---

## Why this is the right next step

Current system state now says something very specific:
- tracked candidates may still have research signal
- but current first-pass capacity constraints breach even at `model_small = 1,000,000`
- therefore the bottleneck is no longer just strategy ranking or role governance
- the bottleneck is the tradability quality of the selected names

So the next practical question is:

> Can we move the tracked system onto a higher-liquidity universe before giving up on these lines entirely?

---

## Scope of this refactor

### In scope
- define a reusable high-liquidity filter policy
- choose one or more candidate liquidity fields/thresholds
- apply it consistently to growth/value review pathways
- rerun the same downstream chain:
  - review
  - realism stress
  - capacity scan
- compare before vs after

### Out of scope
- inventing a new factor family
- redesigning allocator logic
- adding portfolio optimization
- changing role governance before post-refactor evidence exists

---

## Design principle

This refactor should be treated as:

> **universe-quality tightening**, not **signal-surface expansion**.

That means:
- keep the same tracked candidates
- keep the same decision-summary architecture
- keep the same realism/capacity framework
- only change the tradability floor of the candidate pool

---

## Candidate liquidity fields to use

Based on the current dataset inspection, available useful fields include:
- `amount`
- `volume`
- `close`

### Preferred primary field
Use `amount` as the first-pass high-liquidity gate.

Reason:
- it maps most directly to traded notional
- it is easier to connect to capacity logic than raw share volume

---

## Recommended high-liquidity filter structure

### Stage 1: absolute traded-amount floor
At the row/day level, require:

```text
amount >= liquidity_amount_floor
```

Candidate floor ladder to test:
- `300,000`
- `500,000`
- `1,000,000`

Reason:
- current capacity outputs imply that present selected holdings often sit far too low
- a floor ladder lets you test how much signal survives stricter tradability

---

### Stage 2: persistence / coverage requirement
Do not keep a stock in a candidate universe if it only occasionally clears the floor.

Example requirement:

```text
share_of_days_with_amount_above_floor >= 70%
```

This prevents one-off liquid spikes from passing the filter.

---

### Stage 3: optional rolling liquidity floor
Optional v2 refinement:

```text
rolling_20d_median_amount >= threshold
```

This is more stable than a single-day filter, but not required for v1 if implementation complexity rises.

---

## Recommended v1 rollout approach

### Phase A: simplest effective refactor
Start with:
1. `amount >= floor`
2. stock must satisfy the floor on a high enough share of days

### Why this first?
Because it is:
- simple
- explainable
- reusable
- directly tied to current capacity failures

---

## Suggested threshold-testing grid

Do not hard-commit to one threshold before seeing trade-offs.

### Recommended grid
Test at least:
- floor = `300,000`
- floor = `500,000`
- floor = `1,000,000`

and coverage requirement:
- `>= 70%`
- optionally `>= 80%`

### Compare on
For each threshold setting, compare:
1. candidate coverage loss
2. review performance change
3. realism change
4. capacity change

---

## Expected decision criteria

### Good outcome
- capacity breach materially improves
- realism improves
- review quality remains acceptable

### Bad outcome
- liquidity improves, but the signal disappears
- active coverage collapses too hard
- strategy becomes too sparse to remain meaningful

### Mixed outcome
- growth survives liquidity tightening
- value does not

If that happens, the system should say so explicitly rather than forcing both lines to remain symmetrical.

---

## Output files to add

### 1. Liquidity refactor comparison report
Create:
- `data/reports/high_liquidity_filter_refactor_<timestamp>.json`
- `data/reports/high_liquidity_filter_refactor_<timestamp>.md`

### 2. Optional supporting experiment reports
If needed:
- threshold-specific review comparison files
- threshold-specific capacity comparison files

---

## Proposed JSON schema (v1)

```json
{
  "report_type": "high_liquidity_filter_refactor",
  "generated_at": "2026-05-18T00:00:00+00:00",
  "base_context": {
    "tracked_growth": "revgrowth_always_on_v1",
    "tracked_value_primary": "pbindlow_downtrend_narrow_quality_v1",
    "tracked_value_reference": "pbindlow_downtrend_only_v1"
  },
  "tested_filters": [
    {
      "label": "amount_floor_300k_cov70",
      "amount_floor": 300000,
      "coverage_ratio_min": 0.70
    }
  ],
  "results": [
    {
      "label": "amount_floor_300k_cov70",
      "universe_effect": {
        "eligible_ticker_count": 0,
        "coverage_change_vs_base": 0.0
      },
      "growth_effect": {
        "review_status": "...",
        "realism_shift": "...",
        "capacity_shift": "..."
      },
      "value_effect": {
        "review_status": "...",
        "realism_shift": "...",
        "capacity_shift": "..."
      },
      "recommendation": "promising|too_destructive|needs_more_review"
    }
  ]
}
```

---

## Proposed Markdown structure

```md
# High-Liquidity Filter Refactor Summary

## Why this refactor exists
- ...

## Tested liquidity filters
| label | amount floor | coverage min |
|---|---:|---:|

## Universe effect
| label | eligible tickers | coverage change |
|---|---:|---:|

## Growth effect
- ...

## Value effect
- ...

## Recommendation
- ...
```

---

## Integration path

This refactor should plug into the current system in this order:

1. add high-liquidity universe filter
2. rerun tracked review windows on filtered universe
3. rerun realism stress
4. rerun capacity scan
5. compare pre/post
6. only then consider changing formal operating posture

Important rule:
- do not change governance identity/role just because the pre-refactor capacity scan was bad
- first test whether a more tradable universe rescues the line

---

## Recommended implementation file layout

### New script
Create:
- `scripts/run_high_liquidity_filter_refactor.py`

### Optional helper later
If logic grows:
- `app/services/high_liquidity_filter.py`

### Tests
Create:
- `tests/scripts/test_run_high_liquidity_filter_refactor.py`

---

## Implementation plan

### Task 1: Create filter experiment skeleton

**Objective:** Create a script that defines tested high-liquidity filter settings and emits a comparison report skeleton.

**Files:**
- Create: `scripts/run_high_liquidity_filter_refactor.py`
- Test: `tests/scripts/test_run_high_liquidity_filter_refactor.py`

**Step 1: Write failing test**
Assert top-level report keys exist:
- `report_type`
- `tested_filters`
- `results`

**Step 2: Run test to verify failure**
```bash
cd /root/project/quantsandbox_v2 && . .venv/bin/activate && pytest tests/scripts/test_run_high_liquidity_filter_refactor.py -q
```
Expected: FAIL.

**Step 3: Write minimal implementation**
Emit schema-valid skeleton.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_high_liquidity_filter_refactor.py tests/scripts/test_run_high_liquidity_filter_refactor.py
git commit -m "feat: add high-liquidity filter refactor skeleton"
```

### Task 2: Implement reusable high-liquidity stock filter

**Objective:** Build a reusable function that filters tickers by traded-amount floor and persistence.

**Files:**
- Modify: `scripts/run_high_liquidity_filter_refactor.py`
- Optional create: `app/services/high_liquidity_filter.py`
- Test: `tests/scripts/test_run_high_liquidity_filter_refactor.py`

**Step 1: Write failing test**
Assert that a fixture dataset keeps high-liquidity tickers and removes low-liquidity ones.

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Implement:
- `filter_high_liquidity_tickers(...)`
- amount floor
- minimum coverage ratio

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_high_liquidity_filter_refactor.py app/services/high_liquidity_filter.py tests/scripts/test_run_high_liquidity_filter_refactor.py
git commit -m "feat: add reusable high-liquidity ticker filter"
```

### Task 3: Compare universe effect across thresholds

**Objective:** Measure how much each liquidity filter setting shrinks the usable universe.

**Files:**
- Modify: `scripts/run_high_liquidity_filter_refactor.py`
- Test: `tests/scripts/test_run_high_liquidity_filter_refactor.py`

**Step 1: Write failing test**
Assert each threshold run returns:
- `eligible_ticker_count`
- `coverage_change_vs_base`

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Compute per-threshold universe effect summary.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_high_liquidity_filter_refactor.py tests/scripts/test_run_high_liquidity_filter_refactor.py
git commit -m "feat: add high-liquidity universe effect comparison"
```

### Task 4: Add tracked-line comparison hooks

**Objective:** For each tested filter setting, produce placeholder or real growth/value effect blocks so the report can become the basis for the next rerun cycle.

**Files:**
- Modify: `scripts/run_high_liquidity_filter_refactor.py`
- Test: `tests/scripts/test_run_high_liquidity_filter_refactor.py`

**Step 1: Write failing test**
Assert each result row contains:
- `growth_effect`
- `value_effect`
- `recommendation`

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Populate structure with conservative first-pass text or metrics placeholders.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_high_liquidity_filter_refactor.py tests/scripts/test_run_high_liquidity_filter_refactor.py
git commit -m "feat: add tracked-line effect scaffolding for liquidity refactor"
```

---

## Verification checklist

Before calling v1 done, verify:
- [ ] high-liquidity filter thresholds are explicit
- [ ] eligible universe count is reported
- [ ] multiple threshold settings are compared
- [ ] output clearly shows whether the refactor looks promising or too destructive
- [ ] no governance role changes are implied automatically

---

## Recommended follow-up after this refactor design

After implementation:
1. pick the most promising liquidity threshold setting
2. rerun growth/value review under that filtered universe
3. rerun realism and capacity scans
4. only then decide whether the tracked system can be promoted toward more realistic capital use
