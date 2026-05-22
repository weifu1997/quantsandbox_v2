# QuantSandbox_v2 Docs Index

这份索引页的目的只有一个：**告诉后续读者先看什么、哪些文档代表当前事实、哪些只是历史方案或部分实现设计。**

如果你是第一次进入 `quantsandbox_v2`，请不要随机点开文档。优先按下面顺序阅读。

---

## 一、先读这些：当前事实文档（Source of Truth）

这些文档已经和当前代码实现对齐，优先级最高。

### 1. 架构与主流程
- `docs/architecture/experiment_flow.md`
- `docs/architecture/api_examples.md`
- `docs/architecture/phase1_milestone.md`

适用场景：
- 想知道系统现在到底怎么跑
- 想区分通用实验路径 vs growth 生产专线
- 想知道当前 Phase 1 的真实阶段定位

### 2. 数据 / 指标 / 契约
- `docs/contracts/data_schema.md`
- `docs/contracts/metrics_contract.md`
- `docs/contracts/deployability_frontend_contract.md`
- `docs/reports/phase1_report_schema.md`

适用场景：
- 想知道字段口径、回测口径、report 结构
- 想知道前端如何消费 deployability
- 想知道哪些列是 dataset service 自动派生出来的

### 3. 数据输入与适配器
- `docs/architecture/tushare_to_file_workflow.md`
- `docs/architecture/data_adapters.md`
- `docs/contracts/reference_data.md`

适用场景：
- 想知道数据如何采集、落盘、进入主链
- 想理解 reference data / adapter 层

---

## 二、当前实现辅助文档（可作为补充事实）

这些文档大体反映当前实现，但更多偏“交付说明 / 组件说明 / 辅助解释”。

### 已实现（交付说明 / 已落地能力）
- `docs/Dynamic Impact v1 Implementation Plan.md`
- `docs/deployability-allocator-pipeline-delivery.md`

适用场景：
- 想了解某个能力是如何落地的
- 想快速理解 dynamic impact / deployability-allocator 打通背景

注意：
- 它们不是主入口事实文档
- 当前优先级低于第一部分的 Source of Truth 文档

---

## 三、部分实现设计文档（不要当成 100% 当前事实）

这些文档里有一部分内容已经落地，但还有一部分仍属于设计、规划或待进一步冻结的 schema / 流程。

### 部分实现
- `docs/research-capacity-constraints-design.md`
- `docs/research-realism-stress-design.md`
- `docs/research-decision-summary-design.md`
- `docs/decision-summary-gating-upgrade-plan.md`
- `docs/relative-liquidity-tail-pruning-plan.md`

适用场景：
- 想理解为什么当前系统会有某些 realism / capacity / decision summary 结构
- 想看这些能力最初是如何设计的

不要直接把这些文档当成：
- 当前唯一真实 schema
- 当前唯一真实执行流程

读它们之前，先读：
- `experiment_flow.md`
- `data_schema.md`
- `metrics_contract.md`
- `api_examples.md`

---

## 四、历史方案文档（历史背景，不是当前执行总纲）

这些文档主要保留历史决策背景、当时的试验方向或研究分支。它们对理解项目演化有帮助，但**不是当前版本的执行基线**。

### 历史方案
- `docs/real-returns-long-term-implementation-plan.md`
- `docs/high-liquidity-filter-refactor-plan.md`
- `docs/filtered-rerun-amount-bottom-20pct-plan.md`
- `docs/value-line-future-review-plan-topn20.md`

适用场景：
- 回看为什么当时会探索某条路线
- 理解某些参数、过滤器、review 计划的历史背景

不建议：
- 拿这些文档直接指导当前实现改动
- 把它们当成最新 working config 依据

---

## 五、推荐阅读顺序

### 如果你要理解“当前系统怎么工作”
按这个顺序：

1. `docs/architecture/experiment_flow.md`
2. `docs/contracts/data_schema.md`
3. `docs/contracts/metrics_contract.md`
4. `docs/architecture/api_examples.md`
5. `docs/architecture/phase1_milestone.md`
6. `docs/contracts/deployability_frontend_contract.md`

### 如果你要理解“治理/前端/allocator/deployability 怎么串起来”
按这个顺序：

1. `docs/contracts/deployability_frontend_contract.md`
2. `docs/deployability-allocator-pipeline-delivery.md`
3. `docs/research-decision-summary-design.md`
4. `docs/research-realism-stress-design.md`
5. `docs/research-capacity-constraints-design.md`

### 如果你要理解“数据怎么进系统”
按这个顺序：

1. `docs/architecture/tushare_to_file_workflow.md`
2. `docs/architecture/data_adapters.md`
3. `docs/contracts/reference_data.md`
4. `docs/contracts/data_schema.md`

---

## 六、阅读红线

### 1. 先看 Source of Truth，再看设计/历史文档
如果你先读计划文档，再读当前事实文档，很容易误判系统现状。

### 2. 当前系统不是单一路径，而是双轨结构
请始终记住：
- 通用实验路径
- growth production path

两者并存。

### 3. 旧文档如果带有“计划 / design / refactor / rerun / future review”字样，优先视为非主事实文档
除非它已明确标注：
- 已实现

---

## 七、当前文档维护约定（建议）

后续继续改文档时，建议遵守这几条：

1. **事实文档优先更新**
   - `experiment_flow.md`
   - `data_schema.md`
   - `metrics_contract.md`
   - `api_examples.md`

2. **设计/计划文档必须带状态头**
   - 已实现
   - 部分实现
   - 历史方案
   - 已过期

3. **不要把历史方案偷偷写成当前事实**

4. **当前 working config、growth 专线、治理前端相关文档变动时，优先同步更新索引页**

---

## 八、一句话总结

如果你只记一件事，请记这个：

> `docs/architecture/experiment_flow.md`、`docs/contracts/data_schema.md`、`docs/contracts/metrics_contract.md`、`docs/architecture/api_examples.md` 是当前项目最重要的事实基线；其它文档都应该先根据状态标记来判断是不是当前真相。