# 实验流程（当前实现）

这份文档描述 **QuantSandbox_v2 当前已经实现** 的实验主链、生产专线与持久化边界。目标不是描述理想中的未来平台，而是把代码里的真实结构、真实分层、真实执行路径写清楚，避免后续文档、前端、脚本和服务层继续各说各话。

---

## 1. 当前系统目标

当前系统已经不只是一个“最小因子研究 demo”，而是一个同时包含以下两类能力的研究/回测系统：

1. **通用研究实验链路**
   - 接收实验请求
   - 构建 research dataset
   - 运行因子研究验证
   - 运行 TopN 回测
   - 生成 JSON / Markdown 报告
   - 持久化 task / experiment / dataset metadata / report metadata

2. **Growth 生产专线**
   - 固定读取 growth working config
   - 固定读取 growth registry candidate
   - 固定读取 filtered universe artifact
   - 使用更接近真实执行的回测口径（turnover、board-lot、execution、impact）
   - 为治理、deployability、ledger 面板提供上游结果

当前重点不再只是“把一条最小主链打通”，而是：

- 口径统一
- 路径可追踪
- 生产 growth line 与通用实验路径边界清晰
- 输出可被前端与治理层直接消费
- 测试可覆盖

---

## 2. 对外入口

### 2.1 API 入口

当前 API 入口包括：

- `POST /api/experiments`
- `GET /api/experiments/tickers`
- `GET /api/experiments/stock-names`
- `GET /api/experiments/latest/report`
- `GET /api/experiments/{experiment_id}`
- `GET /api/tasks/{task_id}`
- `GET /api/reports/{report_id}`
- `GET /health`

对应代码：

- `app/api/experiments.py`
- `app/api/tasks.py`
- `app/api/reports.py`
- `app/main.py`

### 2.2 App 启动入口

FastAPI app 入口：

- `app/main.py`

启动时当前会做：

- `init_db()`
- `mark_interrupted_running_tasks()`

这意味着：

- SQLite 表结构会在启动时确保存在
- 之前服务退出时仍处于 `running` 的 task 会被标成 `interrupted`
- 当前没有真正的 durable workflow recovery；只有状态清理，不做中间步骤恢复执行

---

## 3. 当前最重要的结构事实：双轨实验主链

当前系统不是单一的“通用 experiment pipeline”，而是 **双轨结构**：

### 3.1 通用实验路径（generic experiment path）

适用条件：

- `config.factors != ["revenue_growth"]`

主链：

```text
POST /api/experiments
  -> submit_experiment(config)
    -> create experiment
    -> create task
    -> submit background runner
      -> run_experiment(task_id, experiment_id, config)
        -> build_research_dataset(...)
        -> _build_backtest_results(...)
          -> run_strategy_backtest(...)
            -> run_topn_backtest(...)
        -> run_factor_research(...)
        -> build_experiment_report(...)
        -> mark_task_completed / failed
```

这是“任意因子研究请求”的标准主链。

### 3.2 Growth 生产专线（growth production path）

适用条件：

- `config.factors == ["revenue_growth"]`

主链：

```text
POST /api/experiments
  -> submit_experiment(config)
    -> create experiment
    -> create task
    -> submit background runner
      -> run_experiment(task_id, experiment_id, config)
        -> _run_growth_backtest(start_date, end_date)
          -> load growth config + registry
          -> load filtered universe
          -> build dataset
          -> apply filter
          -> inject turnover / board-lot / execution attrs
          -> run_topn_backtest(...)
        -> _build_growth_dataset_summary(...)
        -> run_factor_research(...)
        -> build_experiment_report(...)
        -> mark_task_completed / failed
```

这条路径不是普通的“传一个 factor 名称就跑”，而是 **治理批准后的 growth 当前 working config 专线**。

### 3.3 为什么必须单独说明

因为当前系统里：

- 通用实验路径 = 研究框架
- growth production path = 正式 working config 的执行通道

如果文档不区分这两条路径，后续维护者会误以为：

- 所有实验都走统一 dataset/backtest path
- growth 前端展示只是某个普通实验结果

这都是不对的。

---

## 4. 分层职责（当前真实现状）

## 4.1 API 层：接收请求、提供结构化结果

### `app/api/experiments.py`

职责：

- 校验实验请求
- 将 HTTP payload 转为 `ExperimentConfig`
- 提交后台实验
- 暴露 growth ticker 列表
- 暴露 ticker-name mapping
- 提供最新 report ID 查询

当前已做校验包括：

- 日期格式 `YYYYMMDD`
- `horizons > 0`
- `rebalance_frequency in {D, W, M}`
- `weighting in {equal, score, liquidity_tilted_score}`
- `top_n > 0`
- `end_date >= start_date`
- `tickers` / `universe` 至少提供一个

当前还支持这些实验参数：

