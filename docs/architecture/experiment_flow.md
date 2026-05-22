# 实验流程（Phase 1）

这份文档描述 **当前已实现的 Phase 1 主链**，重点是把代码中的真实职责、真实入口、真实持久化边界说明清楚，避免文档停留在旧结构想象里。

---

## 1. 当前目标

Phase 1 的目标不是做一个“大而全的平台”，而是先打通一条**最小但可信的研究主链**：

1. 接收实验请求
2. 解析 ticker universe
3. 构建标准化 research dataset
4. 运行单因子研究验证
5. 运行 TopN 组合回测
6. 生成 JSON / Markdown 报告
7. 持久化 task / experiment / dataset metadata / report metadata

当前重点是：
- 口径统一
- 结构清晰
- 可测试
- 可追踪

而不是分布式调度、复杂工作流引擎、或大规模任务平台。

---

## 2. 对外入口

### API 入口

当前主入口 API 为：

- `POST /api/experiments`
- `GET /api/experiments/{experiment_id}`
- `GET /api/tasks/{task_id}`
- `GET /api/reports/{report_id}`

对应代码：
- `app/api/experiments.py`
- `app/api/tasks.py`
- `app/api/reports.py`

### App 启动入口

FastAPI app 入口：
- `app/main.py`

当前启动时会做的最小 housekeeping：
- `init_db()`
- `mark_interrupted_running_tasks()`

这意味着：
- 数据库表会在启动时确保存在
- 上次服务重启前仍处于 running 的 task 会被标记为 interrupted

---

## 3. 主链总览

当前主链可以概括为：

```text
POST /api/experiments
  -> submit_experiment(config)
    -> create experiment record
    -> create task record
    -> mark task accepted/running
    -> submit background runner
      -> run_experiment(task_id, experiment_id, config)
        -> build research dataset
        -> run factor research
        -> run TopN backtests
        -> build report
        -> persist report metadata
        -> mark task completed / failed
```

这个流程的“同步编排核心”在：
- `app/services/experiment_service.py`

这个流程的“异步启动壳”在：
- `app/tasks/runner.py`

---

## 4. 分层职责（当前真实现状）

### 4.1 API 层：接收请求与返回结果

#### `app/api/experiments.py`
职责：
- 校验请求参数
- 将 HTTP payload 转成 `ExperimentConfig`
- 调用 `submit_experiment(...)`
- 返回 accepted 结果

当前已做校验包括：
- 日期格式 `YYYYMMDD`
- `horizons > 0`
- `rebalance_frequency in {D, W, M}`
- `weighting in {equal, score}`
- `top_n > 0`
- `end_date >= start_date`
- `tickers` / `universe` 至少给一个

#### `app/api/tasks.py`
职责：
- 查询 task 状态

#### `app/api/reports.py`
职责：
- 查询 report metadata
- 读取报告文件内容
- 若为 JSON report，则返回结构化 `structured` 结果

---

### 4.2 Service 层：编排主链，不承载底层算法细节

#### `app/services/experiment_service.py`
这是当前 Phase 1 的主编排器。

当前职责：
- resolve tickers
- 推进 task progress
- 调用 dataset service
- 调用 factor research service
- 调用 backtest service
- 调用 report service
- 成功时 mark task completed
- 失败时 mark task failed

当前已经抽出的 helper 包括：
- `_resolve_tickers_from_config(...)`
- `_config_to_dict(...)`
- `_resolve_split_date(...)`
- `_build_backtest_results(...)`
- `_build_report_payload(...)`
- `_create_experiment_record(...)`

这说明 `experiment_service.py` 当前是**编排器**，而不是算法巨石。

#### `app/services/dataset_service.py`
职责：
- 拉市场数据
- 拉财务数据
- merge 成 research dataset
- 校验数据契约
- 计算因子列
- 计算 future return 列
- 生成样本有效性标记
- 生成 dataset summary
- 持久化 dataset metadata

#### `app/services/factor_research_service.py`
职责：
- 对给定 factor 列表运行统一 validation pipeline

#### `app/services/backtest_service.py`
职责：
- 将 factor name 映射到标准 `factor:<name>` 列
- 调用回测引擎

#### `app/services/report_service.py`
职责：
- 生成 JSON 语义 payload
- 生成 Markdown 或 JSON 文件内容
- 生成 summary
- 落盘报告文件
- 持久化 report metadata

当前已经拆出的 helper 包括：
- `_normalize_report_format(...)`
- `_render_report_payload(...)`
- `_build_report_summary(...)`
- `_render_report_content(...)`
- `_persist_report_file(...)`
- `_create_report_record(...)`

#### `app/services/task_service.py`
职责：
- create / get task
- mark running / completed / failed
- update progress
- 启动时把残留 running task 标为 interrupted

---

### 4.3 Domain 层：研究与回测核心逻辑

#### `app/domain/data_contracts.py`
这是当前 Phase 1 的数据契约地基。

负责：
- 标准行情字段规范
- 标准财务字段规范
- research dataset 校验
- backtest dataset 校验
- `factor:<name>` / `future_return_<horizon>d` 命名 helper
- ticker / trade date 标准化

