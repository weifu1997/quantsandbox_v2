# Dynamic Impact v1 Implementation Plan
**Document Version:** 1.1
**Date:** 2026-05-19
**Author:** Hermes (System)
**Status:** Ready for Engineering Execution
**Goal:** 将动态市场冲击成本模型接进回测引擎主收益，完成从“识别不真实”到“真实扣回”的跃迁。

---

## 0. 一句话定位
> 当前不缺发现能力（realism / capacity / gating），缺的是**把流动性失真定量回写到策略 PnL** 的执行建模能力。v1 的目标就是补上这一环：**让回测收益别再假装所有订单都能按固定滑点成交。**

---

## 1. 设计原则

### 原则 A：v1 不做完整 Execution Simulator
- **不做**：order book replay、部分成交撮合、intraday 分笔模拟、Almgren-Chriss 全套校准
- **只做**：参与率估计 → 动态冲击成本函数 → 回写主收益 → 可解释 diagnostics

### 原则 B：直接接入 Backtest Engine 成交成本层
- 不改 order simulator / execution simulator（如果尚未独立成熟）
- 在已有 rebalance execution 的 **成交价与成本计算** 环节插入 impact model
- 最短路径进入主收益，改动最小，最易对比

### 原则 C：v1 先实现“全成交 + 动态价格惩罚”
- 默认仍全成交，不对仓位做部分执行
- 根据参与率，成交成本非线性放大
- 极端参与率额外 hard warning / cap
- 预留未来部分成交接口，但 v1 不触发

---

## 2. 接入位置：Backtest Engine 的哪个层

### 接入点
```text
原流程：
生成目标持仓 → 计算买卖清单 → 应用固定佣金/滑点 → 更新净值

插入后：
生成目标持仓 → 计算买卖清单 → 计算 base 佣金/滑点
→ 计算 dynamic_impact_bps（按订单参与率）
→ effective_cost = base + impact
→ 更新净值
```

### 关键公式
```text
trade_notional_per_name = abs(target_position_value - current_position_value)
participation_rate = trade_notional_per_name / daily_amount
base_cost_bps = commission_bps + slippage_bps
effective_cost_bps = base_cost_bps + dynamic_impact_bps
```

### 口径说明（必须固定）
- `trade_notional_per_name`：**本次实际调仓金额**，不是最终目标持仓总金额
- `daily_amount`：调仓日该股票成交额
- `dynamic_impact_bps`：在 base cost 之上叠加的**额外冲击成本**，不是替代 slippage

### 为什么必须用 trade_notional 而不是 target_notional
因为 impact 是交易摩擦，不是持仓摩擦。真正吃流动性的，是本次 rebalance 的**买卖变化量**，不是最终想持有的仓位规模。

---

## 3. v1 参与率阈值与冲击惩罚表
采用分段非线性惩罚，经验参数如下（后续可升级为平滑函数或参数扫描）：

| 参与率区间 | 标签 | 额外冲击成本 (bps) |
|---|---|---:|
| `<= 0.5%` | `very_light` | 0 |
| `0.5% – 1.0%` | `light` | +10 |
| `1.0% – 2.0%` | `medium` | +25 |
| `2.0% – 3.0%` | `heavy` | +50 |
| `> 3.0%` | `extreme` | +100 |

### 设计理由
- 保守但不极端，可快速落地
- 已体现非线性：参与率越高，边际冲击加速恶化
- 方便后续升级为 `k * sqrt(participation_rate)` 平滑版

---

## 4. 部分成交 / 无法成交的处理范围

### v1 做
- 全成交（fill ratio = 1.0）
- 动态价格惩罚
- 极端参与率报警
- diagnostics 记录 heavy/extreme bucket 次数

### v1 不做
- 未成交仓位递延
- 部分 fill ratio 计算
- 下期补成交逻辑
- 残单状态持久化

### 预留接口
所有输出结构中增加 `partial_fill_model_enabled: false` 等字段，保证 v2 可平滑升级。

---

## 5. 输出字段设计

### 5.1 Backtest 结果新增 `execution_diagnostics`
```json
{
  "execution_diagnostics": {
    "impact_model": "dynamic_impact_v1",
    "assumed_fill_mode": "full_fill_with_impact_penalty",
    "partial_fill_model_enabled": false,
    "avg_participation_rate": 0.0082,
    "p90_participation_rate": 0.0215,
    "max_participation_rate": 0.0470,
    "avg_dynamic_impact_bps": 18.5,
    "p90_dynamic_impact_bps": 50.0,
    "max_dynamic_impact_bps": 100.0,
    "bucket_counts": {
      "very_light": 120,
      "light": 45,
      "medium": 18,
      "heavy": 7,
      "extreme": 3
    },
    "impact_cost_paid": 0.0123,
    "total_cost_paid_with_impact": 0.0208
  }
}
```

### 5.2 每个调仓日的摘要
```json
{
  "execution_by_rebalance_date": {
    "2025-07-04": {
      "avg_participation_rate": 0.006,
      "max_participation_rate": 0.018,
      "impact_cost_bps": 14.0,
      "extreme_count": 0
    }
  }
}
```

### 5.3 字段归属（必须固定）
#### backtest engine 负责输出
- `execution_diagnostics`
- `execution_by_rebalance_date`
- `impact_cost_paid`
- `total_cost_paid_with_impact`

#### realism 负责输出
- `impact_realism.status`
- `impact_realism.note`
- `impact_realism.snapshot`

#### capacity 负责输出
- 在现有 `liquidity_capacity` 结论基础上消费 impact diagnostics 作为增强输入
- **v1 不重定义 backtest 字段，不承诺完整重建容量模型**

