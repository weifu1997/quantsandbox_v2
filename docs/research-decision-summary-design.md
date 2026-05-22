# Rolling Review → Decision Summary Design

> **文档状态：部分实现**
> 
> decision summary JSON/Markdown、tracked candidate 规范化、deployability 与 realism/capacity 消费链已部分落地；本文仍同时包含初始设计意图和未完全冻结的扩展方向，因此属于“部分实现”。

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Define a standard output structure and generation flow that converts rolling strategy reviews into a compact, repeatable research decision summary for `quantsandbox_v2`.

**Architecture:** Keep the first version simple: consume existing registry/status/reviews artifacts, normalize a tiny set of tracked candidates, and emit two outputs — machine-readable JSON plus a human-readable Markdown summary. Do not build a new UI first. Treat this as a decision-synthesis layer above the existing research scripts.

**Tech Stack:** Python, existing `scripts/` review builders, JSON reports in `data/reports/`, Markdown output.

---

## Current settled state

Before implementation, treat the following as already settled:

- Growth formal tracking object includes the growth core candidate.
- Value primary candidate is `pbindlow_downtrend_narrow_quality_v1`.
- Legacy baseline remains reference-only for the decision-summary layer, not the main operating default.
- Main objective is **decision quality**, not strategy-surface expansion.

Important constraint:
- Value operating defaults should be read from the **current registry params**, not hard-coded into this design.

Therefore this design must optimize for:
1. a small number of tracked candidates,
2. rolling forward review consumption,
3. explicit action guidance,
4. future insertion of realistic trading constraints.

---

## Scope of v1

### In scope
- Read existing candidate-pool artifacts
- Normalize tracked-candidate state
- Produce one JSON decision summary artifact
- Produce one Markdown decision summary artifact
- Include placeholders/flags for future realism checks
- Keep the structure stable enough for cron or repeated manual runs

### Out of scope
- New frontend pages
- New allocator logic
- Automated order sizing
- Portfolio execution engine
- Full realism model implementation (only schema hooks in v1)

---

## Tracked objects in v1

V1 should explicitly track only these three objects:

1. `revgrowth_always_on_v1`
2. `pbindlow_downtrend_narrow_quality_v1`
3. `pbindlow_downtrend_only_v1`

### Why only three?
Because this layer is meant to improve decision clarity, not broaden the strategy surface.

---

## Output files

### File 1: machine-readable summary
Create:
- `data/reports/research_decision_summary_<timestamp>.json`

Optional convenience alias/update path:
- `data/reports/research_decision_summary_latest.json`

### File 2: human-readable summary
Create:
- `data/reports/research_decision_summary_<timestamp>.md`

Optional convenience alias/update path:
- `data/reports/research_decision_summary_latest.md`

### Why both?
- JSON is for future scripting, automation, and downstream rules
- Markdown is for direct operator reading and review

---

## Proposed JSON schema (v1)