#### `app/domain/factors/`
负责：
- 因子定义与注册
- Phase 1 经典因子计算

当前至少包括：
- momentum
- reversal
- valuation
- quality

#### `app/domain/research/`
负责：
- sample split
- IC / RankIC 分析
- group analysis
- validation pipeline
- diagnostics

当前 `validation.py` 已经接入：
- `diagnose_factor(...)`

所以研究结果不再只是原始统计，而开始具备解释层。

#### `app/domain/backtest/`
负责：
- rebalance calendar
- portfolio construction
- benchmark
- cost model
- performance metrics
- run_topn_backtest(...)`

当前回测引擎入口：
- `app/domain/backtest/engine.py`

---

### 4.4 Repository 层：只负责持久化与读取

当前 repository 包括：
- `task_repository.py`
- `experiment_repository.py`
- `report_repository.py`
- `dataset_metadata_repository.py`

职责原则：
- 只做数据库读写与 row/dict 转换
- 不承载业务编排
- 不承载研究/回测逻辑

当前第一阶段数据库重点只存：
- task 元信息
- experiment 元信息
- report 元信息
- dataset metadata

不在 SQLite 中存大宽表行情数据。

---

### 4.5 Adapter 层：统一外部/文件数据输入

当前 adapter 包括：
- `market_data_adapter.py`
- `fundamental_data_adapter.py`
- `universe_adapter.py`

职责：
- 获取市场数据
- 获取财务数据
- 解析 universe
- 输出符合 `data_contracts` 的标准化数据

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
5. 返回：
   - experiment metadata
   - task metadata

### 5.2 后台执行路径

`run_experiment(task_id, experiment_id, config)` 当前做：

#### Step 1: Dataset
- update task progress -> `dataset`
- resolve tickers
- build research dataset
- dataset metadata 持久化

#### Step 2: Factor Research
- update task progress -> `factor_research`
- 根据 dataset 自动推导一个中位 split_date
- 运行 factor validation pipeline

#### Step 3: Backtest
- update task progress -> `backtest`
- 对每个 factor 跑 TopN 回测

#### Step 4: Report
- update task progress -> `report`
- 构建 JSON/Markdown 报告
- 落盘报告文件
- 持久化 report metadata

#### Step 5: Completion
- mark task completed
- 若任一阶段抛异常，则 mark task failed 后继续抛出

---

## 6. 当前持久化边界

### SQLite 持久化
当前数据库中持久化的是：
- task
- experiment
- report
- dataset metadata

### 文件持久化
当前文件系统中持久化的是：
- dataset parquet
- report json / markdown
- 原始/标准化参考数据
- 采集脚本输出的 manifest / checkpoint / validation / run-report 等

注意：
- experiment 主链与采集脚本链路是有关联的，但仍是两条不同关注点的链
- Phase 1 的核心主线仍然是 research/backtest/report，而不是把采集脚本做成独立平台

---

## 7. 测试覆盖现状

当前测试已经开始按分层结构收敛：

- `tests/unit/domain/`
- `tests/unit/adapters/`
- `tests/unit/services/`
- `tests/unit/repositories/`
- `tests/integration/`

这意味着：
- domain 层已有契约/研究/回测相关单测
- adapter 层已有 file/universe/tushare resilience 测试
- service 层已有 report/task/experiment/backtest/dataset 相关测试
- repository 层已有 task/experiment/report/dataset metadata 测试
- integration 层继续覆盖主链端到端行为

当前主线已经不只是“能跑”，而是开始具备：
- 分层职责
- 分层测试
- 文档与代码对齐

---

## 8. 当前限制（真实现状）

### 8.1 后台执行模型仍然是轻量线程池
当前 `app/tasks/runner.py` 使用：
- 单进程 `ThreadPoolExecutor`

这意味着：
- 适合 Phase 1
- 不等同于 durable queue
- 不具备分布式任务调度能力

### 8.2 Task 持久化了，但后台执行不是可恢复工作流引擎
当前具备：
- task 状态持久化
- 服务重启后 running -> interrupted 的清理

但还不具备：
- 任务真正从中间步骤恢复执行
- durable retry workflow
- 分布式执行协调

### 8.3 采集脚本链路比主实验主链更重
这是已知现状。

当前采集链路已经具备：
- checkpoint
- run-state
- structured run report
- retry 策略
- stale lock 自愈

但它仍然应被视为：
- 数据准备链路

而不是第一阶段主应用本身的中心。

---

## 9. 当前最小可信里程碑（已接近的真实目标）

当前 Phase 1 最重要的真实目标是：

> 能通过一个 API 或同步主编排函数，提交一组 ticker / universe、时间区间和 1~N 个因子，然后稳定产出：

- dataset summary
- factor validation result
- TopN backtest result
- JSON / Markdown report
- 持久化的 task / experiment / report / dataset metadata

只要这条链持续稳定、口径统一、测试覆盖逐步补齐，Phase 1 就是健康推进的。
