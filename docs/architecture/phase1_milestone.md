# Phase 1 里程碑总览（当前已达成状态）

这份文档不是路线图，也不是理想目标列表。

它的目的只有一个：

> **记录当前 Phase 1 已经真实达成了什么、哪些能力已经比较稳定、哪些边界仍然是刻意保留的简化。**

这样后面继续开发、回顾、拆阶段、做演示时，都有一个明确锚点，而不是靠记忆或口头印象。

---

## 1. 当前 Phase 1 的核心定位

当前项目已经不再是“零散脚本 + 若干实验代码”，而是逐渐形成了一条**最小但可信的研究主链**：

1. 接收实验请求
2. 解析 ticker / universe
3. 构建标准化 research dataset
4. 运行单因子研究验证
5. 运行 TopN 回测
6. 生成 JSON / Markdown 报告
7. 持久化 task / experiment / dataset metadata / report metadata

这条链路的目标不是“大而全”，而是：
- 结构清晰
- 口径统一
- 可测试
- 可追踪
- 可以稳定复现

---

## 2. 当前已经比较稳定的能力

### 2.1 数据契约已经开始冻结
当前已经收敛出一套 Phase 1 数据契约：

- 行情字段契约
- 财务字段契约
- research dataset 基础字段契约
- 因子列命名契约：`factor:<name>`
- 未来收益列命名契约：`future_return_<horizon>d`
- backtest dataset 输入校验契约

相关文档：
- `docs/contracts/data_schema.md`

相关代码：
- `app/domain/data_contracts.py`

这意味着：
- adapter / dataset service / factor research / backtest / report 开始共享同一套字段口径
- 后续返工风险显著下降

---

### 2.2 主实验主链已经打通
当前已经真实实现：

- `POST /api/experiments`
- `GET /api/experiments/{experiment_id}`
- `GET /api/tasks/{task_id}`
- `GET /api/reports/{report_id}`
- `GET /health`

相关文档：
- `docs/architecture/experiment_flow.md`
- `docs/architecture/api_examples.md`

当前执行模型：
- API 接受请求
- 创建 experiment record
- 创建 task record
- 后台线程池执行 `run_experiment(...)`
- task 状态可查询
- report 可读取

这说明 Phase 1 已经不只是“能写研究函数”，而是有了一条完整的可调用主入口。

---

### 2.3 service 层职责正在变清晰
当前几个关键 service 已经收过一轮：

#### `experiment_service.py`
已经从单函数堆逻辑，收成更像 orchestration layer：
- resolve tickers
- dataset stage
- factor research stage
- backtest stage
- report stage
- task completion/failure

已拆出的 helper 包括：
- `_resolve_split_date(...)`
- `_build_backtest_results(...)`
- `_build_report_payload(...)`
- `_create_experiment_record(...)`

#### `report_service.py`
已经开始拆清：
- format normalize
- JSON payload 渲染
- summary 组装
- Markdown/JSON 内容渲染
- 文件落盘
- repo record create

#### `task_service.py`
已经有清晰职责：
- create/get task
- running/completed/failed/interrupted 标记
- progress 更新

这意味着服务层已经逐渐从“巨石函数”转向“清晰编排层”。

---

### 2.4 因子研究链已有基础解释层
当前 `app/domain/research/` 已经不只是原始统计，还包括：

- sample split
- IC / RankIC
- group analysis
- validation pipeline
- diagnostics

相关新增能力：
- `app/domain/research/diagnostics.py`
- `diagnose_factor(...)`

当前研究结果已经开始能输出：
- `promising`
- `watchlist`
- `weak`
- `unknown`

而不只是丢一堆数值给人自己猜。

---

### 2.5 回测口径已经开始统一
当前回测指标口径已文档化并与实现对齐，包括：

- `periods_per_year`
- `annual_return`
- `annual_volatility`
- `sharpe_ratio`
- `max_drawdown`
- `win_rate`
- `turnover_from_holdings`
- cost model
- benchmark 口径
- `excess_return_vs_benchmark`

相关文档：
- `docs/contracts/metrics_contract.md`

相关代码：
- `app/domain/backtest/performance_metrics.py`
- `app/domain/backtest/benchmark.py`
- `app/domain/backtest/engine.py`

这意味着：
- 指标定义不再散落
- strategy / benchmark 频率口径已经开始统一

---

### 2.6 report 输出已经成型
当前 report 已有两种格式：

- JSON
- Markdown

并且共享同一语义事实源：
- `render_json_report(...)`