```json
{
  "report_type": "research_decision_summary",
  "generated_at": "2026-05-18T00:00:00+00:00",
  "as_of_date": "2026-05-18",
  "tracked_candidates": {
    "growth_primary": "revgrowth_always_on_v1",
    "value_primary": "pbindlow_downtrend_narrow_quality_v1",
    "value_baseline_reference": "pbindlow_downtrend_only_v1"
  },
  "executive_summary": {
    "primary_takeaway": "...",
    "recommended_posture": "...",
    "allocator_priority": "deprioritized",
    "confidence": "low|medium|high"
  },
  "candidate_states": [
    {
      "line": "growth_line",
      "strategy_id": "revgrowth_always_on_v1",
      "role": "primary_candidate",
      "status": "active",
      "latest_review": {
        "review_id": "...",
        "window_label": "...",
        "review_result": "keep",
        "comment": "..."
      },
      "evidence_summary": {
        "formal_review_count": 2,
        "recent_review_count_used": 2,
        "latest_window_label": "2025H2",
        "latest_start_date": "20250701",
        "latest_end_date": "20251231"
      },
      "recent_review_trend": "stable_keep",
      "suggested_action": "continue_tracking",
      "operating_params": {
        "top_n": 20,
        "rebalance_frequency": "W",
        "horizon": 10,
        "weighting": "equal",
        "benchmark": "equal_weight_universe"
      },
      "metrics_snapshot": {
        "annual_return": 0.0,
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "top_bottom_spread": 0.0,
        "active_ratio": 0.0,
        "rank_ic_mean": 0.0,
        "positive_ic_ratio": 0.0,
        "monotonicity_score": 0.0
      },
      "realism_flags": {
        "liquidity_risk": {"status": "unknown", "note": ""},
        "cost_sensitivity": {"status": "unknown", "note": ""},
        "concentration_risk": {"status": "unknown", "note": ""},
        "execution_realism": {"status": "unknown", "note": ""}
      }
    }
  ],
  "line_view": {
    "growth_line": {
      "posture": "core",
      "headline_action": "..."
    },
    "valuation_line": {
      "posture": "primary_active|primary_watch|reference_only",
      "headline_action": "..."
    }
  },
  "decision_actions": {
    "research_actions": [
      "...",
      "..."
    ],
    "portfolio_actions": [
      "...",
      "..."
    ]
  },
  "open_risks": [
    "...",
    "..."
  ],
  "source_artifacts": {
    "growth_status": "data/reports/revgrowth_candidate_pool_status_latest.json",
    "value_status": "data/reports/pbindlow_candidate_pool_status_latest.json",
    "overview": "data/reports/strategy_candidate_pool_overview_latest.json",
    "growth_reviews": "data/reports/revgrowth_candidate_reviews.json",
    "value_reviews": "data/reports/pbindlow_candidate_reviews.json",
    "selection_trace": {
      "revgrowth_always_on_v1": {
        "review_id": "review_2025H2",
        "window_label": "2025H2"
      },
      "pbindlow_downtrend_narrow_quality_v1": {
        "review_id": "review_quality_2025H2",
        "window_label": "2025H2"
      }
    }
  }
}
```

### Schema notes
- `tracked_candidates` replaces the older `tracked_universe` naming.
- `operating_params` must be read from the **current registry params**, not hard-coded defaults.
- `realism_flags` uses `{status, note}` objects to avoid future schema churn.
- `decision_actions` is split into `research_actions` and `portfolio_actions`.
- `selection_trace` must identify which review row actually supplied the latest evidence.

---

## Proposed Markdown structure (v1)

```md
# Research Decision Summary

- Generated at: ...
- As of date: ...

## Executive summary
- Primary takeaway: ...
- Recommended posture: ...
- Allocator priority: deprioritized
- Confidence: ...

## What changed since last summary
- ...
- ...
- ...

## Candidate state table
| line | strategy | role | status | latest review | trend | suggested action |
|---|---|---|---|---|---|---|

## Evidence snapshot
### Growth core
- annual_return: ...
- sharpe: ...
- max_drawdown: ...
- ...

### Value primary
- annual_return: ...
- sharpe: ...
- max_drawdown: ...
- ...

### Value baseline reference
- annual_return: ...
- sharpe: ...
- max_drawdown: ...
- ...

## Realism flags
| strategy | liquidity | cost sensitivity | concentration | execution realism |
|---|---|---|---|---|

## Suggested research actions
1. ...
2. ...

## Suggested portfolio actions
1. ...
2. ...

## Open risks
- ...
- ...
```

---

## Derivation rules for v1

### Executive summary derivation
Generate from existing artifacts using conservative rules:

- If growth core is stable/active and value primary is still accumulating evidence, summary should describe growth as the core line.
- If value primary is active and its latest evidence is acceptable, summary may describe it as `primary_active` rather than watch-only.
- If allocator line still underperforms growth-only baseline, `allocator_priority` should remain `deprioritized`.

### Candidate state derivation
For each tracked candidate, pull from:
- registry role
- registry params
- latest review row
- status summary trend/action
- latest metrics row in reviews log
- evidence counts from the review history

### Realism flags derivation
V1 should allow `unknown` values.
Do not invent realism conclusions before the realism stress-test layer exists.

### Confidence derivation rule
Confidence must not be freehand.
Use simple explicit rules such as:

- `high`
  - primary candidate is active
  - recent review trend is `stable_keep`
  - multiple formal reviews support the state
- `medium`
  - candidate is active but evidence count is still limited
  - or trend is acceptable but realism flags remain mostly `unknown`
- `low`
  - candidate is watch / mixed / recently weakening
  - or signals are contradictory across latest evidence