#### decision summary 负责输出
- `working_config_recommendation`
- `additive_eligibility`
- `promotion_blockers`
- `demotion_triggers`

---

## 6. impact 数据如何被下游消费

### 6.1 realism
读取：
- `avg_dynamic_impact_bps`
- `p90_dynamic_impact_bps`
- `bucket_counts`
- `extreme_bucket_ratio`

新增：
```json
"impact_realism": {
  "status": "acceptable | warning | elevated",
  "note": "...",
  "snapshot": {
    "avg_participation_rate": 0.0082,
    "p90_participation_rate": 0.0215,
    "avg_dynamic_impact_bps": 18.5,
    "extreme_bucket_ratio": 0.03
  }
}
```

### 6.2 capacity
v1 只做**增强**，不做完整重构。
读取：
- `avg_dynamic_impact_bps`
- `p90_participation_rate`
- `max_participation_rate`
- `extreme_bucket_ratio`
- `impact_cost_paid`

用途：
- 增强当前 `acceptable / warning / elevated` 判定
- 作为未来容量模型重构的过渡层

### 6.3 gating summary
使用新字段改变：
- `working_config_recommendation`
- `additive_eligibility`
- `promotion_blockers`
- `demotion_triggers`

---

## 7. impact → gating 的 v1 分层规则（必须先写死）

### 7.1 impact realism 分层
| 条件 | 判定 |
|---|---|
| `avg_dynamic_impact_bps <= 10` 且 `extreme_bucket_ratio = 0` | `pass` |
| `avg_dynamic_impact_bps <= 25` 或 `p90_participation_rate > 1%` | `warn` |
| `avg_dynamic_impact_bps > 25` 或 `extreme_bucket_ratio > 5%` | `fail` |

### 7.2 gating 消费规则
- `impact_realism = fail` → promotion blocker
- growth 若 `review = pass` 但 `impact_realism = fail` → `keep_with_caution`
- value 若 `impact_realism = fail` → `ineligible`
- `extreme_bucket_ratio` 持续偏高 → 可进入 `demotion_triggers`

---

## 8. 第一个验证策略：Growth 主线
- 理由：当前 growth 呈现 “review pass, liquidity_risk elevated, capacity fail” 的典型 executable alpha 困境
- 对比：**old fixed-cost backtest vs dynamic impact v1 backtest**

### 输出要求
- impact before/after 报告
- annual return / Sharpe / turnover 变化
- executable alpha 损耗率
- base cost / impact cost / total cost 拆解

### 验证纪律（必须固定）
- before / after 必须是：**同策略、同窗口、同 universe、同参数**
- 不允许顺手改 universe / top_n / working config 再归因给 impact

---

## 9. 工程分期与任务拆解

## P0：核心模块与回测引擎接入
### 任务 1：`dynamic_impact_model.py`
- 输入：`trade_notional`, `daily_amount`
- 计算 `participation_rate`
- 应用分段阈值，返回 `dynamic_impact_bps`

### 任务 2：backtest engine 接入
- 在 rebalance 执行处，对每笔买卖调用 impact model
- 将返回的 bps 加到 `effective_cost` 中
- 更新净值

### 任务 3：单元测试
- 测试各参与率区间的边界
- 测试极端大单、零成交额等边界情况

## P1：诊断输出与下游消费
### 任务 4：`execution_diagnostics` 生成
- 回测结束时汇总全部调仓日的 impact 数据
- 输出上述 JSON 结构

### 任务 5：realism / capacity 消费新字段
- realism 读取新字段，更新 `impact_realism` 判定
- capacity 读取 impact diagnostics，增强当前容量判定

## P2：gating summary 更新
### 任务 6：gating summary 消费 impact 数据
- 根据扣后收益和 impact realism，自动调整 `working_config_recommendation`
- 例如：impact realism fail → `keep_with_caution` / `ineligible`

## P3：Growth 主线头对头验证
### 任务 7：跑 growth 主线
- 输出固定成本 vs 动态冲击下的收益对比
- 生成 executable alpha 损耗报告

---

## 10. v1 参数配置文件（建议）
```yaml
dynamic_impact_v1:
  enabled: true
  fill_mode: full_fill_with_impact_penalty
  participation_buckets:
    - max_rate: 0.005
      label: very_light
      impact_bps: 0
    - max_rate: 0.010
      label: light
      impact_bps: 10
    - max_rate: 0.020
      label: medium
      impact_bps: 25
    - max_rate: 0.030
      label: heavy
      impact_bps: 50
    - max_rate: 1.000
      label: extreme
      impact_bps: 100
```

---

## 11. 完成标准
- 所有策略回测时，`effective_cost` 包含动态冲击成本
- 回测输出中包含 `execution_diagnostics` 字段
- realism / capacity / gating summary 明确消费新数据
- growth 主线完成 head-to-head 对比，产出真实收益损耗
- 单元测试覆盖所有参与率区间和边界

### 新增验收项
- before / after 对比必须保持同策略、同窗口、同 universe、同参数
- growth head-to-head 必须输出成本拆解：
  - `base_cost_paid`
  - `impact_cost_paid`
  - `total_cost_paid_with_impact`
  - `annual_return_delta`
  - `sharpe_delta`

---

## 12. 下一步行动
1. 确认本计划：无重大调整后直接进入 P0
2. 启动实现：从 `dynamic_impact_model.py` 和 backtest engine 接入开始
3. 并行准备：realism / capacity 读取新字段的适配方案

这一步一旦做进去，系统的诚实度会立刻提高一个层级——从“知道不真实”进化到“把不真实真实扣回”。

---

**End of Plan**
