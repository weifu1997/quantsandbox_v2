# API 使用示例（Phase 1）

## 提交实验

`POST /api/experiments`

示例请求：

```json
{
  "start_date": "20240101",
  "end_date": "20241231",
  "factors": ["momentum_20d", "pe"],
  "horizons": [20],
  "tickers": ["sh600519", "sz000858", "sz300750", "sz000001", "sh600036"],
  "report_format": "json"
}
```

示例响应（精简）：

```json
{
  "status": "accepted",
  "data": {
    "experiment": {"experiment_id": "exp_xxx"},
    "task": {"task_id": "task_xxx", "status": "running"}
  }
}
```

## 查询任务

`GET /api/tasks/{task_id}`

示例响应（精简）：

```json
{
  "status": "success",
  "data": {
    "task_id": "task_xxx",
    "status": "completed",
    "stage": "report",
    "result_ref": "rep_xxx"
  }
}
```

## 查询报告

`GET /api/reports/{report_id}`

说明：
- markdown 报告：返回 `content_type=markdown`，`content` 为 markdown 文本
- json 报告：返回 `content_type=json`，同时附带 `structured` 字段
