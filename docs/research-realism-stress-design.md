# Realism Stress-Test Layer Design

> **文档状态：部分实现**
> 
> realism report 层、decision summary 消费、部分 execution/cost/concentration realism 信号已落地；但本文仍包含设计性内容与未来扩展假设，因此属于“部分实现”。

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Define a first practical realism-stress layer for `quantsandbox_v2` so the decision-summary system can move beyond research-only metrics and start judging whether tracked candidates remain plausible under more realistic trading constraints.

**Architecture:** Keep the first version narrow and decision-oriented. Do not attempt a full market simulator. Instead, compute a small set of realism checks from the existing tracked candidates, emit one dedicated realism report, and let `research_decision_summary` consume the resulting flags. Build this as a report layer first, not a deep engine rewrite.

**Tech Stack:** Python, existing research/backtest outputs, JSON reports in `data/reports/`, Markdown summaries, existing decision-summary builder.

---

## Current state before this layer

Already in place:
- tracked growth/value candidates are defined
- rolling decision summary v1 exists
- realism hooks already exist in decision-summary schema as `{status, note}` placeholders
- decision-summary / registry / status / overview have been calibrated to one consistent governance state

What is missing:
- any real basis for setting `liquidity_risk`
- any real basis for setting `cost_sensitivity`
- any real basis for setting `concentration_risk`
- any real basis for setting `execution_realism`

Therefore the realism layer should do one thing well:

> translate a small number of realistic trading constraints into structured flags that can be consumed by the decision-summary system.

---

## Scope of v1

### In scope
- stress-test the tracked candidates only
- produce structured realism flags for:
  - `cost_sensitivity`
  - `concentration_risk`
  - `liquidity_risk`
  - `execution_realism`
- emit one realism report artifact
- allow `build_research_decision_summary.py` to consume the newest realism report

### Out of scope
- intraday simulation
- order-book modeling
- limit-order execution engine
- broker API integration
- tick-level slippage model
- full portfolio optimizer rewrite

---

## Recommended rollout priority

### Phase 1 (first implementation)
Implement first:
1. `cost_sensitivity`
2. `concentration_risk`

These are the easiest to compute and the fastest to make useful.

### Phase 2
Implement next:
3. `liquidity_risk`
4. `execution_realism`

These require a slightly more interpretive mapping from market data / candidate holdings patterns.

---

## Tracked candidates for realism v1

The realism layer should evaluate only:

1. `revgrowth_always_on_v1`
2. `pbindlow_downtrend_narrow_quality_v1`
3. `pbindlow_downtrend_only_v1`

No broader candidate sweep in v1.

---

## Output files

### Machine-readable realism report
Create:
- `data/reports/research_realism_stress_<timestamp>.json`

Optional latest alias:
- `data/reports/research_realism_stress_latest.json`

### Human-readable realism summary
Create:
- `data/reports/research_realism_stress_<timestamp>.md`

Optional latest alias:
- `data/reports/research_realism_stress_latest.md`

---

## Proposed JSON schema (v1)

