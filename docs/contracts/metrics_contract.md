# 指标口径（当前实现）

这份文档描述 `QuantSandbox_v2` **当前已经实现** 的回测与报告指标口径。重点不是描述最初的 Phase 1 简化设计，而是把当前代码里真实存在的收益、成本、换手、执行与诊断口径写清楚，避免文档继续误导成“只有简单 TopN + 简单成本”的系统。

主要对应代码：

- `app/domain/backtest/performance_metrics.py`
- `app/domain/backtest/cost_model.py`
- `app/domain/backtest/dynamic_impact_model.py`
- `app/domain/backtest/engine.py`
- `app/domain/backtest/benchmark.py`

---

## 1. 当前指标适用范围

当前这些指标主要用于：

- TopN 回测结果摘要
- benchmark 对照
- report JSON / Markdown 输出
- ledger / execution diagnostics 上游数据

当前主回测引擎入口：

- `run_topn_backtest(...)`

当前系统已经不是“纯简化研究回测”，而是带有以下扩展能力的回测引擎：

- turnover limit
- board-lot 约束
- delayed execution return（仅研究标签，不再直接充当真实收益）
- volatility-aware execution slippage
- dynamic impact cost
- per-name accounting
- cash accounting
- execution diagnostics

因此文档中的成本与收益口径必须同时覆盖这些实现事实。

> 2026-05-23 口径修正：growth 正式回测结果已切换为 **真实逐股逐期盯市（mark-to-market by close）**。`future_return_* / delayed_future_return_*` 仍保留在数据集里作为研究标签、排序/覆盖率校验字段，但**不再代表真实账本收益**，也不应再被解释为可审计交易收益。

---

## 2. 周期频率口径

### `periods_per_year(freq)`

当前映射：

- `D -> 252`
- `W -> 52`
- `M -> 12`
- 其它未知值默认回落到 `52`

说明：

- 所有年化收益、年化波动率、Sharpe 都依赖这个映射
- strategy 与 benchmark 必须共享同一 `rebalance_frequency`

---

## 3. `total_return`

### 函数

- `total_return(equity_curve: list[float]) -> float`

### 当前实现口径

- 若 `equity_curve` 为空，返回 `0.0`
- 否则返回：
  - `equity_curve[-1] - 1.0`

含义：

- 净值曲线隐含初始值为 `1.0`
- 总收益率 = 末尾净值 - 1

---

## 4. `annual_return`

### 函数

- `annual_return(period_returns: list[float], periods_per_year: int) -> float`

### 当前实现口径

- 若 `period_returns` 为空，返回 `0.0`
- 若 `periods_per_year <= 0`，返回 `0.0`
- 否则：
  1. 将 period returns 复利成净值
  2. `years = len(period_returns) / periods_per_year`
  3. 返回：
     - `equity ** (1 / years) - 1.0`

重要前提：

- `period_returns` 必须已经和评估频率一致
- 周频回测要传周收益 + `52`
- 月频回测要传月收益 + `12`

---

## 5. `annual_volatility`

### 函数

- `annual_volatility(period_returns: list[float], periods_per_year: int) -> float`

### 当前实现口径

- 若样本数 `< 2`，返回 `0.0`
- 若 `periods_per_year <= 0`，返回 `0.0`
- 否则：
  1. 用总体方差（分母 `n`）计算 period returns 方差
  2. 开根号得到 period volatility
  3. 再乘 `sqrt(periods_per_year)` 年化

说明：

- 当前实现使用 `ddof=0`
- 这是系统当前固定口径，不是文档假设

---

## 6. `sharpe_ratio`

### 函数

- `sharpe_ratio(period_returns: list[float], periods_per_year: int, risk_free_rate: float = 0.0) -> float`

### 当前实现口径

- 先算 `annual_volatility(...)`
- 若波动率极小（`<= 1e-12`），返回 `0.0`
- 否则返回：
  - `(annual_return - risk_free_rate) / annual_volatility`

默认：

- `risk_free_rate = 0.0`

---

## 7. `max_drawdown`

### 函数

- `max_drawdown(equity_curve: list[float]) -> float`

### 当前实现口径

- 若净值曲线为空，返回 `0.0`
- 遍历净值曲线，维护 `peak`
- 当前回撤：
  - `dd = value / peak - 1.0`
- 记录最差回撤后返回其绝对值

输出特点：

- 返回值为**正数**
- 例如最差回撤是 `-0.18`，函数返回 `0.18`

---

## 8. `win_rate`

### 函数

- `win_rate(period_returns: list[float]) -> float`

### 当前实现口径

- 若收益序列为空，返回 `0.0`
- 否则统计 `x > 0` 的 period return 占比

说明：

- `0` 不计为赢

---

