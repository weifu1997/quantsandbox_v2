# Tushare -> File 工作流（Phase 1.7）

## 目标

将 Tushare 作为在线采集层，将结果标准化落到本地 `parquet`，后续研究/回测主流程优先走 `file` 模式。

## 为什么继续使用 parquet

当前阶段 `parquet` 是合适的：
- 列式存储，适合研究和因子计算
- pandas / pyarrow 原生支持
- 易于本地增量合并
- 与现有 file adapter 完全兼容

真正决定长期可用性的不是“换格式”，而是：
- manifest
- watermark
- 增量合并策略
- 明确字段契约

## 分区结构

当前正式 file 主线采用 **按 ticker 分区**：

```text
data/raw/
├── market/
│   ├── sh600519.parquet
│   ├── sz000858.parquet
│   └── ...
├── fundamentals/
│   ├── sh600519.parquet
│   ├── sz000858.parquet
│   └── ...
└── tushare_manifest.json
```

优点：
- 单 ticker 增量更新简单
- 大规模 A 股（3000+）管理更自然
- file adapter 只读所需 ticker 文件，避免整表扫描

## 采集脚本

脚本：`scripts/collect_tushare_to_file.py`

支持：
- 自动根据 manifest 推断下一次 `start_date`
- `--append-tickers` 合并新 ticker 到 manifest
- `--market-only`
- `--fundamental-only`
- `--chunk-size`
- `--manifest-path`
- `--check-only`
- `--dry-run`

### 参数语义说明

- `--check-only`：**纯检查模式**。
  - 只做参数解析、ticker 解析、manifest 继承检查。
  - **不调用 Tushare 拉取数据**。
  - **不写入 parquet 文件**，也**不更新 manifest**。
- `--dry-run` **不是纯参数校验**。
  - 它仍会实际调用 Tushare 拉取数据。
  - 只是**不写入 parquet 文件**，也**不更新 manifest**。
  - 适合先验证整条采集链路、检查 warning、确认输出规模。

### 运行行为（当前实现）

当前脚本已经改为：
- **按 ticker chunk 分批拉取**
- **每个 chunk 拉完后立即写盘**
- **运行中持续输出进度日志**

典型日志示例：
- `[market] chunk=1 tickers=1-50 size=50`
- `[fundamental] chunk=3 tickers=101-150 size=50`
- `tushare fundamentals progress | current=sh600000 completed=1/50`

这意味着：
- 不再需要等全部数据抓完才开始写 parquet
- 运行中可以通过日志观察 market / fundamentals 当前推进到哪一批
- 中途失败时，已经完成的 chunk 会保留落盘结果，不至于整轮白跑

### 推荐用法

- 主板全量正式采集：建议先用 `--chunk-size 50`
- 只验证参数 / manifest / ticker 解析：用 `--check-only`
- 想真实拉数据但不落盘：用 `--dry-run`
- 想把实验性采集和正式 manifest 隔离：用 `--manifest-path <path>`

## Manifest

路径：`data/raw/tushare_manifest.json`

记录：
- 输出目录路径
- 最近一次 start/end date
- tickers
- `ticker_count`
- `partition_mode`
- 本次抓取行数
- warnings
- 本次采集模式

## 基本面来源

- `pe/pb`：`daily_basic`
- `roe`：`fina_indicator`

ROE 对齐策略：
- 使用 `fina_indicator` 的 `ann_date` 和 `roe`
- 按公告日对齐到日频样本
- 使用 backward as-of join，让日频数据继承最近一次已公告的 ROE
