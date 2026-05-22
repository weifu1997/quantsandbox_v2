# API 使用示例（当前实现）

这份文档只描述 `QuantSandbox_v2` **当前已经实现** 的 API 行为，不描述尚未落地的理想接口。

当前 API 入口包括：

- `POST /api/experiments`
- `GET /api/experiments/tickers`
- `GET /api/experiments/stock-names`
- `GET /api/experiments/latest/report`
- `GET /api/experiments/{experiment_id}`
- `GET /api/tasks/{task_id}`
- `GET /api/reports/{report_id}`
- `GET /health`

---

## 1. 健康检查

### 请求

`GET /health`

### 示例响应

```json
{
  "status": "ok"
}
```

说明：

- 当前只做最小健康检查
- 不额外展开数据库、线程池、数据源等更细粒度状态

---

## 2. 提交实验

### 请求

`POST /api/experiments`

### 当前请求字段

必填：

- `start_date`：`YYYYMMDD`
- `end_date`：`YYYYMMDD`

至少二选一：

- `tickers`
- `universe`

可选：

- `factors`
- `horizons`
- `rebalance_frequency`
- `top_n`
- `weighting`
- `benchmark`
- `commission_bps`
- `slippage_bps`
- `report_format`
- `annual_turnover_limit`
- `initial_aum`
- `board_lot_enabled`
- `board_lot_size`
- `execution_assumptions`

### 示例请求（ticker 列表）

```json
{
  "start_date": "20240101",
  "end_date": "20241231",
  "tickers": ["sh600519", "sz000858", "sz300750", "sz000001", "sh600036"],
  "factors": ["momentum_20d", "pe"],
  "horizons": [20],
  "rebalance_frequency": "W",
  "top_n": 10,
  "weighting": "equal",
  "benchmark": "equal_weight_universe",
  "commission_bps": 10.0,
  "slippage_bps": 5.0,
  "report_format": "json",
  "annual_turnover_limit": 3.0,
  "initial_aum": 100000,
  "board_lot_enabled": true,
  "board_lot_size": 100,
  "execution_assumptions": {
    "bar_delay": 1,
    "tick_size": 0.01,
    "base_tick_slippage_ticks": 1.0,
    "high_vol_extra_tick_slippage_ticks": 1.0,
    "high_vol_quantile": 0.8,
    "minimum_roundtrip_ticks": 2.0,
    "commission_bps": 2.0
  }
}
```

### 示例请求（universe）

```json
{
  "start_date": "20240101",
  "end_date": "20241231",
  "universe": "main_board",
  "factors": ["momentum_20d", "pe"],
  "horizons": [20],
  "rebalance_frequency": "W",
  "top_n": 10,
  "weighting": "score",
  "report_format": "markdown"
}
```

### 当前校验规则

- `start_date` / `end_date` 必须是 `YYYYMMDD`
- `end_date >= start_date`
- `horizons` 必须都是正整数
- `rebalance_frequency ∈ {"D", "W", "M"}`
- `weighting ∈ {"equal", "score", "liquidity_tilted_score"}`
- `top_n > 0`
- `tickers` 和 `universe` 至少提供一个

### 示例成功响应

```json
{
  "status": "accepted",
  "data": {
    "experiment": {
      "experiment_id": "exp_xxx",
      "name": null,
      "universe": null,
      "start_date": "20240101",
      "end_date": "20241231",
      "factors": ["momentum_20d", "pe"],
      "horizons": [20],
      "rebalance_frequency": "W",
      "top_n": 10,
      "weighting": "equal",
      "benchmark": "equal_weight_universe",
      "created_at": "2026-05-16T16:00:00+00:00"
    },
    "task": {
      "task_id": "task_xxx",
      "experiment_id": "exp_xxx",
      "status": "running",
      "progress": {
        "current": 0.0,
        "total": 0.0,
        "message": "experiment accepted"
      },
      "stage": "accepted",
      "error": null,
      "result_ref": null,
      "created_at": "2026-05-16T16:00:00+00:00",
      "updated_at": "2026-05-16T16:00:00+00:00"
    }
  }
}
```

说明：

- 当前是 **accepted 后异步执行**
- 不会同步返回完整研究结果
- `task` 初始状态很快会进入 `running`

---

## 3. 查询 growth 预过滤选股池

### 请求

`GET /api/experiments/tickers`

### 语义

返回 growth 当前预过滤 universe ticker 列表。

当前文件来源：

