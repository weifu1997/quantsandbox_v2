# Phase 1 Report Schema（当前实现）

这份文档描述 **当前已经实现** 的报告输出结构，覆盖：

- JSON report payload
- Markdown report 内容结构
- report metadata 持久化摘要
- warning / diagnostics 的当前语义

目标是让：
- service 层
- API 层
- 使用者

都基于同一份“当前真实 report 结构”理解系统，而不是猜测字段。

---

## 1. 报告输出总览

当前 Phase 1 支持两种报告格式：

- `json`
- `markdown`

它们共享同一个**语义事实源**：
- `app.reports.json_report.render_json_report(...)`

也就是说：
- JSON report 直接把这个 payload 结构化输出
- Markdown report 先基于这个 payload 抽 diagnostics / warnings，再渲染成人读格式

这保证了：
- JSON / Markdown 不会各自长成两套逻辑
- `summary` / `warnings` / `factor_diagnostics` 语义来源一致

---

## 2. JSON Report 顶层结构

当前 JSON report 顶层字段包括：

- `title`
- `output_format`
- `config`
- `dataset_summary`
- `factor_results`
- `backtest_results`
- `factor_diagnostics`
- `summary`
- `warnings`

### 2.1 顶层示例

```json
{
  "title": "QuantSandbox v2 Research Report",
  "output_format": "json",
  "config": {
    "start_date": "20240101",
    "end_date": "20241231",
    "factors": ["momentum_20d", "pe"],
    "horizons": [20],
    "top_n": 10,
    "benchmark": "equal_weight_universe"
  },
  "dataset_summary": {
    "rows": 1234,
    "tickers": ["sh600519", "sz000858"],
    "factors": ["momentum_20d", "pe"],
    "horizons": [20],
    "valid_sample_ratio": 0.82,
    "invalid_reasons": {
      "missing_future_return_20d": 42
    },
    "warnings": []
  },
  "factor_results": {},
  "backtest_results": {},
  "factor_diagnostics": [],
  "summary": {
    "factor_count": 2,
    "best_factor": "momentum_20d",
    "warning_count": 1
  },
  "warnings": [
    "dataset contains invalid samples; inspect invalid_reasons"
  ]
}
```

---

## 3. `config` 字段

`config` 是实验输入配置在 report 侧的保留镜像，当前通常至少包括：

- `start_date`
- `end_date`
- `tickers`
- `universe`
- `factors`
- `horizons`
- `rebalance_frequency`
- `top_n`
- `weighting`
- `benchmark`
- `commission_bps`
- `slippage_bps`
- `report_format`

说明：
- 它用于帮助使用者理解报告上下文
- 它不是独立 schema 管理中心，真正的输入契约仍以 API schema / `ExperimentConfig` 为准

---

## 4. `dataset_summary` 字段

当前 `dataset_summary` 由 dataset service 生成，至少包括：

- `rows`
- `tickers`
- `factors`
- `horizons`
- `valid_sample_ratio`
- `invalid_reasons`
- `warnings`

### 字段语义

#### `rows`
研究数据集总行数。

#### `tickers`
本次实际进入 research dataset 的 ticker 列表。

#### `valid_sample_ratio`
样本有效率。当前如果它低于 `0.5`，report warnings 会自动增加：
- `valid_sample_ratio is below 50%; results may be unstable`

#### `invalid_reasons`
记录样本失效原因及计数。当前如果非空，report warnings 会自动增加：
- `dataset contains invalid samples; inspect invalid_reasons`

#### `warnings`
来自 dataset construction 链路的 warning，例如：
- provider warning
- retry warning
- fundamental adapter returned empty dataset

这些 warnings 会直接并入 report 顶层 `warnings`。

---

## 5. `factor_results` 字段

`factor_results` 是 factor research service 的原始结构化输出，当前按 factor_name 分组。

### 当前典型结构

```json
{
  "momentum_20d": {
    "full_sample": {
      "20": {
        "ic": {
          "ic_mean": 0.04,
          "ic_std": 0.12,
          "rank_ic_mean": 0.05,
          "rank_ic_std": 0.10,
          "sample_count": 30,
          "positive_ic_ratio": 0.63
        },
        "group_returns": {
          "Q1": -0.01,
          "Q2": 0.00,
          "Q3": 0.01,
          "Q4": 0.02,
          "Q5": 0.03
        },
        "monotonicity_score": 1.0,
        "diagnostics": {
          "factor_name": "factor:momentum_20d",
          "verdict": "promising",
          "summary": {
            "ic_mean": 0.04,
            "rank_ic_mean": 0.05,
            "sample_count": 30,
            "positive_ic_ratio": 0.63,
            "monotonicity_score": 1.0,
            "top_bottom_spread": 0.04
          },
          "strengths": ["ic_mean_is_material"],
          "warnings": []
        }
      }
    },
    "in_sample": {},
    "out_sample": {}
  }
}
```

说明：
- 当前 report 会保留这份完整结构，不主动扁平化
- 更轻量的人类可读解释，在 `factor_diagnostics` 顶层字段中再次聚合输出

---

## 6. `backtest_results` 字段

`backtest_results` 当前按 factor_name 分组，值为回测引擎输出 payload。

### 当前典型字段

- `factor_name`
- `horizon`
- `top_n`
- `rebalance_frequency`
- `weighting`
- `benchmark_name`
- `annual_return`
- `total_return`
- `max_drawdown`
- `sharpe`
- `turnover`
- `win_rate`
- `cost_paid`
- `holdings_by_rebalance_date`
- `equity_curve`
- `benchmark_equity_curve`
- `benchmark_returns`
- `excess_return_vs_benchmark`

