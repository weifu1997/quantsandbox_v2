# 指标口径（Phase 1，当前实现）

这份文档描述 **当前已经实现** 的回测与报告指标口径，重点是把代码中的真实定义写清楚，避免文档和实现出现偏差。

当前主要对应代码：
- `app/domain/backtest/performance_metrics.py`
- `app/domain/backtest/benchmark.py`
- `app/domain/backtest/engine.py`

---

## 1. 当前指标使用范围

当前这些指标主要用于：
- TopN 回测结果摘要
- benchmark 对照
- report JSON / Markdown 输出

当前主回测引擎入口：
- `run_topn_backtest(...)`

在 Phase 1 中，指标口径强调：
- 简单
- 一致
- 可测试
- 不引入过早复杂化

而不是追求所有真实交易细节都完全建模。

---

## 2. 周期频率口径

### `periods_per_year(freq)`

当前映射：
- `D -> 252`
- `W -> 52`
- `M -> 12`
- 其它未知值默认回落到 `52`

说明：
- Phase 1 里，年化相关指标完全依赖这个频率映射
- 因此 strategy 与 benchmark 必须共享同一 `rebalance_frequency`

---

## 3. `total_return`

### 函数
- `total_return(equity_curve: list[float]) -> float`

### 当前实现口径
- 若 `equity_curve` 为空，返回 `0.0`
- 否则返回：
  - `equity_curve[-1] - 1.0`

### 含义
假设净值曲线起点隐含为 `1.0`，则总收益率等于末尾净值减 1。

### 示例
- 若 `equity_curve = [1.02, 1.05, 1.10]`
- 则 `total_return = 0.10`

说明：
- 当前不单独存储初始净值点 `1.0`
- 直接基于累积后的曲线末点计算

---

## 4. `annual_return`

### 函数
- `annual_return(period_returns: list[float], periods_per_year: int) -> float`

### 当前实现口径
- 若 `period_returns` 为空，返回 `0.0`
- 若 `periods_per_year <= 0`，返回 `0.0`
- 否则：
  1. 将 period return 序列复利成净值
  2. `years = len(period_returns) / periods_per_year`
  3. 返回：
     - `equity ** (1 / years) - 1`

### 重要前提
`period_returns` 必须已经是**与评估频率一致**的收益序列，例如：

- 日频回测 -> 传日收益 + `252`
- 周频回测 -> 传周收益 + `52`
- 月频回测 -> 传月收益 + `12`

### 不允许的错误口径
- strategy 用周频调仓，但 annual return 却拿日收益去年化
- benchmark 用日频累计，而 strategy 用周频累计，再直接比较年化结果

---

## 5. `annual_volatility`

### 函数
- `annual_volatility(period_returns: list[float], periods_per_year: int) -> float`

### 当前实现口径
- 若样本数 `< 2`，返回 `0.0`
- 若 `periods_per_year <= 0`，返回 `0.0`
- 否则：
  1. 用总体方差（分母为 `n`，不是 `n-1`）计算 period return 方差
  2. 对方差开根号得到 period volatility
  3. 再乘 `sqrt(periods_per_year)` 年化

### 说明
- 当前实现使用总体方差，不做无偏样本方差修正
- 这在 Phase 1 是一个明确且稳定的口径，只要 strategy / benchmark 一致即可

---

## 6. `sharpe_ratio`

### 函数
- `sharpe_ratio(period_returns: list[float], periods_per_year: int, risk_free_rate: float = 0.0) -> float`

### 当前实现口径
- 先计算 `annual_volatility(...)`
- 若年化波动率几乎为 0（`<= 1e-12`），返回 `0.0`
- 否则：
  - `(annual_return - risk_free_rate) / annual_volatility`

### 默认假设
- `risk_free_rate = 0.0`

### 说明
- 当前 Sharpe 使用年化收益 / 年化波动率
- 不做更复杂的风险自由利率曲线处理

---

## 7. `max_drawdown`

### 函数
- `max_drawdown(equity_curve: list[float]) -> float`

### 当前实现口径
- 若净值曲线为空，返回 `0.0`
- 否则遍历净值曲线：
  - 维护历史峰值 `peak`
  - 计算当前回撤 `dd = value / peak - 1`
  - 记录最差回撤
- 最终返回回撤绝对值

### 输出特点
- 返回值为**正数**
- 例如最差回撤是 `-0.18`，函数返回 `0.18`

说明：
- 这是一个需要在文档里明确的实现口径，因为有些系统会保留负号

---

