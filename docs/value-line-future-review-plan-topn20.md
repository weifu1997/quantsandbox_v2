# Value Line Future Review Plan (top_n=20)

> **文档状态：历史方案**
> 
> 本文对应某一阶段对 value line 的 forward review 计划。当前系统重点已更多转向 growth working config、deployability、allocator 与统一治理链，因此本文保留为历史 review 计划背景。

**Goal:** Continue forward review of the official value-line primary candidate under the new operating default (`top_n=20`) without reopening governance or allocator work.

**Current official state:**
- Primary candidate: `pbindlow_downtrend_narrow_quality_v1`
- Role: `primary_candidate`
- Status: `watch`
- Operating default: `top_n=20`
- Legacy baseline: `pbindlow_downtrend_only_v1`

---

## Why this plan exists

The candidate-pool role is already settled.
The only thing that now matters is whether the current primary candidate continues to hold up in future windows **under the new official parameterization**.

Do **not** reopen:
- allocator tuning as the main line
- governance-role reshuffling
- old `top_n=10` as the main operating default

---

## Review trigger rule

Run the next formal review only when a genuinely new forward window is available.

### Trigger
Run a new review when both are true:
1. market/fundamental data has advanced beyond `2026-05-14`
2. the new window is large enough to form a meaningful review slice

### Minimum practical window
Prefer one of:
- next half-year style window
- next quarter window
- or another clearly labeled forward slice with enough active dates

---

## Official review principle

All future reviews must use the **registry current params**.

That means for the primary candidate:
- `top_n=20`
- not `top_n=10`

`top_n=10` may still be used as an auxiliary reference in ad-hoc analysis, but it is **no longer the main operating default**.

---

## Next formal review command template

```bash
cd /root/project/quantsandbox_v2 && \
REVIEW_ID=review_quality_<WINDOW_ID> \
WINDOW_LABEL=<WINDOW_LABEL> \
START_DATE=<START_DATE> \
END_DATE=<END_DATE> \
SAMPLE_NAME=expanded_main_board_1000 \
SAMPLE_LIMIT=1000 \
make pbindlow-review
```

### Example next-run shape

```bash
cd /root/project/quantsandbox_v2 && \
REVIEW_ID=review_quality_2026Q3 \
WINDOW_LABEL=2026Q3 \
START_DATE=20250701 \
END_DATE=20250930 \
SAMPLE_NAME=expanded_main_board_1000 \
SAMPLE_LIMIT=1000 \
make pbindlow-review
```

Use this only when the underlying dataset actually supports the window you want to review.

---

## Immediate post-run checks

After every future review, inspect these files first:

1. `data/reports/pbindlow_candidate_pool_status_20260517.json`
2. `data/reports/strategy_candidate_pool_overview_20260517.json`
3. `data/reports/pbindlow_candidate_reviews.json`

Confirm:
- primary candidate is still `pbindlow_downtrend_narrow_quality_v1`
- role did not drift
- old baseline was not accidentally re-promoted
- latest review row used the current parameter regime (`top_n=20` via registry)
- recent trend changed in a way consistent with the new review result

---

## What to evaluate after the next review

### Pool-level
- `primary_candidate`
- `enhanced_candidate`
- `active_count`
- `watch_count`

### Primary-candidate fields
- `status`
- `review_count`
- `latest_result`
- `recent_review_trend`
- `suggested_action`

### Metrics to read directly
- `annual_return`
- `sharpe`
- `max_drawdown`
- `top_bottom_spread`
- `active_ratio`
- `rank_ic_mean`
- `positive_ic_ratio`
- `monotonicity_score`

---

## Decision framework for the next review

### Case A: keep improves again
Signal pattern:
- return/sharpe recover materially
- spread stops being clearly negative
- review result returns to `keep`

Interpretation:
- 2026H1 was a weakening window, not a breakdown
- the new `top_n=20` operating default is doing its job

Action:
- keep primary role
- consider whether watch should remain or later be relaxed after one more future window

### Case B: still weak but less bad than old top_n=10 history
Signal pattern:
- still `watch`
- but drawdown / sharpe / return profile is less damaged than the old narrow setting

Interpretation:
- candidate still needs observation
- parameter migration helped, but signal is not fully re-confirmed

Action:
- keep primary role
- keep `watch`
- wait for another future window before any governance change

### Case C: repeated future weakness
Signal pattern:
- another clearly weak forward review
- trend remains `watch` / deteriorates
- spread and monotonicity stay poor

Interpretation:
- this is no longer a one-window wobble

Action:
- keep governance disciplined
- prepare discussion on whether primary should remain only as a monitored research candidate
- do not jump straight into allocator tuning as a rescue move

---

## What not to do

Do not use the next review to justify:
- restoring `top_n=10` as the default without new evidence
- reopening simple allocator as the main priority
- changing candidate role based on one emotional reading of one window

---

## Recommended operating sequence from here

1. Freeze current governance and parameter state
2. Wait for genuinely new forward data
3. Run one formal future review with registry-driven `top_n=20`
4. Re-check status/overview/reviews
5. Only after that decide whether the candidate is stabilizing or remains in watch mode
