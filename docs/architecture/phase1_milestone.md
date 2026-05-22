# Phase 1 里程碑总览（当前实现状态）

这份文档记录 `QuantSandbox_v2` **当前真实已经达到的里程碑状态**。它不是路线图，也不是理想目标清单，而是给开发、审计、文档维护和阶段拆分提供一个统一锚点。

---

## 1. 当前 Phase 1 的真实定位

当前项目已经不再是“若干脚本 + 零散研究函数”的雏形，而是一个具备以下能力的 **最小可信研究系统**：

1. API 接收实验请求
2. task / experiment / report / dataset metadata 持久化
3. 标准化 research dataset 构建
4. 因子研究验证链
5. TopN 回测引擎
6. JSON / Markdown 报告输出
7. growth production path
8. governance / deployability / allocator / ledger 前端消费链

因此当前 Phase 1 的定位已经比最初“最小 demo”更强，比较准确的描述应是：

> **通用研究主链已打通，同时已经内嵌一条 revenue_growth growth working config 的生产化回测专线，并开始形成治理与前端消费层。**

---

## 2. 当前已经稳定成立的能力

## 2.1 数据契约已经冻结到可用级别

当前已经有一套真实可用的数据契约，覆盖：

- 行情字段契约
- 财务字段契约
- research base dataset 字段
- 因子列命名契约：`factor:<name>`
- future return 列命名契约：`future_return_<horizon>d`
- backtest dataset 输入校验
- delayed execution 相关派生列
- listing days / sample flags

相关代码：

- `app/domain/data_contracts.py`
- `app/services/dataset_service.py`

意义：

- adapter / dataset service / factor research / backtest / report 已不再各自发明字段口径
- 后续重构与文档维护已有地基

---

## 2.2 主实验主链已经打通

当前已经真实实现：

- `POST /api/experiments`
- `GET /api/experiments/tickers`
- `GET /api/experiments/stock-names`
- `GET /api/experiments/latest/report`
- `GET /api/experiments/{experiment_id}`
- `GET /api/tasks/{task_id}`
- `GET /api/reports/{report_id}`
- `GET /health`

当前主链具备：

- experiment 提交
- task 状态追踪
- report 查询
- alias/fallback report 解析

意义：

- 项目已经从“能写研究函数”演进到“有真实调用入口的研究系统”

---

## 2.3 当前系统已经形成双轨结构

这是当前最重要的里程碑之一。

### 通用实验路径

适用：

- 非 `revenue_growth` 因子实验

链路：

- `build_research_dataset(...)`
- `run_factor_research(...)`
- `run_strategy_backtest(...)`
- `build_experiment_report(...)`

### growth production path

适用：

- `config.factors == ["revenue_growth"]`

链路：

- `_run_growth_backtest(...)`
- growth config + registry + filtered universe
- turnover / board-lot / execution attrs 注入
- 生产 working config 回测

意义：

- 当前系统不再是纯通用研究框架
- 已经有一条与治理、部署、前端联动的正式生产专线

---

## 2.4 service 层职责已经明显清晰化

### `experiment_service.py`

当前已经不只是巨石函数，而是实际承担：

- experiment/task 创建
- 双轨路径分流
- task progress 编排
- factor research / backtest / report 串联
- 成功 / 失败收口

### `report_service.py`

当前已经拆出：

- format normalize
- JSON payload render
- summary 组装
- Markdown/JSON 内容 render
- 文件落盘
- repo record create
- latest alias / fallback 文件解析

### `task_service.py`

已经具备：

- create/get task
- running/completed/failed/interrupted 标记
- progress 更新

意义：

- service 层已经接近真正的 orchestration layer
- 不再只是临时拼接代码

---

## 2.5 因子研究链已有解释层

当前 `app/domain/research/` 已不只是算数值，还包括：

- sample split
- IC / RankIC
- group analysis
- validation pipeline
- diagnostics

相关新增：

- `app/domain/research/diagnostics.py`
- `diagnose_factor(...)`

意义：

- 因子输出不再只是“给你几个数”
- 已经能给出更接近结论层的解释信号

---

## 2.6 回测引擎已经超出最初 Phase 1 简化版

当前回测引擎具备：

- horizon / rebalance frequency 配对限制
- turnover limit
- 首期 turnover limit
- board-lot 约束
- delayed execution return
- volatility-aware execution slippage
- dynamic impact model
- per-name gross contribution
- per-name accounting
- cash accounting
- execution diagnostics
- benchmark 对照