```json
{
  "report_type": "research_realism_stress",
  "generated_at": "2026-05-18T00:00:00+00:00",
  "as_of_date": "2026-05-18",
  "tracked_candidates": {
    "growth_primary": "revgrowth_always_on_v1",
    "value_primary": "pbindlow_downtrend_narrow_quality_v1",
    "value_baseline_reference": "pbindlow_downtrend_only_v1"
  },
  "assumptions": {
    "cost_scenarios": [
      {"label": "base", "commission_bps": 10.0, "slippage_bps": 5.0},
      {"label": "stress_1", "commission_bps": 15.0, "slippage_bps": 10.0},
      {"label": "stress_2", "commission_bps": 20.0, "slippage_bps": 15.0}
    ],
    "concentration_thresholds": {
      "single_name_weight_warn": 0.12,
      "top3_weight_warn": 0.35,
      "top5_weight_warn": 0.55
    },
    "liquidity_thresholds": {
      "position_to_daily_turnover_warn": 0.05,
      "position_to_daily_turnover_elevated": 0.10
    }
  },
  "candidate_realism": [
    {
      "strategy_id": "pbindlow_downtrend_narrow_quality_v1",
      "line": "valuation_line",
      "operating_params": {
        "top_n": 20,
        "rebalance_frequency": "W",
        "horizon": 10,
        "weighting": "equal",
        "benchmark": "equal_weight_universe"
      },
      "cost_sensitivity": {
        "status": "acceptable|warning|elevated",
        "note": "...",
        "scenario_comparison": [
          {"label": "base", "annual_return": 0.0, "sharpe": 0.0},
          {"label": "stress_1", "annual_return": 0.0, "sharpe": 0.0},
          {"label": "stress_2", "annual_return": 0.0, "sharpe": 0.0}
        ]
      },
      "concentration_risk": {
        "status": "acceptable|warning|elevated",
        "note": "...",
        "snapshot": {
          "avg_single_name_weight": 0.0,
          "avg_top3_weight": 0.0,
          "avg_top5_weight": 0.0
        }
      },
      "liquidity_risk": {
        "status": "unknown|acceptable|warning|elevated",
        "note": "...",
        "snapshot": {
          "median_position_to_daily_turnover": null,
          "p90_position_to_daily_turnover": null
        }
      },
      "execution_realism": {
        "status": "unknown|acceptable|warning|elevated",
        "note": "...",
        "checks": {
          "weekly_rebalance_feasible": true,
          "extreme_turnover_warning": false,
          "small_sample_caution": false
        }
      },
      "overall_realism": {
        "status": "acceptable|warning|elevated",
        "note": "..."
      }
    }
  ],
  "source_artifacts": {
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
# Research Realism Stress Summary

- Generated at: ...
- As of date: ...

## Executive takeaway
- ...

## Candidate realism table
| strategy | cost sensitivity | concentration | liquidity | execution | overall |
|---|---|---|---|---|---|

## Cost sensitivity details
### value primary
- base annual / sharpe: ...
- stress_1 annual / sharpe: ...
- stress_2 annual / sharpe: ...

## Concentration risk details
### value primary
- avg single-name weight: ...
- avg top3 weight: ...
- avg top5 weight: ...

## Liquidity & execution notes
- ...

## Recommended realism actions
1. ...
2. ...
```

---

## Status derivation rules

### Cost sensitivity
Suggested rule shape:

- `acceptable`
  - stress scenarios reduce returns but do not collapse the strategy narrative
  - sharpe degradation remains moderate
- `warning`
  - performance degrades materially under modestly harsher cost assumptions
- `elevated`
  - the strategy becomes weak / negative / implausible under realistic cost stress

### Concentration risk
Suggested rule shape:

- `acceptable`
  - top3/top5 concentration stays comfortably under thresholds
- `warning`
  - concentration repeatedly approaches or modestly exceeds thresholds
- `elevated`
  - exposure is persistently too concentrated for comfortable production-style use

### Liquidity risk
Suggested rule shape:

- `unknown`
  - if v1 lacks sufficient turnover/notional data
- `acceptable`
  - position sizes appear small relative to daily turnover
- `warning`
  - sizing may be feasible only at modest capital scales
- `elevated`
  - realistic capacity likely much lower than naive backtest interpretation

### Execution realism
Suggested rule shape:

- `unknown`
  - if checks are not yet wired
- `acceptable`
  - turnover and rebalance assumptions appear operationally sane
- `warning`
  - frequent or concentrated rebalances create realism concerns
- `elevated`
  - execution assumptions likely overstate practical tradability

### Overall realism
Overall status should be the worst of the four categories unless future versions adopt a more nuanced scoring model.

---

## Data source strategy

### Cost sensitivity inputs
Use the same candidate definition, but rerun the relevant backtest under several cost assumptions.

### Concentration inputs
Read or reconstruct holdings snapshots from the candidate backtest output. If holdings details are not exposed cleanly enough, add a minimal helper in the backtest/report path to summarize concentration metrics.

### Liquidity inputs
Prefer using market data already in the dataset layer:
- daily turnover value / traded value / amount if available
- otherwise use the best available liquidity proxy and mark assumptions clearly

### Execution realism inputs
Use:
- turnover
- rebalance frequency
- concentration
- available active dates
- simple feasibility rules

---

## Integration with decision summary

`build_research_decision_summary.py` should later do the following:

1. resolve the latest realism report
2. map `candidate_realism[*]` by `strategy_id`
3. replace placeholder `realism_flags` with real values
4. optionally lift `overall_realism.status` into executive-summary wording
5. add realism-based research actions when needed

Important rule:
- decision summary should **consume** realism outputs
- decision summary should not recompute realism logic itself

Keep the realism layer separate.

---

## Recommended implementation file layout

