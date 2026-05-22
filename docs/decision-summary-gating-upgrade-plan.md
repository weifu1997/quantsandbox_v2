# Decision Summary Gating Upgrade Plan

> **文档状态：部分实现**
> 
> gating/realism/capacity 已经进入当前系统的重要判断链，但本文描述的顶层 machine-readable blocks（如 `working_config_recommendation`、`additive_eligibility`）未必已全部冻结为最终 schema，因此属于“部分实现”。

> 目标：把 realism / capacity 从展示层升级为 decision summary 的主判断输入，让系统对 working config、加仓资格、升级阻塞、降级触发给出机器可读且可执行的结论。

## 当前状态

当前系统已经具备：
- current working config artifact
- review / realism / capacity / decision summary pipeline
- allocation guidance
- pipeline 一键执行入口

但当前问题是：
- realism / capacity 仍主要用于“展示”和“文字建议”
- 决策主判断仍偏向 review / candidate status
- summary 没有正式输出：
  - working_config_recommendation
  - additive_eligibility
  - promotion_blockers
  - demotion_triggers

这导致系统还不是一个严格的收益决策器，而更像研究控制面板。

---

## 设计目标

新增四个正式判定块，并让它们进入 summary 顶层：

1. `working_config_recommendation`
2. `additive_eligibility`
3. `promotion_blockers`
4. `demotion_triggers`

要求：
- review 不是唯一主判断
- realism / capacity 拥有正式否决权
- warning / fail 分层明确
- 输出机器可读，可被后续资金动作层直接消费

---

## 顶层输出 schema

### 1. working_config_recommendation

```json
{
  "working_config_recommendation": {
    "status": "keep | keep_with_caution | needs_revision | stop_using",
    "reason": "...",
    "decision_inputs": {
      "growth_review": "pass | warn | fail",
      "value_review": "pass | warn | fail",
      "growth_realism": "pass | warn | fail",
      "value_realism": "pass | warn | fail",
      "growth_capacity": "pass | warn | fail",
      "value_capacity": "pass | warn | fail"
    }
  }
}
```

### 2. additive_eligibility

```json
{
  "additive_eligibility": {
    "revgrowth_always_on_v1": "eligible | conditional | ineligible",
    "pbindlow_downtrend_narrow_quality_v1": "eligible | conditional | ineligible"
  }
}
```

### 3. promotion_blockers

```json
{
  "promotion_blockers": {
    "pbindlow_downtrend_narrow_quality_v1": [
      "latest review_result=watch",
      "cost_sensitivity=elevated",
      "liquidity_risk=elevated",
      "capacity constraint breach present"
    ]
  }
}
```

### 4. demotion_triggers

```json
{
  "demotion_triggers": {
    "revgrowth_always_on_v1": [
      "latest review_result becomes watch",
      "cost_sensitivity turns elevated",
      "capacity status worsens to elevated",
      "working config alignment becomes needs_review"
    ]
  }
}
```

---

## 统一判定口径

## A. review 信号分层

### pass
满足：
- candidate status = active
- latest review_result = keep
- recent_review_trend ∈ {stable_keep}

### warn
满足其一：
- candidate status = watch
- latest review_result = keep 但 recent_review_trend = recent_weakening
- latest review_result = watch 但仍为 official primary candidate

### fail
满足其一：
- latest review_result = watch 且 recent_review_trend 持续恶化
- candidate 不再具备主线资格

说明：v1 里对 growth / value 可以简化为：
- active + latest keep -> pass
- watch 或 recent_weakening -> warn
- 明确连续退化 / 非主线 -> fail

---

## B. realism 判定分层

从 realism flags 聚合：
- cost_sensitivity
- liquidity_risk
- concentration_risk
- execution_realism

### pass
- 无 elevated
- warning 数量 <= 1

### warn
- 至少 1 个 warning
- 或 1 个 elevated 但不属于核心否决项

### fail
满足其一：
- cost_sensitivity = elevated
- liquidity_risk = elevated
- execution_realism = elevated

