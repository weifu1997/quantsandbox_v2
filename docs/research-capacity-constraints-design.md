# Capacity Assumption & Liquidity Constraint Design

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Convert the newly surfaced liquidity realism findings into explicit capital-scale assumptions and enforceable liquidity constraints, so `quantsandbox_v2` can move from risk discovery to operational portfolio limits.

**Architecture:** Keep the first version simple and transparent. Do not attempt broker-grade market-impact modeling. Introduce one explicit model-capital assumption, define a small set of liquidity-capacity rules, emit a capacity/liquidity constraints report, and let downstream decision layers use these flags and suggested limits.

**Tech Stack:** Python, existing research datasets/backtests, JSON reports in `data/reports/`, Markdown output, current realism and decision-summary layers.

---

## Current state before this layer

Already in place:
- rolling decision summary exists
- cost sensitivity exists
- concentration risk exists
- execution realism exists
- first-pass liquidity signals now flag low-liquidity exposure from holdings-level traded-amount distributions

What is still missing:
- an explicit capital assumption
- a way to translate liquidity warnings into position-size limits
- a policy for filtering or downweighting low-liquidity names
- a stable rule that says when a candidate is too capacity-fragile for production-style use

Therefore this layer should answer one practical question:

> Given a chosen model capital, what liquidity constraints should the system enforce before trusting or sizing a candidate?

---

## Scope of v1

### In scope
- define one or more explicit capital assumptions
- define holdings-level liquidity-capacity rules
- define candidate-level low-liquidity exposure thresholds
- emit a machine-readable constraints report
- emit a human-readable summary
- prepare fields that later decision layers can consume directly

### Out of scope
- market-impact curve fitting
- intraday execution simulation
- real broker slippage model
- dynamic smart-order routing
- tick-level order-book analysis

---

## Core design choice: explicit capital assumptions

V1 should not pretend liquidity constraints are meaningful without a capital baseline.

### Recommended capital-assumption structure
Use one primary model capital plus optional scenario capitals.

Example:

```json
{
  "capital_assumptions": [
    {"label": "model_small", "aum": 1000000},
    {"label": "model_medium", "aum": 5000000},
    {"label": "model_large", "aum": 10000000}
  ]
}
```

### Why multiple sizes?
Because a strategy can be perfectly fine at 1M and unrealistic at 10M.
That difference is essential to real decision-making.

### Recommended v1 practical default
If you want just one first implementation path, start with:
- `model_medium = 5,000,000`

This is large enough to expose fragility without turning every small-cap strategy into an instant reject by construction.

---

## Liquidity-constraint rule set (v1)

### Rule 1: single-position-to-daily-amount cap
For each holding on each rebalance date, compute:

```text
position_notional / daily_traded_amount
```

Where:
- `position_notional = model_capital * target_weight`
- `daily_traded_amount` comes from the candidate dataset `amount`

### Suggested thresholds
- `acceptable`: <= 1%
- `warning`: > 1% and <= 3%
- `elevated`: > 3%

These are intentionally conservative first-pass rules.

---

### Rule 2: portfolio low-liquidity exposure ratio
Measure how much of the portfolio repeatedly falls into high-impact territory.

Example metric:

```text
low_liquidity_exposure_ratio = share of holding observations where position_notional / daily_traded_amount > 1%
```

### Suggested thresholds
- `acceptable`: <= 10%
- `warning`: > 10% and <= 25%
- `elevated`: > 25%

---

### Rule 3: stressed capacity percentile
Use the worst tail rather than just the median.

Metrics:
- median position-to-amount ratio
- p90 position-to-amount ratio
- max position-to-amount ratio

### Suggested interpretation
- if p90 already exceeds the warning threshold, candidate capacity is not robust
- if max is extreme even when median is fine, candidate still needs caution

---

### Rule 4: hard liquidity filter candidate
Create a candidate-level boolean like:

```text
liquidity_constraint_breach = True
```

when:
- p90 position-to-amount ratio > 3%
- or low-liquidity exposure ratio > 25%

This gives downstream decision logic a clean gate.

---

## Output files

### Machine-readable report
Create:
- `data/reports/research_capacity_constraints_<timestamp>.json`

Optional latest alias:
- `data/reports/research_capacity_constraints_latest.json`

### Human-readable summary
Create:
- `data/reports/research_capacity_constraints_<timestamp>.md`

Optional latest alias:
- `data/reports/research_capacity_constraints_latest.md`

---

## Proposed JSON schema (v1)

```json
{
  "report_type": "research_capacity_constraints",
  "generated_at": "2026-05-18T00:00:00+00:00",
  "as_of_date": "2026-05-18",
  "capital_assumptions": [
    {"label": "model_medium", "aum": 5000000}
  ],
  "liquidity_thresholds": {
    "single_position_ratio_warn": 0.01,
    "single_position_ratio_elevated": 0.03,
    "low_liquidity_exposure_warn": 0.10,
    "low_liquidity_exposure_elevated": 0.25
  },
  "candidate_capacity": [
    {
      "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
      "line": "valuation_line",
      "capital_label": "model_medium",
      "operating_params": {
        "top_n": 20,
        "rebalance_frequency": "W",
        "weighting": "equal"
      },
      "liquidity_capacity": {
        "status": "acceptable|warning|elevated",
        "note": "...",
        "snapshot": {
          "median_position_to_amount_ratio": 0.0,
          "p90_position_to_amount_ratio": 0.0,
          "max_position_to_amount_ratio": 0.0,
          "low_liquidity_exposure_ratio": 0.0
        },
        "constraint_breach": false
      },
      "suggested_constraint": {
        "max_position_to_amount_ratio": 0.01,
        "action": "keep|downweight|filter|reject_for_mainline"
      }
    }
  ],
  "source_artifacts": {
    "realism_report": "data/reports/research_realism_stress_latest.json",
    "decision_summary": "data/reports/research_decision_summary_latest.json",
    "selection_trace": {
      "pbindlow_downtrend_narrow_quality_v1": {
        "review_id": "review_quality_2026H1",
        "window_label": "2026H1"
      }
    }
  }
}
```