## 9. `turnover_from_holdings`

### 函数

- `turnover_from_holdings(previous: dict[str, float], current: dict[str, float]) -> float`

### 当前实现口径

- 对前后两期持仓 ticker 做并集
- 计算每个 ticker 的权重变化绝对值
- 最终求和

即：

- `sum(abs(current_w - previous_w))`

说明：

- 这是**组合权重变化口径**
- 不是成交金额 / AUM 的二次换算口径

---

## 10. turnover limit 口径

当前回测引擎支持：

- 年化换手上限

来源：

- dataset attrs：`growth_turnover_annual_limit`

当前换算方式：

1. 先根据 `rebalance_frequency` 计算 `periods_per_year`
2. 单期换手上限：
   - `annual_limit / periods_per_year`

例如：

- 年化换手上限 = `3.0`
- 周频 `W -> 52`
- 单期上限约 = `3.0 / 52 = 0.0577`

### 当前一个重要实现细节

首期调仓现在也受 turnover limit 约束。

当前实现：

- 若 `previous_holdings` 为空
- 不再直接 100% 满仓
- 而是把首期目标权重按 `turnover_limit` 比例缩放

这点会影响：

- 首期建仓速度
- annualized turnover
- growth line 历史结果与旧版本的对比

---

## 11. 基础交易成本口径

基础交易成本仍然来自：

- `estimate_transaction_cost(turnover, commission_bps, slippage_bps)`

在主回测中：

1. 先计算 `turnover`
2. 基础成本：
   - `base_cost = estimate_transaction_cost(...)`

其本质仍是基于：

- 换手率
- 佣金 bps
- 滑点 bps

但这已经不是最终总成本。

---

## 12. 执行附加滑点口径（extra execution slippage）

当前引擎支持 execution-aware 额外滑点：

- `_extra_execution_cost_bps(...)`

依赖字段：

- `next_open_price`
- `open`
- `rolling_vol_20d`
- `rolling_vol_20d_hist_q80`

依赖 execution config attrs：

- `execution_tick_size`
- `execution_base_tick_slippage_ticks`
- `execution_high_vol_extra_tick_slippage_ticks`
- `execution_high_vol_quantile`
- `execution_minimum_roundtrip_ticks`

当前逻辑：

- 默认每笔交易至少有 base tick slippage
- 若滚动波动率进入高波动区间，再加 extra ticks
- 最终换算成 bps
- 对当前 rebalance 交易组合取平均附加 bps

该附加 bps 会叠加到基础 `slippage_bps` 上，形成：

- `base_cost = estimate_transaction_cost(turnover, commission_bps, slippage_bps + extra_slippage_bps)`

---

## 13. 动态冲击成本口径（dynamic impact cost）

当前系统已经实现动态冲击成本：

- `estimate_dynamic_impact_bps(trade_notional, daily_amount)`

对应模块：

- `app/domain/backtest/dynamic_impact_model.py`

当前逻辑：

1. 根据单笔 trade notional 与当日成交额 `amount`
2. 计算 participation rate
3. 按 participation bucket 映射到 impact bps：
   - `very_light`
   - `light`
   - `medium`
   - `heavy`
   - `extreme`
4. 将每个 ticker 的 impact cost 累加为本期 `impact_cost`

当前总成本：

- `cost = base_cost + impact_cost`

因此当前净收益口径是：

- `net = gross - cost`

不是旧文档里描述的“只有简单成本模型”。

---

## 14. delayed execution / return 列口径

`future_return_*` / `delayed_future_return_*` 现在仅作为**研究标签**存在，用于：

- 因子研究
- 候选排序评估
- execution-aware 研究分析

它们**不再直接充当真实交易账本收益口径**。

当前真实回测收益口径为：

- 调仓日先按 `next_open_price`（fallback `open`）确定目标成交股数与目标持仓名义金额
- 当期以 `close` 对真实持仓做逐股逐期盯市
- `end_notional = shares * close`
- `gross_pnl_cny = end_notional - post_trade_notional`
- `net_pnl_cny = gross_pnl_cny - allocated_cost_cny`

这意味着：

- strategy return 不再直接等于 `future_return_*` / `delayed_future_return_*` 的横截面加权平均
- benchmark 也应使用相同的真实价格盯市语义，而不是共享标签收益列
- 旧的“标签收益驱动的组合模拟”已降级为研究层能力，不应再解释为真实收益

---

## 15. board-lot 约束口径

当前引擎支持 A 股一手约束：

- 默认 lot size = `100`

来源：

- dataset attrs：
  - `board_lot_enabled`
  - `board_lot_size`

当前实现：

1. 按目标权重换算 target notional
2. 使用 `next_open_price`，若无则 fallback `open`
3. 计算原始股数
4. 按 `board_lot_size` 向下取整
5. 重新计算 actual notional
6. 以 `actual_notional / equity` 回写调整后权重

