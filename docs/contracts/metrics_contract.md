# 指标口径（Phase 1）

## 年化收益

函数：`annual_return(period_returns, periods_per_year)`

约束：
- `period_returns` 必须是已经按有效评估频率聚合后的收益序列
- 日频回测传日收益 + 252
- 周频回测传周收益 + 52
- 月频回测传月收益 + 12

公式：
- 先对 period returns 复利得到总净值
- `years = len(period_returns) / periods_per_year`
- `annual = equity ** (1 / years) - 1`

## Benchmark 口径

- benchmark 必须与 strategy 使用同一 `rebalance_frequency`
- benchmark 只保留重采样后的日期收益
- 不允许 strategy 用周频而 benchmark 仍按全量日频累计

## Sharpe

- Phase 1 使用年化收益 / 年化波动率
- 无风险利率默认 0

## 最大回撤

- 基于 equity curve 的峰值回撤

## Turnover

- 使用相邻调仓时点持仓权重绝对变化之和

## 成本模型

- `cost = turnover * (commission_bps + slippage_bps) / 10000`
- Phase 1 采用统一简化模型，不引入冲击成本分层