## 8. `win_rate`

### 函数
- `win_rate(period_returns: list[float]) -> float`

### 当前实现口径
- 若收益序列为空，返回 `0.0`
- 否则：
  - 统计 `x > 0` 的 period return 占比

### 说明
- 当前只把**严格大于 0** 计为赢
- `0` 不计为赢

---

## 9. `turnover_from_holdings`

### 函数
- `turnover_from_holdings(previous: dict[str, float], current: dict[str, float]) -> float`

### 当前实现口径
- 对前后两期所有持仓名称取并集
- 对每个标的计算权重变化绝对值
- 最终求和

即：
- `sum(abs(current_w - previous_w))`

### 示例
若：
- 上期：`{"a": 0.5, "b": 0.5}`
- 本期：`{"b": 0.5, "c": 0.5}`

则换手率为：
- `|0 - 0.5| + |0.5 - 0.5| + |0.5 - 0| = 1.0`

说明：
- 当前是简单权重变化口径
- 不做更复杂的成交量/价格冲击修正

---

## 10. 成本模型口径

当前成本来自：
- `estimate_transaction_cost(turnover, commission_bps, slippage_bps)`

在主回测流程里：
1. 先根据前后持仓计算 `turnover`
2. 再根据手续费 + 滑点计算成本
3. `net = gross - cost`

当前采用的 Phase 1 简化口径为：
- `cost = turnover * (commission_bps + slippage_bps) / 10000`

说明：
- 不引入冲击成本分层
- 不做单边/双边更复杂拆分
- 先保证口径统一，后续再扩展

---

## 11. Benchmark 口径

### 当前 benchmark 入口
- `run_benchmark(dataset, return_col, benchmark, rebalance_frequency)`

### 当前已实现 benchmark
- `equal_weight_universe`

### `run_equal_weight_universe_benchmark(...)` 当前实现口径
1. 使用与 strategy 相同的 `return_col`
2. 使用与 strategy 相同的 `rebalance_frequency`
3. 对每个 rebalance date：
   - 取该横截面所有样本的 return 均值
4. 输出：
   - `dates`
   - `returns`
   - `equity_curve`

### 重要约束
- benchmark 必须与 strategy 使用同一 `rebalance_frequency`
- benchmark 只保留重采样后的日期收益
- 不允许 strategy 用周频而 benchmark 仍按全量日频累计

这点当前在实现和文档中是一致的。

---

## 12. `run_topn_backtest(...)` 当前输出指标

当前 TopN 回测主输出 payload 至少包括：

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
- `win_rate`
- `cost_paid`
- `holdings_by_rebalance_date`
- `equity_curve`
- `benchmark_equity_curve`
- `benchmark_returns`
- `excess_return_vs_benchmark`

### 指标来源
- `annual_return` -> `annual_return(...)`
- `total_return` -> `total_return(...)`
- `max_drawdown` -> `max_drawdown(...)`
- `sharpe` -> `sharpe_ratio(...)`
- `turnover` -> 各调仓期换手率均值
- `win_rate` -> `win_rate(...)`
- `cost_paid` -> 每期成本累计和
- `excess_return_vs_benchmark` ->
  - `strategy total_return - benchmark total_return`

说明：
- `excess_return_vs_benchmark` 当前使用的是**总收益差**，不是 annualized alpha
- 这是一个已实现、且应在文档中明确的 Phase 1 口径

---

## 13. 当前实现中的明确简化

### 13.1 不做更复杂的风险指标体系
当前没有：
- Sortino
- Calmar
- Information Ratio
- Alpha / Beta
- Tracking Error

### 13.2 不做成交层级微观模拟
当前没有：
- 撮合引擎
- 涨跌停成交约束
- 容量限制
- 冲击成本曲线

### 13.3 不区分 gross return / net return 序列的独立输出
当前引擎内部会算：
- gross
- cost
- net

但最终 report 主要暴露的是 net 结果和累计成本。

### 13.4 benchmark 只有一个实现
当前仅支持：
- `equal_weight_universe`

---

## 14. Phase 1 红线

为了避免后续口径漂移，当前应坚持这几条：

1. 年化收益、年化波动率、Sharpe 只能有一份实现来源
2. strategy 与 benchmark 必须共享相同频率口径
3. 最大回撤必须明确是返回正数绝对值
4. turnover 口径必须固定为持仓权重绝对变化之和
5. cost model Phase 1 先保持统一简化，不随不同调用点改变

只要这些红线不被破坏，Phase 1 的回测结果口径就是稳定的。