---

## Proposed Markdown structure (v1)

```md
# Research Capacity & Liquidity Constraint Summary

- Generated at: ...
- As of date: ...
- Capital assumption: model_medium = 5,000,000

## Executive takeaway
- ...

## Candidate capacity table
| strategy | capital | liquidity capacity | breach | suggested action |
|---|---|---|---|---|

## Liquidity-capacity details
### value primary
- median position/amount: ...
- p90 position/amount: ...
- max position/amount: ...
- low-liquidity exposure ratio: ...

## Suggested liquidity constraints
1. ...
2. ...
```

---

## Status derivation rules

### Candidate liquidity-capacity status
Use the worst applicable threshold:

- `acceptable`
  - p90 ratio <= 1%
  - low-liquidity exposure <= 10%
- `warning`
  - p90 ratio > 1% and <= 3%
  - or low-liquidity exposure > 10% and <= 25%
- `elevated`
  - p90 ratio > 3%
  - or low-liquidity exposure > 25%

### Suggested action mapping
- `acceptable` -> `keep`
- `warning` -> `downweight`
- `elevated` -> `filter` or `reject_for_mainline`

V1 may keep this mapping simple.

---

## Integration with existing layers

### Realism stress layer
This new layer should consume:
- latest realism report
- latest decision summary
- candidate holdings / dataset windows implied by current selection trace

### Decision summary layer
Later, decision summary can use capacity output to refine portfolio actions such as:
- growth remains core, but only below model-medium capital
- value remains secondary and must obey stricter liquidity filters

Important rule:
- decision summary should consume capacity outputs
- capacity logic should remain separate and explicit

---

## Recommended implementation file layout

### New script
Create:
- `scripts/build_research_capacity_constraints.py`

### Optional helper module later
If needed later:
- `app/services/research_capacity_constraints.py`

### Tests
Create:
- `tests/scripts/test_build_research_capacity_constraints.py`

---

## Implementation plan

### Task 1: Create capacity report skeleton

**Objective:** Create the capacity/liquidity constraints builder with stable top-level schema.

**Files:**
- Create: `scripts/build_research_capacity_constraints.py`
- Test: `tests/scripts/test_build_research_capacity_constraints.py`

**Step 1: Write failing test**
Assert top-level keys exist:
- `report_type`
- `capital_assumptions`
- `candidate_capacity`

**Step 2: Run test to verify failure**
```bash
cd /root/project/quantsandbox_v2 && . .venv/bin/activate && pytest tests/scripts/test_build_research_capacity_constraints.py -q
```
Expected: FAIL.

**Step 3: Write minimal implementation**
Return schema-valid skeleton.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_capacity_constraints.py tests/scripts/test_build_research_capacity_constraints.py
git commit -m "feat: add capacity constraints report skeleton"
```

### Task 2: Add single-capital first-pass calculation

**Objective:** Compute per-holding position-to-amount ratios under one capital assumption.

**Files:**
- Modify: `scripts/build_research_capacity_constraints.py`
- Test: `tests/scripts/test_build_research_capacity_constraints.py`

**Step 1: Write failing test**
Assert snapshot contains:
- `median_position_to_amount_ratio`
- `p90_position_to_amount_ratio`
- `low_liquidity_exposure_ratio`

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Implement first-pass ratio calculation using:
- holdings
- target weights
- capital assumption
- `amount`

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_capacity_constraints.py tests/scripts/test_build_research_capacity_constraints.py
git commit -m "feat: add first-pass position-to-amount capacity calculations"
```

### Task 3: Add status derivation and suggested action

**Objective:** Convert capacity ratios into enforceable status + action.

**Files:**
- Modify: `scripts/build_research_capacity_constraints.py`
- Test: `tests/scripts/test_build_research_capacity_constraints.py`

**Step 1: Write failing test**
Assert warning/elevated cases map to expected actions.

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Implement:
- `derive_capacity_status(...)`
- `derive_constraint_action(...)`

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_capacity_constraints.py tests/scripts/test_build_research_capacity_constraints.py
git commit -m "feat: add capacity status and constraint action mapping"
```

### Task 4: Emit Markdown + latest aliases

**Objective:** Produce readable capacity summary artifacts.

**Files:**
- Modify: `scripts/build_research_capacity_constraints.py`
- Test: `tests/scripts/test_build_research_capacity_constraints.py`

**Step 1: Write failing test**
Assert Markdown contains:
- `# Research Capacity & Liquidity Constraint Summary`
- `## Candidate capacity table`
- `## Suggested liquidity constraints`

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Add Markdown renderer and latest alias outputs.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_capacity_constraints.py tests/scripts/test_build_research_capacity_constraints.py
git commit -m "feat: emit capacity constraint reports"
```

---

## Verification checklist

Before calling v1 done, verify:
- [ ] explicit capital assumption is stored in output
- [ ] candidate capacity rows exist for all tracked candidates
- [ ] ratio-based liquidity metrics are present
- [ ] status/action are derived, not hand-written
- [ ] Markdown summary is readable
- [ ] later decision-summary integration can consume this without schema churn

---

## Recommended follow-up after capacity v1

After this lands:
1. decide whether model capital should become a user-configurable research setting
2. connect capacity outputs into decision-summary portfolio actions
3. use capacity breaches to justify hard filters or downweight rules in the next portfolio-rule layer