相关代码：

- `app/domain/backtest/engine.py`
- `app/domain/backtest/dynamic_impact_model.py`
- `app/domain/backtest/performance_metrics.py`

意义：

- 当前项目已经不是“只有简单收益摘要”的回测器
- 已具备面向治理、ledger、执行现实性的上游结构

---

## 2.7 report 输出已经成型

当前 report 支持：

- JSON
- Markdown

并共享同一语义事实源：

- `render_json_report(...)`

当前 report 已稳定包含：

- `dataset_summary`
- `factor_results`
- `backtest_results`
- `factor_diagnostics`
- `summary`
- `warnings`
- 视具体 report 而定的 `deployability` 等结构化字段

意义：

- report 已经不是临时字符串
- 可以作为 API / 前端 / 治理页面的稳定事实源

---

## 2.8 前端治理/回测页面已经成形

当前前端已经不只是 demo 页面，而是形成了两大区域：

### 治理面板

- decision summary report
- allocator report
- ledger report
- deployability summary
- allocator blocked / value overlay blocked 状态

### 回测实验面板

- production config 语义展示
- 日期区间提交
- 任务进度轮询
- 回测结果
- 实际运行配置展示
- 持仓 / 收益 / 明细 / 展开视图

意义：

- 项目已经进入“有真实前端消费层”的阶段
- 后端输出结构不再只面向脚本或终端

---

## 2.9 分层测试已经成立

当前测试已经形成如下结构：

- `tests/unit/domain/`
- `tests/unit/adapters/`
- `tests/unit/services/`
- `tests/unit/repositories/`
- `tests/integration/`
- `tests/scripts/`

当前全量测试基线：

- `192 passed`

意义：

- 分层职责已有测试映射
- 不是只有集成测试兜底
- 当前系统已具备基础回归保护能力

---

## 3. 当前采集链路已达到的状态

虽然采集链路不是主应用中心，但它已经明显超出“临时脚本”水平。

当前 `scripts/collect_tushare_to_file.py` 已具备：

- chunk 采集
- 边拉边落盘
- ticker 级 checkpoint / 恢复
- failed ticker 队列
- precheck / validation
- per-ticker `max_date + 1` 精细增量
- 单实例 lock
- JSON 原子写
- SQLite run-state
- 结构化 run report
- retry 阶段低速策略
- stale lock / stale run 自愈
- 统一状态模型

意义：

- 数据准备链路已经相对可运维
- 但它仍然应被视为数据输入链，不是主应用本身的中心

---

## 4. 当前仍刻意保留的边界

## 4.1 后台任务仍是轻量线程池模型

当前：

- `app/tasks/runner.py` 使用 `ThreadPoolExecutor`

说明：

- 可满足当前版本
- 不是 durable queue
- 不是分布式 worker

## 4.2 task 状态可追踪，但不是完整工作流引擎

当前已经具备：

- task 状态持久化
- 服务重启后 running -> interrupted 清理

但还不具备：

- 中间步骤恢复执行
- durable retry workflow
- 分布式协调

## 4.3 benchmark 当前只有一个实现

当前只支持：

- `equal_weight_universe`

## 4.4 当前不是撮合级微观交易系统

当前没有：

- 涨跌停成交约束
- order book / queue 模拟
- partial fill 真正落地
- 连续型 market impact 曲线

这些是刻意保留的边界，不是遗漏。

---

## 5. 当前阶段应该如何命名

如果继续沿用“Phase 1”这个名字，那么更准确的理解不是：

- “最小 demo 阶段”

而是：

- **最小可信研究系统阶段**

它已经具备：

- 主实验主链
- growth 生产专线
- 指标/数据契约
- 报告输出
- 治理/前端消费
- 分层测试

因此后续如果要继续拆阶段，更合理的方向可能是：

- Phase 1：最小可信研究系统（当前）
- Phase 1.5 / 2：耐久任务编排、更多 benchmark、更多执行现实性、正式 schema 冻结、更多治理自动化

---

## 6. 当前一句话总结

如果现在要对外或对内部总结当前状态，建议用这句话：

> **QuantSandbox_v2 当前已经从代码雏形进入“最小可信研究系统”阶段：通用实验主链已打通，growth working config 生产专线已存在，数据/指标/报告契约开始冻结，治理前端与分层测试已经成立。**

这句话与当前真实实现是相符的。