说明：
- 当前 report 直接保留 backtest engine 产出，不额外重命名
- 如果后续要冻结更正式的 report schema，可以再单独收这块

---

## 7. `factor_diagnostics` 字段

这是 JSON report 中最重要的“解释层摘要”之一。

它来自：
- `app.reports.json_report._factor_diagnostics(...)`

当前每个因子至少会输出：

- `factor_name`
- `reference_horizon`
- `rank_ic_mean`
- `rank_ic_mean_in_sample`
- `rank_ic_mean_out_sample`
- `monotonicity_score`
- `verdict`
- `notes`
- `warnings`

### 当前 verdict 语义

可能值包括：
- `promising`
- `watchlist`
- `weak`
- `unknown`

### 当前判定逻辑（已实现）

#### `promising`
当：
- `rank_ic_mean > 0.03`
- `monotonicity_score >= 0.75`

#### `weak`
当：
- `rank_ic_mean <= 0`

#### `watchlist`
其它情况

#### `unknown`
当：
- `full_sample` 为空

### 当前 warning 来源

`factor_diagnostics[*].warnings` 目前至少可能包括：
- `in-sample positive but out-of-sample non-positive`
- `group return monotonicity is weak`

这些 warning 会继续向上汇总进 report 顶层 `warnings`。

---

## 8. `summary` 字段

当前 `summary` 是给 metadata / API 概览使用的轻量摘要。

### 当前字段

- `factor_count`
- `best_factor`
- `warning_count`

### 字段语义

#### `factor_count`
`factor_results` 的 factor 数量。

#### `best_factor`
当前按以下排序逻辑选出：
- `rank_ic_mean`
- `monotonicity_score`

取排序最高的 factor_name。

#### `warning_count`
当前 report 顶层 warnings 的数量。

---

## 9. `warnings` 字段

这是 report 顶层的统一 warning 汇总。

当前来源包括：

1. dataset summary warning
2. dataset invalid sample 提示
3. `valid_sample_ratio < 0.5` 提示
4. factor_diagnostics 内部 warning
5. 缺少 factor_results / backtest_results 的提示

### 当前典型 warning 示例

- `valid_sample_ratio is below 50%; results may be unstable`
- `dataset contains invalid samples; inspect invalid_reasons`
- `no factor research results available`
- `no backtest results available`
- `in-sample positive but out-of-sample non-positive`
- `group return monotonicity is weak`
- 各类 dataset/provider/retry warning

说明：
- 当前 warnings 不做去重与级别分类
- Phase 1 先以“完整汇总”优先

---

## 10. Markdown Report 当前结构

Markdown report 不是完整 schema 镜像，而是面向人读的摘要输出。

当前固定大致结构为：

- `# QuantSandbox v2 Research Report`
- `## Config`
- `## Dataset Summary`
- `## Factor Diagnostics`
- `## Backtest Results`
- `## Warnings`（如果有）

### 当前展示内容特点

#### Config
当前展示：
- `start_date`
- `end_date`
- `factors`
- `horizons`
- `top_n`
- `benchmark`

#### Dataset Summary
当前展示：
- `rows`
- `valid_sample_ratio`
- `invalid_reasons`

#### Factor Diagnostics
每个因子当前展示简要行：
- `factor_name`
- `verdict`
- `rank_ic_mean`
- `monotonicity_score`

#### Backtest Results
每个因子当前展示：
- `total_return`
- `annual_return`
- `sharpe`
- `max_drawdown`

#### Warnings
按 bullet list 逐条列出

说明：
- Markdown 当前是简洁摘要，不是 report JSON 的 1:1 映射
- 它依赖 report service 先从 JSON payload 抽出 diagnostics / warnings，再渲染

---

## 11. Report Metadata（DB/API 摘要层）

report metadata 当前存储在 report repository 中，至少包括：

- `report_id`
- `experiment_id`
- `task_id`
- `report_format`
- `report_path`
- `summary`
- `created_at`

### `summary` 当前实际结构

在 report service 中，summary 会额外补上：
- `title`
- `output_format`
- `experiment_id`

因此 API 返回给 report metadata 的 summary 当前至少可包含：
- `title`
- `output_format`
- `experiment_id`
- `factor_count`
- `best_factor`
- `warning_count`

---

## 12. API 读取报告时的当前行为

`GET /api/reports/{report_id}` 当前返回：

- metadata
- `content`
- `content_type`
- `structured`

### JSON 报告
- `content_type = json`
- `content` 为 JSON 文本
- `structured` 为解析后的 JSON dict

### Markdown 报告
- `content_type = markdown`
- `content` 为 markdown 文本
- `structured = null`

说明：
- 当前 API 层不会再对 structured payload 做二次裁剪
- report 内容是否可读，依赖 report file 仍然存在于本地文件系统

---

## 13. 当前限制

### 13.1 顶层 warnings 还没有级别体系
当前没有：
- info / warning / critical 分级
- machine-readable warning code
- warning 去重策略

### 13.2 Markdown 还不是完整 report schema 的镜像
Markdown 当前偏摘要化，适合人读，但不适合再被下游机器强解析。

### 13.3 `factor_results` / `backtest_results` 仍然保留较多原始结构
这在 Phase 1 是可接受的，因为完整性优先于过早抽象。

### 13.4 Report schema 还没有独立 pydantic model 冻结
当前真实结构来自：
- `render_json_report(...)`
- `render_markdown_report(...)`
- `report_service`

如果后续要进一步产品化，可以考虑补一层正式的 report schema model。
