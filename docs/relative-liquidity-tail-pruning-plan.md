# Relative Liquidity Tail-Pruning Plan

> **文档状态：部分实现**
> 
> relative-liquidity pruning 的核心方向已经进入当前 filtered universe / growth universe 工件链路，但本文仍包含原始设计与试验性描述，因此标记为“部分实现”。

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Replace the overly destructive hard liquidity floors with a gentler relative-liquidity pruning method that removes the worst liquidity tail while preserving enough universe breadth for the tracked growth/value lines to remain research-meaningful.

**Architecture:** Keep the current research stack intact. Add a relative-liquidity filter or weighting layer that works within the current universe rather than replacing it with a tiny absolute-liquidity subset. This should be implemented as a controlled pre-portfolio selection step and evaluated using the same review/realism/capacity chain already in place.

**Tech Stack:** Python, existing dataset builders, current review scripts, realism/capacity layers, JSON/Markdown reports.

---

## Why this plan exists

The hard-liquidity floor experiment established a useful negative result:
- `amount >= 300k/500k/1000k` plus coverage gating is too destructive
- universe shrink is so extreme that the strategy layer may become meaningless before tradability improves

So the next question is not:
- how do we raise the absolute floor further?

The next question is:

> Can we remove only the worst liquidity tail and keep enough breadth for the tracked lines to survive?

---

## Core design principle

This is a **tail-pruning** intervention, not a **hard tradability wall**.

That means:
- remove the worst liquidity names relative to peers
- preserve a workable fraction of the universe
- test whether capacity improves without destroying signal breadth

---

## Candidate relative-liquidity fields

Preferred first-pass field:
- `amount`

Optional later refinement:
- rolling median `amount`
- rolling average `amount`
- cross-sectional liquidity rank persistence

---

## Recommended v1 methods

### Method A: cross-sectional bottom-tail pruning
On each date, compute cross-sectional rank of `amount` and remove the bottom tail.

Candidate tail cuts to test:
- bottom 10%
- bottom 20%
- bottom 30%

This is the simplest and most interpretable v1 design.

---

### Method B: rolling-liquidity rank pruning
Use each stock's rolling 20d median `amount`, then rank cross-sectionally by that rolling value.

Candidate tail cuts:
- bottom 20%
- bottom 30%

This is likely more stable than single-day `amount`, but slightly more work.

---

### Method C: liquidity-aware weighting (later)
Do not remove low-liquidity names from the research universe outright.
Instead:
- cap their portfolio weight
- or demote them during final portfolio construction

This is more nuanced but should come after relative tail pruning is evaluated.

---

## Recommended first implementation order

### Phase 1
Implement only:
- cross-sectional bottom-tail pruning using same-day `amount`

### Tail cuts to test
- `bottom_10pct`
- `bottom_20pct`
- `bottom_30pct`

### Why this first?
Because it directly tests the hypothesis:
- maybe the worst 10-30% of liquidity names are causing most of the capacity problem
- without destroying 80-90% of the universe like the hard-floor test did

---

## What to compare

For each tail-pruning setting, compare:

1. universe retention
2. growth line effect
3. value line effect
4. realism shift
5. capacity shift

And explicitly compare against:
- the original base universe
- the failed hard-floor approach

---

## Suggested comparison report outputs

### Machine-readable
Create:
- `data/reports/relative_liquidity_tail_pruning_<timestamp>.json`

### Human-readable
Create:
- `data/reports/relative_liquidity_tail_pruning_<timestamp>.md`

Optional latest aliases:
- `relative_liquidity_tail_pruning_latest.json`
- `relative_liquidity_tail_pruning_latest.md`

---

## Proposed JSON schema (v1)

```json
{
  "report_type": "relative_liquidity_tail_pruning",
  "generated_at": "2026-05-18T00:00:00+00:00",
  "base_context": {
    "tracked_growth": "revgrowth_always_on_v1",
    "tracked_value_primary": "pbindlow_downtrend_narrow_quality_v1",
    "tracked_value_reference": "pbindlow_downtrend_only_v1"
  },
  "tested_methods": [
    {
      "label": "amount_bottom_10pct",
      "field": "amount",
      "method": "cross_sectional_tail_prune",
      "tail_cut": 0.10
    }
  ],
  "results": [
    {
      "label": "amount_bottom_10pct",
      "universe_effect": {
        "retained_fraction": 0.90,
        "coverage_change_vs_base": -0.10
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
      "recommendation": "promising|needs_more_review|too_weak"
    }
  ]
}
```

---

## Proposed Markdown structure

```md
# Relative Liquidity Tail-Pruning Summary

## Why this experiment exists
- ...

## Tested methods
| label | field | method | tail cut |
|---|---|---|---:|

## Universe effect
| label | retained fraction | coverage change |
|---|---:|---:|

## Growth effect
- ...

## Value effect
- ...

## Recommendation
- ...
```

