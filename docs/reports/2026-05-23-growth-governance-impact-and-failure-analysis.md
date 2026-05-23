# Growth 策略真实收益口径切换后的治理影响与失效原因分析

日期：2026-05-23

## 1. 结论摘要

本次已确认：

1. 回测正式收益口径已从研究标签驱动收益切换为**真实逐股逐期盯市**。
2. growth 当前正式结果为 **-13.234386%**，benchmark 为 **-3.201611%**，超额收益约 **-10.03%**。
3. deployability / allocator 治理链路已重跑，当前结论仍然是 **blocked / stop_using**，没有因为口径切换而意外“放行”。
4. 当前治理主字段已完成更新：working config 与 decision summary 都已明确把 growth 从“执行锚点”降级为“待重构研究候选”。
5. growth 失效的主因不是成本，而是**真实价格路径下组合本身没有兑现研究标签暗示的高收益**，并且相对 benchmark 明显跑输。

---

## 2. 本次核查范围

本次实际核查/重跑了以下治理产物：

- `scripts/run_current_working_config_pipeline.py`
- `scripts/build_research_decision_summary.py`
- `scripts/run_strategy_line_allocator.py`
- `scripts/sync_current_working_config.py`

重跑结果：
- growth_review：成功
- value_review：成功
- realism：成功
- capacity：成功
- scale_stress：成功
- decision_summary：成功
- strategy_line_allocator：成功
- sync_working_config：成功

说明：当前治理链路**可执行**，不是 pipeline 故障。

---

## 3. 真实收益口径下的正式结果

### growth
- total_return_pct = **-13.234386%**
- annual_return ≈ **-5.918%**
- sharpe ≈ **-0.4708**
- max_drawdown ≈ **19.49%**

### benchmark
- benchmark_total_return_pct = **-3.201611%**

### 超额
- excess_return_vs_benchmark_pct ≈ **-10.032775%**

结论：
> growth 不仅亏损，而且在统一真实价格口径下明显跑输 benchmark。

---

## 4. growth 失效原因分析

## 4.1 不是成本主导

当前总成本约：
- `cost_cny_total = 3936.39`

约占 10 万本金的 3.94%。

这不足以解释：
- 总收益 -13.23%
- 相对 benchmark 落后约 10 个百分点

因此主因不是：
- 手续费
- 滑点
- 冲击成本
- 一手约束本身

## 4.2 主因是价格路径真实化后，组合本身没有跑出来

旧口径把 `future_return_* / delayed_future_return_*` 研究标签直接当作真实持仓收益；
新口径改成 `entry -> close` 逐股盯市后，实际持仓路径无法复现这些高收益。

也就是说：
> 研究标签曾经高估了真实可执行收益，真实组合路径并未兑现研究阶段暗示的 alpha。

## 4.3 组合层面存在多次真实回撤

历史期度归因显示，存在多次明显负收益调仓期；虽然也有个别正收益阶段，但无法覆盖整体回撤。

这说明不是单一股票问题，而是：
- 真实持仓路径波动更差
- 正收益阶段持续性不够
- 回撤阶段的组合暴露更痛

## 4.4 相对 benchmark 也失效

统一真实口径后，growth 依然落后 benchmark，说明问题不是“市场不好一起跌”，而是：
> growth 这套真实可执行组合没有形成稳定正 alpha。

---

## 5. deployability / allocator 治理影响

## 5.1 当前治理结论仍然是 blocked

### current_working_strategy_config.json
当前仍显示：
- `operating_mode = governance_needs_revision`
- growth.deployability.deployment_blocked = `true`
- value_primary.deployability.deployment_blocked = `true`

### strategy_line_allocator_latest.json
当前仍显示：
- `allocator_status.status = blocked`
- `reason = growth core revgrowth_always_on_v1 is deployment_blocked by deployability schema`

结论：
> allocator 的 blocked 结论仍然成立，而且与当前真实口径下的负收益并不冲突。

## 5.2 decision summary 已吸收真实收益失败

重跑后的 `research_decision_summary_latest.json` 现在显示：
- `working_config_recommendation.status = needs_revision`
- `growth_review = pass`
- `growth_realism = fail`
- `growth_capacity = fail`
- `growth_scale_stress = warn`
- `growth_realized_backtest = fail`

但其 executive / mainline narrative 仍然保留：
- “Growth remains the cleaner line ...”
- “growth remains the execution anchor ...”
- `keep_rule_status = keep`

这和当前真实收益结论 **-13.23% 且跑输 benchmark** 存在明显叙事滞后。

结论：
> 当前治理链路在“可部署性阻断”上是对的，但在“主线叙事 / working config 推荐语义”上仍然偏旧。

---

## 6. 关键判断

### 已正确的部分
1. 正式回测收益口径已真实化
2. benchmark 已统一到真实价格口径
3. deployability / allocator 仍能正确阻断不可部署策略
4. working-config pipeline 可重跑且未崩溃

### 仍需修正的部分
1. `current_working_strategy_config.json` 里的主线叙事仍过于偏向旧 growth-anchor 逻辑
2. `research_decision_summary_latest.json` 的 executive narrative 对真实负收益吸收不足
3. scale stress / deployability 判断仍大量依赖旧研究治理维度，尚未把“真实收益为负且跑输基准”提升为更强的决策输入

---

## 7. 建议优先级

## P0
**把真实收益失败纳入 working-config / decision-summary 的显式决策输入**

建议增加明确字段，例如：
- `growth_realized_backtest_status = fail`
- `growth_benchmark_relative_status = fail`
- `working_config_recommendation.status = stop_using`（若治理规则认可）

## P0
**下调 current working config 的主线叙事强度**

应避免继续保留：
- “growth remains the execution anchor”

更合适的表述应是：
- growth 暂为研究主线候选，但当前真实可执行回测未通过，不能视为正式执行锚点

## P1
**扩展 decision summary 的决策规则**

目前更偏重：
- review
- realism
- capacity
- scale stress

建议补充：
- 真实盯市后 total_return 是否为正
- 相对 benchmark 是否为正
- 若二者同时失败，working config 自动降级到 `stop_using` 或至少 `suspended`

---

## 8. 最终结论

本次真实收益口径切换后，QuantSandbox 的治理链路并没有“误放行” growth；deployability 与 allocator 仍保持 blocked，这一层是正确的。

但新的正式事实已经很明确：
> growth 在真实逐股逐期盯市口径下总收益约 **-13.23%**，且显著跑输 benchmark。

因此，当前最需要修的不是 allocator，而是：
1. working config 叙事
2. decision summary 的决策输入
3. growth 作为“执行主线”的默认定位

在这些未更新前，系统虽然会阻断部署，但上层治理文案仍会给人“growth 还是主线、只是需要修订”的印象，这已经落后于真实收益证据。