当前 report 已经稳定具备：
- `dataset_summary`
- `factor_results`
- `backtest_results`
- `factor_diagnostics`
- `summary`
- `warnings`

相关文档：
- `docs/reports/phase1_report_schema.md`

这意味着：
- 报告不再只是临时字符串输出
- API / metadata / 内容结构开始有可依赖的稳定形态

---

### 2.7 分层测试结构已经开始成形
当前测试已经不再完全扁平，开始按分层组织：

- `tests/unit/domain/`
- `tests/unit/adapters/`
- `tests/unit/services/`
- `tests/unit/repositories/`
- `tests/integration/`

而且这些层已经不是空目录，已经有真实测试内容：
- domain：contracts / diagnostics / research / backtest / benchmark / metrics
- adapters：file/universe/tushare resilience/reference source
- services：task / experiment / report / dataset / backtest helper
- repositories：task / experiment / report / dataset metadata

这意味着：
- 项目测试已经开始真正反映代码分层，而不是只靠集成测试兜底

---

## 3. 采集链路当前已达成的状态

虽然采集链路不是 Phase 1 主应用的中心，但它已经明显变强，并且足以作为稳定的数据准备入口。

当前 `scripts/collect_tushare_to_file.py` 已经具备：

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

相关文档：
- `docs/architecture/tushare_to_file_workflow.md`

这说明：
- 数据准备链路已经从“能跑”升级到“相对可运维”
- 但它仍应被视为数据输入链，而不是主应用中心

---

## 4. 当前明确存在的边界与简化

### 4.1 后台任务模型仍是轻量线程池
当前：
- `app/tasks/runner.py` 使用 `ThreadPoolExecutor`

这意味着：
- 可以满足 Phase 1
- 但它不是 durable queue
- 也不是分布式 worker 体系

### 4.2 task 持久化了，但不是完整工作流引擎
当前已经具备：
- task 状态持久化
- 服务重启后 running -> interrupted 的清理

但还不具备：
- 真正从中间步骤恢复主实验工作流
- 分布式重试协调
- durable step-level orchestration

### 4.3 report schema 还没有独立 model 冻结
当前 report 结构真实可用，但还主要由：
- `render_json_report(...)`
- `render_markdown_report(...)`
- `report_service.py`

共同定义，而不是由一层正式的 report schema model 冻结。

### 4.4 benchmark 当前只有一个实现
当前只支持：
- `equal_weight_universe`

### 4.5 metrics 仍然是 Phase 1 简化模型
当前明确不做：
- alpha/beta
- information ratio
- sortino/calmar
- 复杂冲击成本
- 容量/撮合级模拟

这些都是刻意保留的边界，不是遗漏。

---

## 5. 当前最重要的结构成果

如果只总结这一轮最有价值的成果，我会归纳成 5 条：

### 1. 数据契约开始成为真正地基
现在已经不是每层自己猜字段，而是开始共享同一 contract。

### 2. service 层开始像真正的编排层
`experiment_service.py` 和 `report_service.py` 已经明显比之前更健康。

### 3. 测试开始真正反映分层结构
不是只靠 integration 测主链了。

### 4. 文档开始回到真实实现
architecture / API / report / metrics / contracts 已经形成连续对齐。

### 5. 数据采集链路足够强，但没有完全反客为主
它变强了，但主线仍然是 research/backtest/report。

---

## 6. 当前 Phase 1 可以怎样被描述

如果现在要对外或对团队内部用一句话描述当前阶段，我建议这样说：

> **QuantSandbox v2 Phase 1 已经从“代码雏形”进入“最小可信研究系统”阶段：主实验主链已打通，数据/指标/报告契约开始冻结，分层职责与分层测试开始成立。**

这句话我觉得和当前真实状态是相符的。

---

## 7. 这个里程碑的实际价值

这个阶段性里程碑的价值不只是“功能多了”，而是：

- 后面继续做功能时，不再总要返工地基
- 口径讨论开始有文档锚点
- 分层测试让重构风险下降
- 结构越来越适合长期维护
- 主链已经足够拿来作为后续 Phase 2 的稳定起点

也就是说，现在项目最重要的变化不是“更大”，而是**更稳、更清楚、更可复用**。

---

## 8. 当前仍然适合坚持的原则

在后续继续推进前，当前最适合继续坚持的 3 条原则依然是：

1. **先定契约，再写业务**
2. **先让 service 只编排，再谈更多入口/外围功能**
3. **先把一条主链做可信，再考虑扩更多能力**

这 3 条如果继续守住，Phase 1 后面的演进会顺很多。
