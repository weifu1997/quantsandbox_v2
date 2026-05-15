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
- `--checkpoint-path`
- `--tickers-file`
- `--check-only`
- `--precheck-only`
- `--dry-run`

### 参数语义说明

- `--check-only`：**纯检查模式**。
  - 只做参数解析、ticker 解析、manifest / checkpoint 路径解析。
  - **不调用 Tushare 拉取数据**。
  - **不写入 parquet 文件**，也**不更新 manifest / checkpoint**。
- `--precheck-only`：**预校验模式**。
  - 扫描现有 parquet，生成 precheck 结果。
  - 输出 covered / incremental / missing / invalid ticker 分类。
  - **不执行真正采集**。
- `--dry-run` **不是纯参数校验**。
  - 它仍会实际调用 Tushare 拉取数据。
  - 只是**不写入 parquet 文件**，也**不更新 manifest / checkpoint**。
  - 适合先验证整条采集链路、检查 warning、确认输出规模。

### 运行行为（当前实现）

当前脚本已经具备以下能力：
- **按 ticker chunk 分批拉取**
- **每个 chunk 拉完后立即写盘**
- **运行中持续输出进度日志**
- **ticker 级 checkpoint / 恢复**
- **failed ticker 队列输出**
- **采集前 precheck 分类**
- **采集后 validation 验收报告**

典型日志示例：
- `[market] chunk=1 tickers=1-50 size=50`
- `[fundamental] chunk=3 tickers=101-150 size=50`
- `tushare fundamentals progress | current=sh600000 completed=1/50`

这意味着：
- 不再需要等全部数据抓完才开始写 parquet
- 运行中可以通过日志观察 market / fundamentals 当前推进到哪一批
- 中途失败时，已经完成的 chunk 会保留落盘结果，不至于整轮白跑
- 再次启动时可以自动跳过已完成 ticker
- 跑完后可以直接根据 validation 报告判断结果是否可接受

### 推荐用法

- 主板全量正式采集：建议先用 `--chunk-size 50`
- 只验证参数 / manifest / ticker 解析：用 `--check-only`
- 只做采集前扫描 / 增量判断：用 `--precheck-only`
- 想真实拉数据但不落盘：用 `--dry-run`
- 想把实验性采集和正式 manifest / checkpoint 隔离：用 `--manifest-path <path>` + `--checkpoint-path <path>`
- 想对失败票单独补采：用 `--market-only` / `--fundamental-only` 搭配 `--tickers-file <failed.json>`

## Manifest / Checkpoint / 报告文件

### Manifest

路径默认：`data/raw/tushare_manifest.json`

记录：
- 输出目录路径
- 最近一次 start/end date
- tickers
- `ticker_count`
- `partition_mode`
- 本次抓取行数
- warnings
- 本次采集模式

### Checkpoint

默认路径：与 manifest 同目录，文件名形如：
- `tushare_manifest.checkpoint.json`

记录：
- `market_completed_tickers`
- `fundamental_completed_tickers`
- `market_failed_tickers`
- `fundamental_failed_tickers`
- `stage`
- `updated_at`

用途：
- 自动跳过已完成 ticker
- 中断后恢复
- failed ticker 输出与补采

### Precheck 报告

默认路径：
- `tushare_manifest.precheck.json`

输出分类：
- `covered_tickers`
- `incremental_tickers`
- `missing_tickers`
- `invalid_tickers`

用途：
- 采集前扫描已有 parquet
- 自动跳过已覆盖到目标 `end_date` 的 ticker
- 识别缺失 / 损坏 / 需要增量的 ticker

### Validation 报告

默认路径：
- `tushare_manifest.validation.json`

输出内容：
- `missing_tickers`
- `extra_tickers`
- `suspicious_row_tickers`
- `uncovered_range_tickers`
- `acceptable`

用途：
- 采集后做结构化验收
- 判断这一轮结果是否可接受

## 仓库边界与版本化规则

默认原则：**只版本化稳定参考数据与文档样例，不默认版本化运行态产物。**

### 建议默认入库
- `data/raw/reference/`
  - 例如：`stock_basic_main_board.parquet`
  - 用途：主板 universe、ticker 合法性校验、名称映射
- `data/archive/legacy-flat-files/`
  - 作为历史兼容样例和迁移参考
- 文档、脚本、测试

### 建议默认不入库（运行态产物）
- `data/raw/market/`
- `data/raw/fundamentals/`
- `data/datasets/`
- `data/db/`
- `data/reports/`
- `data/cache/`
- `manifest / checkpoint / precheck / validation` 等 JSON 报告文件

原因：
- 这些文件体积大、变化频繁
- 包含运行时状态，不利于代码仓库保持干净
- 容易引入测试污染、脏状态和无意义 diff

### 例外情况
如果某一轮数据需要保留为“验收基线”或“公开样例”，建议：
- 单独建立样例目录或 release artifact
- 不要直接把大规模运行态全量数据长期堆在主分支仓库里


- `pe/pb`：`daily_basic`
- `roe`：`fina_indicator`

ROE 对齐策略：
- 使用 `fina_indicator` 的 `ann_date` 和 `roe`
- 按公告日对齐到日频样本
- 使用 backward as-of join，让日频数据继承最近一次已公告的 ROE