注：
- concentration warning 不直接 fail
- cost/liquidity elevated 在当前项目语境下应视为强阻塞

---

## C. capacity 判定分层

从 capacity report 的 `liquidity_capacity.status` 提取。

### pass
- acceptable

### warn
- warning

### fail
- elevated
- 或 constraint_breach = true

说明：当前阶段 capacity fail 对 promotion 拥有正式否决权。

---

## D. 主判断原则

### 1. working config recommendation

#### keep
满足：
- growth_review = pass
- growth_realism ≠ fail
- growth_capacity ≠ fail
- no superior alternative needed
- current working config alignment = aligned

#### keep_with_caution
满足：
- growth_review = pass
- 但 growth_realism = warn 或 growth_capacity = warn
- 或 value 仍为 ineligible / blocked

#### needs_revision
满足其一：
- growth_review = warn
- growth_realism = fail
- growth_capacity = fail
- config_alignment = needs_review

#### stop_using
满足其一：
- growth_review = fail
- growth_realism = fail 且 growth_capacity = fail
- 当前 working config 在现实约束下不可继续执行

---

### 2. additive eligibility

#### eligible
- review = pass
- realism = pass
- capacity = pass

#### conditional
- review = pass
- realism = warn 或 capacity = warn

#### ineligible
满足其一：
- review = warn/fail
- realism = fail
- capacity = fail

说明：
- value 当前大概率应为 ineligible
- growth 当前大概率是 conditional（因为 liquidity/capacity 仍有现实约束）

---

### 3. promotion blockers

适用于不满足 eligible 的对象。

阻塞源包括：
- latest review_result = watch
- recent_review_trend = recent_weakening / persistent_watch
- cost_sensitivity = elevated
- liquidity_risk = elevated
- capacity status = elevated
- constraint_breach = true

要求：
- blocker 必须逐条列出，不能只给抽象结论

---

### 4. demotion triggers

对当前 active/working lines 输出未来触发条件，不是当前事实复述。

growth 核心触发建议：
- latest review_result becomes watch
- recent_review_trend leaves stable_keep
- cost_sensitivity turns elevated
- capacity status turns elevated
- working config alignment becomes needs_review

value 观察线触发建议：
- 如果继续 watch 且 realism/capacity 无改善，则维持 observe_only
- 如果连续新窗口继续恶化，可进入 retirement / deeper restriction discussion

---

## 推荐的 v1 接入顺序

### P0
1. 在 `build_research_decision_summary.py` 内新增：
   - review/realism/capacity 分层函数
   - 顶层四个新输出块
2. 不改 realism/capacity 计算逻辑，只消费现有 artifacts
3. 先保持 allocation guidance 不动，只新增 gating 判定

### P1
4. 让 allocation guidance 改为消费：
   - working_config_recommendation
   - additive_eligibility
5. 把 open_risks / portfolio_actions wording 改为引用这些新判定

### P2
6. 后续再让资金动作层直接基于 gating outputs 做档位建议

---

## 当前项目下的预期落地结果

在当前真实数据下，v1 很可能会输出：

### growth
- review = pass
- realism = fail 或 warn（取决于 elevated 是否视作 fail）
- capacity = fail / warn
- additive_eligibility = conditional

### value
- review = warn
- realism = fail
- capacity = fail
- additive_eligibility = ineligible
- promotion_blockers = 明确列出 watch + elevated + breach

### working config
- 不是“纯 keep”
- 更可能是：`keep_with_caution`

这比现在的简单 keep 更诚实，也更接近真实收益决策。

---

## 验证要求

实现后要验证：
1. summary 顶层新增四个块
2. value 当前必须显示：
   - additive_eligibility = ineligible
   - blockers 非空
3. growth 当前不能被错误判为 fully eligible
4. working config 不应忽略 realism/capacity 的 elevated 情况
5. markdown 版本要新增对应 sections

---

## 一句话结论

Direction A 的目标不是再增加报告字段，而是把 realism/capacity 提升为正式决策门槛，让 decision summary 真正具备“允许做 / 允许加 / 禁止升 / 何时降”的收益治理能力。
