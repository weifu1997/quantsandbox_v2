# 参考数据（Reference）

## 主板股票清单

文件位置：
- `data/raw/reference/stock_basic_main_board.parquet`

采集脚本：
- `scripts/collect_stock_basic.py`

默认参数：
- `market=主板`
- `list_status=L`

建议保留字段：
- `ts_code`
- `symbol`
- `name`
- `area`
- `industry`
- `market`
- `list_status`
- `list_date`
- `delist_date`
- `ticker`
- `updated_at`

用途：
- 生成主板 universe
- 校验 ticker 合法性
- 名称映射与展示
- 后续按上市日期 / 行业做过滤
