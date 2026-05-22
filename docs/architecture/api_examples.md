# API 使用示例（Phase 1）

这份文档只描述**当前已经实现**的 API 行为，不描述尚未落地的理想接口。

当前 API 入口包括：
- `POST /api/experiments`
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
- 不额外展开数据库、后台线程池、数据源等更细粒度状态

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
  "report_format": "json"
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
  "report_format": "markdown"
}
```

### 当前校验规则

- `start_date` / `end_date` 必须是 `YYYYMMDD`
- `end_date >= start_date`
- `horizons` 必须都是正整数
- `rebalance_frequency ∈ {"D", "W", "M"}`
- `weighting ∈ {"equal", "score"}`
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
- 当前是**accepted 后异步执行**，不是同步返回完整研究结果
- `task` 初始状态会很快进入 `running`

### 常见错误示例

#### 日期格式错误

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "start_date"],
      "msg": "Value error, date must be in YYYYMMDD format",
      "input": "2024-01-01"
    }
  ]
}
```

#### 未提供 tickers / universe

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body"],
      "msg": "Value error, either tickers or universe is required"
    }
  ]
}
```

---

## 3. 查询实验元信息

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

## 4. 查询任务状态

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

## 5. 查询报告

### 请求

`GET /api/reports/{report_id}`

### 当前返回结构

当前 report 接口直接返回 `ReportResponseModel` 风格对象，不再额外包一层 `{status, data}`。

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
    "warnings": []
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
  "structured": null
}
```

### 404 示例

```json
{
  "detail": "report not found"
}
```

说明：
- `content_type` 当前直接等于 `report_format`
- 只有 JSON report 才会附带 `structured`
- Markdown report 返回 `content` 文本，但 `structured = null`

---

## 6. 当前 API 的真实限制

### 6.1 实验提交是异步接受，不是同步完成
- `POST /api/experiments` 只返回 accepted + task/experiment metadata
- 需要通过 `GET /api/tasks/{task_id}` 轮询任务状态
- 完成后再用 `result_ref` 去取 report

### 6.2 当前无取消任务 / 重试任务 API
当前尚未实现：
- cancel task
- retry task
- list experiments / list tasks / list reports

### 6.3 当前 report 读取依赖本地文件存在
- metadata 在 DB 中
- report 内容在文件系统中
- 若文件不存在，则 `content` 可能为空

### 6.4 当前后台执行模型是轻量线程池
- 不是 durable queue
- 不是分布式 worker
- 更适合 Phase 1 主链打通，而不是高并发生产调度