Implementation may refine thresholds later, but v1 must not rely on pure intuition.

### Line posture derivation
- `growth_line.posture` can remain simple (`core` in v1).
- `valuation_line.posture` must support:
  - `primary_active`
  - `primary_watch`
  - `reference_only`

### Decision actions derivation
Limit action lists to 3-5 lines max per section.
Actions should be operational, not essay-like.

Good research-action examples:
- `Continue forward review accumulation for the value primary under current registry params.`
- `Run realism stress checks before any promotion to production-style allocation.`

Good portfolio-action examples:
- `Keep growth core as the main tracked allocation anchor.`
- `Treat value primary as an active secondary sleeve rather than the dominant line.`

---

## Generation flow (v1)

### Step 1: Resolve source artifacts dynamically
Read:
- `data/reports/revgrowth_candidate_registry.json`
- `data/reports/revgrowth_candidate_reviews.json`
- latest matching `data/reports/revgrowth_candidate_pool_status_*.json`
- `data/reports/pbindlow_candidate_registry.json`
- `data/reports/pbindlow_candidate_reviews.json`
- latest matching `data/reports/pbindlow_candidate_pool_status_*.json`
- latest matching `data/reports/strategy_candidate_pool_overview_*.json`

Builder should resolve the latest available status/overview artifacts by explicit path configuration or by selecting the newest matching file, rather than hard-coding one date-stamped filename.

### Step 2: Resolve tracked candidates
Normalize the three tracked objects into one internal structure.

### Step 3: Pull latest evidence
For each tracked candidate:
- locate latest review row
- extract latest metrics
- attach trend/action from status summary
- attach operating params from registry
- attach formal review counts and latest window metadata
- store selection trace (`review_id`, `window_label`)

### Step 4: Synthesize line posture
Produce a small line-level decision:
- growth line = core / not core
- valuation line = primary_active / primary_watch / reference_only

### Step 5: Build executive summary and changes section
Produce:
- one concise top-level interpretation
- one “What changed since last summary” section if a previous summary exists

### Step 6: Emit JSON + Markdown
Write both outputs to `data/reports/`.
Also update `*_latest.*` convenience aliases if desired.

---

## Recommended implementation file layout

### New script
Create:
- `scripts/build_research_decision_summary.py`

### Optional helper module later
If the script grows too large, extract to:
- `app/services/research_decision_summary.py`

For v1, keep it as one script unless size clearly justifies extraction.

### Tests
Create:
- `tests/scripts/test_build_research_decision_summary.py`

V1 tests should focus on:
- tracked candidate extraction
- latest review selection
- JSON schema key presence
- Markdown output key sections
- role-switch compatibility for value primary vs baseline reference

---

## Implementation plan

### Task 1: Create script skeleton

**Objective:** Create the report builder entrypoint with stable input/output paths.

**Files:**
- Create: `scripts/build_research_decision_summary.py`
- Test: `tests/scripts/test_build_research_decision_summary.py`

**Step 1: Write failing test**
Create a test that asserts the script module can build a minimal summary dict with required top-level keys.

**Step 2: Run test to verify failure**
Run:
```bash
cd /root/project/quantsandbox_v2 && . .venv/bin/activate && pytest tests/scripts/test_build_research_decision_summary.py -q
```
Expected: FAIL — module/function missing.

**Step 3: Write minimal implementation**
Add the script with a pure function like `build_summary(...)` returning a dict containing:
- `report_type`
- `generated_at`
- `candidate_states`
- `decision_actions`

**Step 4: Run test to verify pass**
Run the same pytest command.
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_decision_summary.py tests/scripts/test_build_research_decision_summary.py
git commit -m "feat: add research decision summary builder skeleton"
```

### Task 2: Add tracked-candidate loading

**Objective:** Load the three tracked candidates from registry/status/reviews artifacts.

**Files:**
- Modify: `scripts/build_research_decision_summary.py`
- Test: `tests/scripts/test_build_research_decision_summary.py`

**Step 1: Write failing test**
Add a test that feeds fixture-like registry/review/status data and expects exactly three normalized tracked candidates.

**Step 2: Run test to verify failure**
Run the specific test.
Expected: FAIL — normalization not implemented.

**Step 3: Write minimal implementation**
Implement helper functions:
- `load_json(path)`
- `select_latest_review(reviews, strategy_id)`
- `build_candidate_state(...)`

**Step 4: Run test to verify pass**
Run pytest again.
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_decision_summary.py tests/scripts/test_build_research_decision_summary.py
git commit -m "feat: normalize tracked candidate states for decision summary"
```