- `annual_turnover_limit`
- `initial_aum`
- `board_lot_enabled`
- `board_lot_size`
- `execution_assumptions`

### `app/api/tasks.py`

职责：

- 查询 task 状态

### `app/api/reports.py`

职责：

- 查询 report metadata
- 读取 report 文件内容
- JSON report 自动解析为 `structured`
- 若存在顶层 `deployability`，抽取为单独字段供前端直接消费

---

## 4.2 Service 层：主编排与稳定输出

### `app/services/experiment_service.py`

这是当前实验主链的核心编排器。

职责：

- 提交 experiment/task
- 分支决定走通用实验路径还是 growth production path
- 推进 task progress
- 调用 dataset service / factor research / backtest / report
- 处理失败收口

当前关键函数：

- `_config_to_dict(...)`
- `_resolve_split_date(...)`
- `_load_growth_config(...)`
- `_run_growth_backtest(...)`
- `run_strategy_backtest(...)`
- `_build_backtest_results(...)`
- `_build_report_payload(...)`
- `_create_experiment_record(...)`
- `_build_growth_dataset_summary(...)`
- `run_experiment(...)`
- `submit_experiment(...)`

需要特别理解的事实：

- `run_experiment(...)` 当前本身就承载“growth 专线 / generic path”的分流逻辑
- `run_strategy_backtest(...)` 已恢复为通用服务层接口，保证测试与非 growth 实验路径稳定
- growth path 不通过 `build_research_dataset(...)`，而是直接构造专线 dataset 并向引擎注入 attrs

### `app/services/dataset_service.py`

职责：

- 拉市场数据
- 拉财务数据
- merge 成 research dataset
- 补充 reference data（如 `listed_days`）
- 校验 research dataset 契约
- 计算 factor 列
- 计算 future return / delayed future return / execution 相关列
- 生成样本有效性标记
- 生成 dataset summary
- 持久化 dataset metadata

当前系统行为有两个关键点：

1. **fundamental provider 缺列兼容**
   - 若 fundamentals 缺少 `roa` / `gross_margin` / `revenue_growth` / `profit_growth` 等列
   - 会先补 `pd.NA`
   - 再进入统一 schema 校验

2. **dataset service 不只是 research 数据拼装器**
   - 还生成 execution-aware 的衍生字段
   - 包括 `next_open_price`、`rolling_vol_20d`、`rolling_vol_20d_hist_q80`、`delayed_future_return_*`

### `app/services/factor_research_service.py`

职责：

- 对给定 factor 列表运行统一 validation pipeline
- 输出可直接进入 report 的因子研究结果

### `app/services/report_service.py`

职责：

- 生成 JSON 语义 payload
- 生成 Markdown 或 JSON 内容
- 构建 summary
- 落盘 report 文件
- 持久化 report metadata
- 支持 `_latest` alias / fallback 文件解析

当前关键 helper：

- `_normalize_report_format(...)`
- `_render_report_payload(...)`
- `_build_report_summary(...)`
- `_render_report_content(...)`
- `_persist_report_file(...)`
- `_create_report_record(...)`
- `_latest_report_candidates(...)`
- `_find_report_file_by_id(...)`
- `resolve_report_content(...)`

### `app/services/task_service.py`

职责：

- create / get task
- mark running / completed / failed
- update progress
- 启动时将遗留 running task 标为 interrupted

---

## 4.3 Domain 层：研究与回测真实核心

### `app/domain/data_contracts.py`

职责：

- 标准行情字段规范
- 标准财务字段规范
- research dataset 校验
- backtest dataset 校验
- `factor:<name>` / `future_return_<horizon>d` 命名 helper
- ticker / trade date 标准化

### `app/domain/factors/`

职责：

- 因子定义与注册
- 估值 / 质量 / 动量 / 反转等因子计算

当前需要特别注意：

- `momentum.py` 和 `reversal.py` 已改为按 `ticker` 分组后再做 `shift()`
- 之前的跨 ticker 泄漏问题已修复

### `app/domain/research/`

职责：

- sample split
- IC / RankIC 分析
- group analysis
- validation pipeline
- diagnostics

研究结果现在不仅有原始统计，还开始有解释层输出。

### `app/domain/backtest/`

职责：

- rebalance calendar
- portfolio construction
- benchmark
- cost model
- dynamic impact model
- performance metrics
- run_topn_backtest(...)

当前回测引擎已经不再是“简单 TopN + 简单成本”的最小实现，而是包含：

- horizon / frequency 配对限制
- turnover limit
- 首期 turnover 限制
- board-lot 约束
- delayed execution return
- extra execution slippage
- dynamic impact cost
- per-name contribution/accounting
- cash accounting
- execution diagnostics
- benchmark comparison

---

## 4.4 Repository 层：元信息持久化

当前 repository 包括：

- `task_repository.py`
- `experiment_repository.py`
- `report_repository.py`
- `dataset_metadata_repository.py`