- `reports_dir / filtered_universe_growth_amount_bottom_50pct_latest.json`

### 示例成功响应

```json
{
  "status": "success",
  "data": {
    "tickers": ["sh600000", "sh600036", "sz000858"],
    "count": 3
  }
}
```

### 404 示例

```json
{
  "detail": "ticker file not found"
}
```

说明：

- 若文件内容是 `{ "filtered_universe": { "tickers": [...] } }`，系统会读取其中的 `tickers`
- 若文件内容本身是 list，也会直接返回

---

## 4. 查询股票名称映射

### 请求

`GET /api/experiments/stock-names`

### 语义

返回 reference data 中所有 ticker 到股票名称的映射。

当前文件来源：

- `data/raw/reference/stock_basic_main_board.parquet`

### 示例成功响应

```json
{
  "status": "success",
  "data": {
    "sh600519": "贵州茅台",
    "sz000858": "五粮液"
  }
}
```

### 404 示例

```json
{
  "detail": "reference file not found"
}
```

---

## 5. 查询最新 report ID

### 请求

`GET /api/experiments/latest/report`

### 语义

返回数据库中最新一条 report 的 `report_id`。

### 示例成功响应

```json
{
  "status": "success",
  "data": {
    "report_id": "rep_xxx"
  }
}
```

### 404 示例

```json
{
  "detail": "no reports found"
}
```

说明：

- 当前读取的是 SQLite `reports` 表
- 不是扫描文件系统得出的 latest alias

---

## 6. 查询实验元信息

### 请求

`GET /api/experiments/{experiment_id}`

### 示例成功响应

```json
{
  "status": "success",
  "data": {
    "experiment_id": "exp_xxx",
    "name": null,
    "universe": "main_board",
    "start_date": "20240101",
    "end_date": "20241231",
    "factors": ["momentum_20d", "pe"],
    "horizons": [20],
    "rebalance_frequency": "W",
    "top_n": 10,
    "weighting": "equal",
    "benchmark": "equal_weight_universe",
    "created_at": "2026-05-16T16:00:00+00:00"
  }
}
```

### 404 示例

```json
{
  "detail": "experiment not found"
}
```

说明：

- 当前接口只返回 experiment metadata
- 不直接展开 dataset / factor results / report 内容

---

## 7. 查询任务状态

### 请求

`GET /api/tasks/{task_id}`

### 示例响应（运行中）

```json
{
  "status": "success",
  "data": {
    "task_id": "task_xxx",
    "experiment_id": "exp_xxx",
    "status": "running",
    "progress": {
      "current": 2.0,
      "total": 4.0,
      "message": "running factor validation"
    },
    "stage": "factor_research",
    "error": null,
    "result_ref": null,
    "created_at": "2026-05-16T16:00:00+00:00",
    "updated_at": "2026-05-16T16:00:05+00:00"
  }
}
```

### 示例响应（完成）

```json
{
  "status": "success",
  "data": {
    "task_id": "task_xxx",
    "experiment_id": "exp_xxx",
    "status": "completed",
    "progress": {
      "current": 4.0,
      "total": 4.0,
      "message": "experiment completed"
    },
    "stage": "completed",
    "error": null,
    "result_ref": "rep_xxx",
    "created_at": "2026-05-16T16:00:00+00:00",
    "updated_at": "2026-05-16T16:00:10+00:00"
  }
}
```

### 示例响应（失败）

```json
{
  "status": "success",
  "data": {
    "task_id": "task_xxx",
    "experiment_id": "exp_xxx",
    "status": "failed",
    "progress": {
      "current": 2.0,
      "total": 4.0,
      "message": "some failure message"
    },
    "stage": "failed",
    "error": "some failure message",
    "result_ref": null,
    "created_at": "2026-05-16T16:00:00+00:00",
    "updated_at": "2026-05-16T16:00:08+00:00"
  }
}
```

### 404 示例

```json
{
  "detail": "task not found"
}
```

---

## 8. 查询报告

### 请求

`GET /api/reports/{report_id}`

### 当前返回结构

当前 report 接口**直接返回** `ReportResponseModel` 风格对象，不额外包一层 `{status, data}`。

主要字段包括：

- `report_id`
- `experiment_id`
- `task_id`
- `report_format`
- `report_path`
- `summary`
- `content_type`
- `content`
- `structured`
- `deployability`

### JSON 报告示例响应