### New script
Create:
- `scripts/build_research_realism_stress.py`

### Optional helper module later
If needed later:
- `app/services/research_realism_stress.py`

### Tests
Create:
- `tests/scripts/test_build_research_realism_stress.py`

---

## Implementation plan

### Task 1: Create realism report skeleton

**Objective:** Create the realism report builder and its top-level schema.

**Files:**
- Create: `scripts/build_research_realism_stress.py`
- Test: `tests/scripts/test_build_research_realism_stress.py`

**Step 1: Write failing test**
Assert the builder returns top-level keys:
- `report_type`
- `candidate_realism`
- `source_artifacts`

**Step 2: Run test to verify failure**
Run:
```bash
cd /root/project/quantsandbox_v2 && . .venv/bin/activate && pytest tests/scripts/test_build_research_realism_stress.py -q
```
Expected: FAIL.

**Step 3: Write minimal implementation**
Add skeleton builder returning an empty but schema-valid payload.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_realism_stress.py tests/scripts/test_build_research_realism_stress.py
git commit -m "feat: add realism stress report skeleton"
```

### Task 2: Implement cost sensitivity scenarios

**Objective:** Add multi-scenario cost-stress evaluation for tracked candidates.

**Files:**
- Modify: `scripts/build_research_realism_stress.py`
- Test: `tests/scripts/test_build_research_realism_stress.py`

**Step 1: Write failing test**
Assert each candidate includes `cost_sensitivity.scenario_comparison` with base/stress rows.

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Implement scenario reruns or scenario-driven derivation using current candidate params with cost overrides.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_realism_stress.py tests/scripts/test_build_research_realism_stress.py
git commit -m "feat: add cost sensitivity realism checks"
```

### Task 3: Implement concentration risk summaries

**Objective:** Add basic concentration summaries for tracked candidates.

**Files:**
- Modify: `scripts/build_research_realism_stress.py`
- Test: `tests/scripts/test_build_research_realism_stress.py`

**Step 1: Write failing test**
Assert each candidate includes `concentration_risk.snapshot.avg_top3_weight` and status.

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Compute a simple concentration summary from holdings/backtest outputs.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_realism_stress.py tests/scripts/test_build_research_realism_stress.py
git commit -m "feat: add concentration realism checks"
```

### Task 4: Add placeholder-or-basic liquidity and execution checks

**Objective:** Wire the remaining two flags with explicit status logic, even if still conservative in v1.

**Files:**
- Modify: `scripts/build_research_realism_stress.py`
- Test: `tests/scripts/test_build_research_realism_stress.py`

**Step 1: Write failing test**
Assert liquidity/execution keys exist with `{status, note}` and snapshots/checks.

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Implement either real calculations or explicit `unknown` with rationale when data is not sufficient.

**Step 4: Run test to verify pass**
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_realism_stress.py tests/scripts/test_build_research_realism_stress.py
git commit -m "feat: add liquidity and execution realism checks"
```

### Task 5: Integrate realism report into decision summary

**Objective:** Replace placeholder realism flags in decision summary with realism-report values.

**Files:**
- Modify: `scripts/build_research_decision_summary.py`
- Test: `tests/scripts/test_build_research_decision_summary.py`
- Test: `tests/scripts/test_build_research_realism_stress.py`

**Step 1: Write failing test**
Assert decision summary consumes realism flags from the latest realism report when present.

**Step 2: Run test to verify failure**
Expected: FAIL.

**Step 3: Write minimal implementation**
Read the latest realism report and merge `candidate_realism` by `strategy_id`.

**Step 4: Run tests to verify pass**
Run both test files.
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_realism_stress.py scripts/build_research_decision_summary.py tests/scripts/
git commit -m "feat: connect realism stress layer to decision summary"
```

---

## Verification checklist

Before calling realism v1 done, verify:
- [ ] realism JSON output exists
- [ ] realism Markdown output exists
- [ ] all tracked candidates are present
- [ ] cost scenarios are explicit and reproducible
- [ ] concentration snapshot fields are populated
- [ ] liquidity/execution statuses are explicit, even if still `unknown`
- [ ] overall realism is derived, not hand-written
- [ ] decision summary can consume realism outputs without schema changes

---

## Recommended follow-up after realism v1

After this lands:
1. refine liquidity proxies using better turnover/capacity data
2. use realism output to gate portfolio-actions wording in decision summary
3. only then move on to a simple research-state-driven allocation rule layer
