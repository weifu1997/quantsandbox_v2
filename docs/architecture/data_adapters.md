# 数据源 Adapter（Phase 1.6）

当前系统保留三套 adapter：

## 1. Baseline adapter（默认）
- `InMemoryMarketDataAdapter`
- `InMemoryFundamentalDataAdapter`

作用：
- 作为稳定、可重复、无外部依赖的 regression baseline
- 默认用于测试与主回归

## 2. Formal file adapter
- `FileMarketDataAdapter`
- `FileFundamentalDataAdapter`

作用：
- 从本地标准化文件读取真实市场/财务数据
- 支持 `parquet` / `csv`
- 通过配置切换，不替换 baseline

## 3. Online provider adapter（Tushare）
- `TushareMarketDataAdapter`
- `TushareFundamentalDataAdapter`

作用：
- 使用官方 `tushare` SDK
- 如果配置 `tushare_http_url`，则优先通过第三方 Tushare 兼容地址访问
- 未配置 `tushare_http_url` 时，回退官方 SDK 默认地址

## 配置项

环境变量 / settings：
- `QS_MARKET_DATA_MODE=memory|file|tushare`
- `QS_FUNDAMENTAL_DATA_MODE=memory|file|tushare`
- `QS_MARKET_DATA_FILE=/path/to/market_data.parquet`
- `QS_FUNDAMENTAL_DATA_FILE=/path/to/fundamentals.parquet`
- `QS_TUSHARE_TOKEN=your_token`
- `QS_TUSHARE_HTTP_URL=https://tushare.data.godscode.com.cn` （可选）
- `QS_TUSHARE_PRICE_ADJUST=qfq` （当前预留）

## 当前建议

- CI / 主回归：继续使用 `memory`
- 手工验证 / staging：优先 `file`
- 在线 provider：使用 `tushare`

## 字段映射

### 市场行情
Tushare `daily` -> 标准字段：
- `trade_date` -> `date`
- `vol` -> `volume`
- `amount` -> `amount`
- 其余 `open/high/low/close` 直接对应

### 基本面
Tushare `daily_basic` -> 标准字段：
- `trade_date` -> `date`
- `pe` -> `pe`
- `pb` -> `pb`
- `roe` 当前未由 `daily_basic` 提供，phase 1 保留为空