输出：

- `position_details_by_rebalance_date`

记录：

- `shares`
- `price`
- `target_notional`
- `actual_notional`
- `skipped`

---

## 16. 逐股与现金核算口径

当前引擎不仅输出聚合收益，还输出逐股和现金核算：

### 16.1 逐股会计核算

- `per_name_accounting_by_rebalance_date`

包含：

- `start_notional`
- `target_notional`
- `gross_pnl_cny`
- `trade_abs_notional`
- `trade_net_notional`
- `allocated_cost_cny`
- `post_trade_notional`
- `net_pnl_cny`
- `end_notional`

### 16.2 现金核算

- `cash_accounting_by_rebalance_date`

包含：

- `cash_start`
- `cash_trade_flow`
- `cash_end`
- `cost_cny`
- `gross_pnl_total_cny`
- `net_pnl_total_cny`

这意味着当前系统已经具备面向 ledger/report 的较细粒度会计输出，而不是只有摘要指标。

---

## 17. benchmark 口径

当前 benchmark 入口：

- `run_benchmark(dataset, return_col, benchmark, rebalance_frequency)`

当前已实现 benchmark：

- `equal_weight_universe`

当前 benchmark 口径：

1. 使用与 strategy 相同的 `return_col`
2. 使用与 strategy 相同的 `rebalance_frequency`
3. 对每个 rebalance date 求横截面平均收益
4. 输出：
   - `returns`
   - `equity_curve`

这意味着：

- benchmark 与 strategy 共享同一收益列语义
- 不允许 strategy 用 delayed return、benchmark 仍用另一种口径

---

## 18. `run_topn_backtest(...)` 当前主要输出

当前 TopN 回测 payload 至少包括：

### 18.1 摘要指标

- `factor_name`
- `horizon`
- `top_n`
- `rebalance_frequency`
- `weighting`
- `benchmark_name`
- `annual_return`
- `total_return`
- `max_drawdown`
- `sharpe`
- `turnover`
- `annualized_one_way_turnover`
- `win_rate`
- `cost_paid`
- `base_cost_paid`
- `impact_cost_paid`
- `total_cost_paid_with_impact`
- `excess_return_vs_benchmark`

### 18.2 持仓与收益轨迹

- `holdings_by_rebalance_date`
- `returns_by_rebalance_date`
- `gross_return_by_rebalance_date`
- `turnover_by_rebalance_date`
- `cost_by_rebalance_date`
- `equity_curve`
- `benchmark_equity_curve`
- `benchmark_returns`

### 18.3 执行与持仓细节

- `position_details_by_rebalance_date`
- `per_name_accounting_by_rebalance_date`
- `cash_accounting_by_rebalance_date`
- `execution_by_rebalance_date`
- `execution_diagnostics`

---

## 19. `execution_diagnostics` 当前口径

当前回测结果中会输出：

- `impact_model`
- `assumed_fill_mode`
- `bar_delay`
- `partial_fill_model_enabled`
- `avg_participation_rate`
- `p90_participation_rate`
- `max_participation_rate`
- `avg_dynamic_impact_bps`
- `p90_dynamic_impact_bps`
- `max_dynamic_impact_bps`
- `bucket_counts`
- `impact_cost_paid`
- `total_cost_paid_with_impact`
- `turnover_limit_per_rebalance`

这些字段已经是前端治理/ledger/realism 层的重要上游输入，不应继续被文档省略。

---

## 20. 当前实现中的明确简化

虽然当前回测比旧版本复杂很多，但仍有明确简化：

### 20.1 不是撮合级微观交易模拟

当前没有：

- 真实撮合引擎
- 涨跌停成交约束
- partial fill 真正落地
- order book / queue position 模拟

### 20.2 impact model 仍是分桶近似

当前动态冲击是：

- participation rate -> bucket -> impact bps

不是连续市场冲击曲线模型。

### 20.3 benchmark 仍然只有一个实现

当前仅支持：

- `equal_weight_universe`

---

## 21. 当前必须坚持的口径红线

为了避免后续继续漂移，当前文档应固定以下红线：

1. 年化收益、波动率、Sharpe 只有一份实现来源
2. strategy 与 benchmark 必须共享同一频率与同一 return 列口径
3. 最大回撤返回**正数绝对值**
4. turnover 口径固定为持仓权重变化绝对值求和
5. 总成本 = 基础交易成本 + execution 附加滑点 + 动态冲击成本
6. 首次调仓当前也受 turnover limit 约束
7. board-lot 向下取整是当前真实实现，不是可选注释行为

只要这些红线不变，系统的回测与报告口径才是稳定的。