职责原则：

- 只做数据库读写
- 只做 row/dict 转换
- 不承载研究逻辑
- 不承载回测逻辑

当前 SQLite 主要存：

- task 元信息
- experiment 元信息
- report 元信息
- dataset metadata

不在 SQLite 中存储大宽表行情数据。

---

## 4.5 Adapter 层：统一外部数据入口

当前 adapter 包括：

- `market_data_adapter.py`
- `fundamental_data_adapter.py`
- `universe_adapter.py`

职责：

- 获取市场数据
- 获取财务数据
- 解析 universe
- 输出符合 data contract 的标准化 DataFrame

当前支持：

- memory adapter（测试/开发）
- file adapter（标准化文件输入）
- Tushare adapter（在线数据源）

---

## 5. 当前真实执行时序

### 5.1 异步提交路径

`submit_experiment(config)` 当前做：

1. 创建 experiment record
2. 创建 task record
3. 标记 task 为 `accepted` / `running`
4. 通过 `submit_background(...)` 提交后台执行
5. 立即返回：
   - experiment metadata
   - task metadata

这意味着：

- `POST /api/experiments` 是 accepted-then-async 模式
- 不是同步执行并直接返回研究结果

### 5.2 后台执行路径

`run_experiment(task_id, experiment_id, config)` 当前做：

#### Step 1: Dataset

- `update_task_progress(..., stage="dataset")`
- 若是 growth 专线：
  - `_run_growth_backtest(...)`
  - 同时得到 growth filtered dataset
- 若是通用实验路径：
  - `build_research_dataset(...)`
  - 生成 dataset summary 和 dataset metadata
  - `_build_backtest_results(...)`

#### Step 2: Factor Research

- `update_task_progress(..., stage="factor_research")`
- 自动根据 dataset 计算中位 split date
- `run_factor_research(...)`

#### Step 3: Backtest

- `update_task_progress(..., stage="backtest")`
- growth path 的 backtest 实际已在 `_run_growth_backtest(...)` 内完成
- generic path 在 `_build_backtest_results(...)` 中完成

#### Step 4: Report

- `update_task_progress(..., stage="report")`
- `build_experiment_report(...)`
- 落盘 report 文件
- 持久化 report metadata

#### Step 5: Completion

- `mark_task_completed(...)`
- 若任一阶段抛异常：
  - `mark_task_failed(...)`
  - 再继续抛出异常

---

## 6. 当前持久化边界

### 6.1 SQLite 持久化

当前数据库中持久化的是：

- task
- experiment
- report
- dataset metadata

### 6.2 文件系统持久化

当前文件系统中持久化的是：

- dataset parquet
- report json / markdown
- raw/reference 数据
- growth / deployability / allocator / ledger 上游 artifact
- 采集脚本的 manifest / checkpoint / validation / run-report 等

### 6.3 一个重要事实

当前“实验主链”和“研究治理/生产脚本链”是相关联但不等价的两条链：

- experiment 主链 = 通用研究/回测 API 编排
- growth/deployability/allocator/ledger = 治理批准后的生产化研究链

文档后续更新必须持续保留这条边界。

---

## 7. 测试覆盖现状

当前测试已经按分层结构收敛：

- `tests/unit/domain/`
- `tests/unit/adapters/`
- `tests/unit/services/`
- `tests/unit/repositories/`
- `tests/integration/`
- `tests/scripts/`

当前全量测试基线：

- `192 passed`

这意味着当前项目不是“能跑但不可验证”的状态，而是：

- 分层职责存在
- 分层测试存在
- growth path 与 generic path 至少具备基础回归保护

---

## 8. 当前限制（真实现状）

### 8.1 后台执行模型仍是轻量线程池

当前 `app/tasks/runner.py` 使用：

- 单进程 `ThreadPoolExecutor`

这意味着：

- 适合当前版本
- 不等同于 durable queue
- 不具备分布式任务调度能力

### 8.2 task 状态可追踪，但不是可恢复工作流引擎

当前具备：

- task 状态持久化
- 服务重启后 `running -> interrupted` 清理

但不具备：

- 从中间步骤恢复执行
- durable retry workflow
- 分布式执行协调

### 8.3 growth 专线路径对 artifact 仍有依赖

例如：

- growth config
- registry
- filtered universe artifact

这些当前仍通过文件 artifact 驱动，不是完全 API-first 的统一中心配置系统。

---

## 9. 当前系统的最小可信描述

当前系统可以被最准确地描述为：

> 一个带有通用研究实验主链的量化研究平台雏形，同时内嵌一条 revenue_growth growth working config 的生产化回测专线，并已经接入 deployability / allocator / ledger 前端治理面板所需的上游数据结构。

只要后续文档继续围绕这个真实结构更新，而不是回退到“抽象 Phase 1 理想平台”的表述，项目文档就会重新和代码对齐。