```json
{
  "report_id": "rep_xxx",
  "experiment_id": "exp_xxx",
  "task_id": "task_xxx",
  "report_format": "json",
  "report_path": "/root/project/quantsandbox_v2/data/reports/exp_xxx.json",
  "summary": {
    "title": "QuantSandbox v2 Research Report",
    "output_format": "json",
    "experiment_id": "exp_xxx",
    "factor_count": 2,
    "best_factor": "momentum_20d",
    "warning_count": 1
  },
  "content_type": "json",
  "content": "{\n  \"title\": \"QuantSandbox v2 Research Report\", ... }",
  "structured": {
    "title": "QuantSandbox v2 Research Report",
    "output_format": "json",
    "config": {
      "factors": ["momentum_20d", "pe"]
    },
    "dataset_summary": {
      "rows": 1234
    },
    "factor_results": {},
    "backtest_results": {},
    "factor_diagnostics": [],
    "summary": {
      "factor_count": 2,
      "best_factor": "momentum_20d",
      "warning_count": 1
    },
    "warnings": [],
    "deployability": {
      "growth": {
        "deployment_blocked": false,
        "recommended_max_aum": "model_micro"
      }
    }
  },
  "deployability": {
    "growth": {
      "deployment_blocked": false,
      "recommended_max_aum": "model_micro"
    }
  }
}
```

### Markdown 报告示例响应

```json
{
  "report_id": "rep_xxx",
  "experiment_id": "exp_xxx",
  "task_id": "task_xxx",
  "report_format": "markdown",
  "report_path": "/root/project/quantsandbox_v2/data/reports/exp_xxx.md",
  "summary": {
    "title": "QuantSandbox v2 Research Report",
    "output_format": "markdown",
    "experiment_id": "exp_xxx",
    "factor_count": 2,
    "best_factor": "momentum_20d",
    "warning_count": 1
  },
  "content_type": "markdown",
  "content": "# QuantSandbox v2 Research Report\n\n## Config\n...",
  "structured": null,
  "deployability": null
}
```

### `_latest` alias / fallback 行为

当前 `get_report(report_id)` 除了查 DB，还会做文件 fallback：

- 若直接 `repo_get_report(report_id)` 没找到
- 会尝试：
  - `report_id`
  - `report_id.removesuffix("_latest")`
  - 或补上 `_latest`
- 再在 `reports_dir` 中找：
  - `.json`
  - `.md`

因此某些前端页面可以直接请求 alias 报告，例如：

- `research_decision_summary_latest`
- `strategy_line_allocator_latest`
- `growth_personal_100k_2024_2026_boardlot_rebalance_detail_latest`

即使该 alias 不在 DB 中，也可能通过文件 fallback 被解析。

### 404 示例

```json
{
  "detail": "report not found"
}
```

说明：

- `content_type` 当前直接等于 `report_format`
- 只有 JSON report 才会解析出 `structured`
- 只有 JSON report 且存在顶层 `deployability` 时，才会抽取 `deployability`

---

## 9. 当前 API 的真实限制

### 9.1 实验提交是异步 accepted，不是同步完成

- `POST /api/experiments` 只返回 accepted + task/experiment metadata
- 需要通过 `GET /api/tasks/{task_id}` 轮询任务状态
- 完成后再用 `result_ref` 或 report alias 去取 report

### 9.2 当前没有 cancel / retry / list API

当前尚未实现：

- cancel task
- retry task
- list experiments
- list tasks
- list reports

### 9.3 report 内容依赖文件系统存在

- metadata 在 DB 中
- report 内容在文件系统中
- 若文件不存在，则 `content` 可能为空，或 fallback 失败

### 9.4 当前后台执行模型是轻量线程池

- 不是 durable queue
- 不是分布式 worker
- 更适合当前版本主链打通，而不是高并发调度系统

---

## 10. 当前前端最常依赖的 API 组合

治理/前端页面当前通常组合使用：

- `GET /api/reports/{decision_summary_report_id}`
- `GET /api/reports/{allocator_report_id}`
- `GET /api/reports/{ledger_report_id}`
- `GET /api/reports/{stock_ledger_report_id}`
- `GET /api/reports/{stock_summary_report_id}`
- `GET /api/experiments/tickers`
- `GET /api/experiments/stock-names`

回测实验页面当前通常组合使用：

- `POST /api/experiments`
- `GET /api/tasks/{task_id}`
- `GET /api/reports/{report_id}`

这也是为什么 report fallback / latest alias 行为在当前系统里很重要。