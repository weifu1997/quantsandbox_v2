# Growth 回测收益真实性审计（2026-05-23）

> 状态更新：本文记录的是 **2026-05-23 修复前** 对旧收益口径的审计结论。随后已完成引擎改造，正式回测口径已切换为 **真实逐股逐期盯市（mark-to-market by close）**，旧的标签收益 fallback 已移除。本文保留作为问题来源与修复背景档案。

## 结论

当时的 `run_topn_backtest()` 高收益结果**不能视为真实逐股逐期盯市收益**。

更准确地说：

- 引擎内部 `equity / cash / per_name_accounting` 是自洽闭合的；
- 但该闭合口径来自 `future_return_* / delayed_future_return_*` 标签驱动的名义盈亏分配；
- 当使用 `data/raw/market/*.parquet` 的原始价格、真实持仓股数、真实调仓日期做外部独立重算时，结果与引擎输出发生系统性大偏差；
- 因此当前结果属于“标签收益驱动的组合模拟”，不是“原始行情逐股盯市的真实交易收益”。

## 关键证据

### 1. 引擎会计公式不是逐股价格盯市

`app/domain/backtest/engine.py` 关键逻辑：

- 先由样本标签收益计算 `per_name_gross`
- 再令 `gross_pnl_cny = contribution * current_equity_cny`
- 再令 `end_notional = post_trade_notional + gross_pnl_cny`

这意味着 `end_notional` 不是由 `shares * market_price` 直接得到，而是由标签收益反推。

### 2. 外部独立重算与引擎结果严重不一致

已用以下输入独立重算：

- `data/raw/market/*.parquet`
- `position_details_by_rebalance_date` 中真实持仓股数
- 调仓日期序列

重算方法：

- `raw_end_notional = shares * raw_market_close`
- `raw_gross_pnl = raw_end_notional - period_start_notional`
- `raw_net_like = raw_gross_pnl - allocated_cost`

核心结果：

- 引擎汇总 `sum_engine_net_total = 1,386,586.60293`
- 原始行情重算 `sum_raw_net_like_total = -178,229.39707`
- 差额 `-1,564,816.0`

这不是浮点误差，而是口径错误。

### 3. 个股期末市值与原始 close × shares 不一致

示例：`sh600641` 在 `2026-04-07`

- 原始行情 `close = 19.17`
- 持仓 `shares = 16500`
- 原始行情期末市值应为 `316,305`
- 引擎报告 `end_notional = 405,900`
- 差额 `-89,595`

类似偏差在多个日期、多只股票上重复出现，证明不是个别数据脏点。

## 当前系统应如何定性

当前 growth 回测结果应定性为：

- **研究标签驱动的组合模拟结果**

而不应定性为：

- **真实逐股逐期价格路径下的交易收益**

## 改造建议

### P0
将 `future_return_* / delayed_future_return_*` 降级为研究标签，不再直接充当真实账本收益。

### P0
把引擎改造成真实逐股逐期盯市：

1. 调仓日用执行价得到真实成交股数；
2. 记录调仓后持仓；
3. 下一评价日用真实市场价格对持仓盯市；
4. 组合收益来自 `shares * (mark_price - entry_or_prev_mark_price)`；
5. 现金、成本、卖出结转与组合资产严格闭合；
6. `per_name_accounting.end_notional` 必须可由 `shares * mark_price` 回推。

## 后续动作

- 增加失败测试，锁定真实盯市口径；
- 重构 `run_topn_backtest()`；
- 重跑 growth latest 报告并重新评估收益真实性。