---

## Decision criteria

### Good outcome
- universe retention remains high enough to keep the line meaningful
- realism improves
- capacity improves materially
- tracked line does not collapse in coverage

### Bad outcome
- capacity barely improves
- or signal collapses even after mild tail pruning

### Mixed outcome
- growth benefits from pruning
- value still remains too weak or too capacity-fragile

If so, accept asymmetry.
Do not force the system to keep both lines on equal footing.

---

## Integration path

1. add relative-liquidity tail-pruning experiment runner
2. compare universe retention across cuts
3. choose the most promising cut
4. rerun growth/value review under that cut
5. rerun realism and capacity
6. only then decide whether this becomes the new tradability-aware default

Important rule:
- do not promote any tail-pruning setting into official default only from retention statistics
- it must survive the full downstream chain

---

## Recommended implementation file layout

### New script
Create:
- `scripts/run_relative_liquidity_tail_pruning.py`

### Optional helper later
If logic grows:
- `app/services/relative_liquidity_filter.py`

### Tests
Create:
- `tests/scripts/test_run_relative_liquidity_tail_pruning.py`

---

## Implementation plan

### Task 1: Create experiment skeleton

**Objective:** Build the comparison-report skeleton and test harness.

**Files:**
- Create: `scripts/run_relative_liquidity_tail_pruning.py`
- Test: `tests/scripts/test_run_relative_liquidity_tail_pruning.py`

**Step 1: Write failing test**
Assert report keys exist:
- `report_type`
- `tested_methods`
- `results`

**Step 2: Run test to verify failure**
```bash
cd /root/project/quantsandbox_v2 && . .venv/bin/activate && pytest tests/scripts/test_run_relative_liquidity_tail_pruning.py -q
```
Expected: FAIL.

**Step 3: Write minimal implementation**
Emit schema-valid skeleton.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_relative_liquidity_tail_pruning.py tests/scripts/test_run_relative_liquidity_tail_pruning.py
git commit -m "feat: add relative liquidity tail-pruning skeleton"
```

### Task 2: Implement cross-sectional tail-pruning selector

**Objective:** Build a reusable function that removes the bottom liquidity tail by date.

**Files:**
- Modify: `scripts/run_relative_liquidity_tail_pruning.py`
- Optional create: `app/services/relative_liquidity_filter.py`
- Test: `tests/scripts/test_run_relative_liquidity_tail_pruning.py`

**Step 1: Write failing test**
Assert bottom-tail names are removed while the rest of the cross-section remains.

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Implement:
- `prune_bottom_liquidity_tail(...)`
- by field
- by tail cut
- at cross-sectional date level

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_relative_liquidity_tail_pruning.py app/services/relative_liquidity_filter.py tests/scripts/test_run_relative_liquidity_tail_pruning.py
git commit -m "feat: add relative liquidity tail-pruning selector"
```

### Task 3: Add base-vs-tail-pruned universe comparison

**Objective:** Measure universe retention under each tail cut.

**Files:**
- Modify: `scripts/run_relative_liquidity_tail_pruning.py`
- Test: `tests/scripts/test_run_relative_liquidity_tail_pruning.py`

**Step 1: Write failing test**
Assert each result row contains:
- `retained_fraction`
- `coverage_change_vs_base`

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Compute simple retention summaries across tail cuts.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_relative_liquidity_tail_pruning.py tests/scripts/test_run_relative_liquidity_tail_pruning.py
git commit -m "feat: add relative liquidity universe retention comparison"
```

### Task 4: Add tracked-line effect scaffolding

**Objective:** Produce growth/value effect placeholders or first-pass judgments so the report becomes actionable.

**Files:**
- Modify: `scripts/run_relative_liquidity_tail_pruning.py`
- Test: `tests/scripts/test_run_relative_liquidity_tail_pruning.py`

**Step 1: Write failing test**
Assert each result row contains:
- `growth_effect`
- `value_effect`
- `recommendation`

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Populate effect blocks and a simple recommendation rule based on universe retention.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/run_relative_liquidity_tail_pruning.py tests/scripts/test_run_relative_liquidity_tail_pruning.py
git commit -m "feat: add relative tail-pruning comparison report"
```

---

## Verification checklist

Before calling v1 done, verify:
- [ ] multiple tail cuts are compared
- [ ] universe retention is clearly shown
- [ ] results are less destructive than hard floors
- [ ] recommendation is explicit
- [ ] no governance role changes are implied automatically

---

## Recommended follow-up after implementation

After this lands:
1. choose the most promising tail cut
2. rerun growth/value review on the tail-pruned universe
3. rerun realism and capacity layers
4. then decide whether relative-liquidity pruning should become the new tradability-aware default path