### Task 3: Add executive summary and line posture logic

**Objective:** Convert raw states into concise top-level posture.

**Files:**
- Modify: `scripts/build_research_decision_summary.py`
- Test: `tests/scripts/test_build_research_decision_summary.py`

**Step 1: Write failing test**
Add tests for simple rule outcomes, e.g.:
- growth active + value active => growth core, value primary_active
- allocator still deprioritized
- confidence follows explicit derivation rules

**Step 2: Run test to verify failure**
Run targeted pytest.
Expected: FAIL.

**Step 3: Write minimal implementation**
Implement:
- `build_line_view(...)`
- `build_executive_summary(...)`
- `build_decision_actions(...)`
- `derive_confidence(...)`

Keep logic explicit and conservative.

**Step 4: Run test to verify pass**
Run pytest again.
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_decision_summary.py tests/scripts/test_build_research_decision_summary.py
git commit -m "feat: add research posture synthesis for decision summary"
```

### Task 4: Add Markdown renderer and file output

**Objective:** Emit both JSON and Markdown artifacts under `data/reports/`.

**Files:**
- Modify: `scripts/build_research_decision_summary.py`
- Test: `tests/scripts/test_build_research_decision_summary.py`

**Step 1: Write failing test**
Add test asserting Markdown output contains required headings:
- `# Research Decision Summary`
- `## What changed since last summary`
- `## Suggested research actions`
- `## Suggested portfolio actions`

**Step 2: Run test to verify failure**
Run pytest.
Expected: FAIL.

**Step 3: Write minimal implementation**
Implement:
- `render_markdown(summary)`
- timestamped output path builder
- optional latest-alias write helper

**Step 4: Run test to verify pass**
Run pytest again.
Expected: PASS.

**Step 5: Commit**
```bash
git add scripts/build_research_decision_summary.py tests/scripts/test_build_research_decision_summary.py
git commit -m "feat: emit json and markdown decision summary artifacts"
```

### Task 5: Run against real artifacts and verify outputs

**Objective:** Validate the builder on the current real research files.

**Files:**
- Modify if needed: `scripts/build_research_decision_summary.py`
- Output: `data/reports/research_decision_summary_*.json`
- Output: `data/reports/research_decision_summary_*.md`

**Step 1: Run the real builder**
Run:
```bash
cd /root/project/quantsandbox_v2 && . .venv/bin/activate && python scripts/build_research_decision_summary.py
```
Expected: two output paths printed successfully.

**Step 2: Inspect outputs**
Check that:
- the tracked strategies are exactly the intended three
- value primary reads operating params from the current registry
- allocator remains deprioritized
- summary text is concise and action-oriented
- selection trace is populated

**Step 3: Run tests**
Run:
```bash
cd /root/project/quantsandbox_v2 && . .venv/bin/activate && pytest tests/scripts/test_build_research_decision_summary.py -q
```
Expected: PASS.

**Step 4: Commit**
```bash
git add scripts/build_research_decision_summary.py tests/scripts/test_build_research_decision_summary.py data/reports/
git commit -m "feat: add rolling research decision summary outputs"
```

---

## Verification checklist

Before calling v1 done, verify:
- [ ] JSON output exists and is valid
- [ ] Markdown output exists and is readable
- [ ] Exactly three tracked candidates are included
- [ ] Value primary params are read from registry, not hard-coded
- [ ] Legacy baseline is clearly reference-only in the summary layer
- [ ] Executive summary is concise, not essay-like
- [ ] Suggested actions are split into research vs portfolio
- [ ] Realism flags exist with `{status, note}` shape
- [ ] Selection trace points to the actual latest review row used
- [ ] Role-switch compatibility test passes

---

## Recommended follow-up after v1

After this lands, the next two logical steps are:

1. plug in realism/stress-test outputs to replace `unknown` realism flags
2. add a simple rule-based allocation recommendation layer that reads this summary rather than raw research files directly
