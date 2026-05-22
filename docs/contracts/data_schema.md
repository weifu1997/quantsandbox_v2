# 数据契约（当前实现）

这份文档描述 `QuantSandbox_v2` **当前已经实现** 的标准化数据契约。目标不是定义所有未来可能出现的字段，而是把当前 adapter、dataset service、factor research、backtest、report 真实依赖的字段与派生列说明清楚，避免文档继续停留在更早版本的“最小字段假设”。

---

## 1. 契约层的角色

当前数据契约主要由以下代码定义：

- `app/domain/data_contracts.py`
- `app/services/dataset_service.py`

其中：

- `data_contracts.py` 负责：
  - 基础字段清单
  - 命名 helper
  - research/backtest dataset 校验
  - ticker / date 标准化
- `dataset_service.py` 负责：
  - merge 数据
  - 生成派生列
  - 补样本标记
  - 落盘 dataset metadata

因此“当前数据契约”不仅包含输入字段，还包含 dataset service 在主链中**会自动生成的派生列**。

---

## 2. 标准行情字段（Market DataFrame）

标准行情输入至少必须包含：

- `date`
- `ticker`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`

说明：

- `date` 必须可被 `pandas.to_datetime(...)` 解析
- `ticker` 进入 dataset 前统一归一化为小写字符串，例如 `sh600519`
- `amount` 是成交额，也是后续流动性、容量、执行成本建模的关键基础字段

对应代码常量：

- `PRICE_COLUMNS`
- `REQUIRED_PRICE_COLUMNS`

对应校验函数：

- `validate_market_dataframe(df)`

---

## 3. 标准财务字段（Fundamental DataFrame）

当前系统认定的标准财务字段为：

- `date`
- `ticker`
- `pe`
- `pb`
- `roe`
- `roa`
- `gross_margin`
- `revenue_growth`
- `profit_growth`

对应代码常量：

- `FUNDAMENTAL_COLUMNS`
- `REQUIRED_FUNDAMENTAL_COLUMNS`

对应校验函数：

- `validate_fundamental_dataframe(df)`

### 重要：provider 缺列兼容行为

当前 `dataset_service.build_research_dataset(...)` 在 fundamentals 非空时，会先做一层兼容：

若 provider 返回的 fundamentals 缺少以下列中的任意一项：

- `pe`
- `pb`
- `roe`
- `roa`
- `gross_margin`
- `revenue_growth`
- `profit_growth`

系统会先补 `pd.NA` 空列，再进入统一校验。

这意味着：

- **标准 schema 仍然是完整 schema**
- 但系统允许上游 provider 暂时不完整，只要能被补齐到统一结构

这个行为对于 file adapter / Tushare adapter / 测试 stub 都很重要。

---

## 4. 标准研究基础数据集（Research Base Dataset）

市场数据与财务数据 merge 后，当前 research base dataset 的基础字段包括：

- `date`
- `ticker`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`
- `pe`
- `pb`
- `roe`
- `roa`
- `gross_margin`
- `revenue_growth`
- `profit_growth`
- `listed_days`

对应代码常量：

- `RESEARCH_BASE_COLUMNS`

对应校验函数：

- `validate_research_dataset(df)`

说明：

- `listed_days` 由 reference data 映射补入，不是 provider 原始字段
- 这只是 **基础层 dataset**
- 因子列、future return 列、样本标记列、执行辅助列会在后续步骤补齐

---

## 5. reference data 衍生字段

当前 dataset service 在基础 merge 后，还会尝试补充 reference 衍生字段：

### `listed_days`

来源：

- `attach_listing_days(...)`
- reference file：`data/raw/reference/stock_basic_main_board.parquet`

语义：

- 当前交易日距离上市日的天数

用途：

- 样本有效性过滤
- `min_sample_listed_days` 约束

若 reference 数据不可用：

- `listed_days` 会为空
- dataset summary warnings 会记录：
  - `listing days unavailable; listed_days filter could not be applied`

---

## 6. 因子字段命名规范

所有因子列统一命名为：

- `factor:<name>`

例如：

- `factor:momentum_20d`
- `factor:momentum_60d`
- `factor:reversal_5d`
- `factor:pe`
- `factor:pb`
- `factor:roe`
- `factor:revenue_growth`

统一 helper：

- `factor_column(name)`

约束：

- `name` 不能为空
- service / validation / backtest 层应优先通过 helper 生成列名

---

## 7. future return 字段命名规范

所有未来收益列统一命名为：

- `future_return_<horizon>d`

例如：

- `future_return_5d`
- `future_return_10d`
- `future_return_20d`
- `future_return_60d`

统一 helper：

- `future_return_column(horizon)`

约束：

- `horizon` 必须为正整数

---

## 8. execution / delayed return 派生字段

当前系统已经引入 execution-aware 的衍生字段，这些字段虽然不在 `data_contracts.py` 的基础清单里，但会在 `dataset_service.add_future_returns(...)` 中统一生成。

### 8.1 `next_open_price`

来源：

- `groupby("ticker")["open"].shift(-1)`

语义：

- 下一根 bar 的开盘价

用途：

- delayed execution return
- board-lot 执行价格 fallback

### 8.2 `rolling_vol_20d`

来源：

- 每个 ticker 的 `close.pct_change()`
- 再做 20 日滚动标准差

当前实现使用：

- `std(ddof=0)`

用途：

- execution slippage 分层
- volatility-aware 交易诊断

### 8.3 `rolling_vol_20d_hist_q80`

来源：

- 每个 ticker 的 `rolling_vol_20d`
- 再做 expanding quantile(0.8)

用途：

- 判断是否进入高波动附加 tick slippage 区间

### 8.4 `delayed_future_return_<horizon>d`

来源：

- `future_close / next_open_price - 1`

语义：

- 以“下一期开盘成交、持有 horizon 天后卖出”的近似 delayed execution 收益口径

用途：

- 当 execution config enabled 且引擎发现该列存在时，回测引擎优先使用 delayed return 列

---

## 9. 样本标记字段规范

在 future return 构造后，研究数据集还应包含：

- `is_valid_sample`
- `missing_reason`

对应代码常量：

- `SAMPLE_FLAG_COLUMNS`

语义：

- `is_valid_sample`：当前样本是否允许进入后续研究 / 回测
- `missing_reason`：样本失效原因

当前常见原因包括：

- `missing_future_return_5d`
- `missing_future_return_10d`
- `missing_future_return_20d`
- `missing_future_return_60d`
- `too_few_trading_days_min_<N>`
- `too_few_listed_days_min_<N>`

这些标记由：

- `add_sample_flags(...)`

统一生成。

---

## 10. 完整研究数据集（Full Research Dataset）

当数据集完成以下步骤后：

1. merge 行情与财务
2. 补 reference 字段（如 `listed_days`）
3. 计算 factor 列
4. 计算 future return / delayed future return / execution 辅助列
5. 补 `is_valid_sample` / `missing_reason`

则完整研究数据集应满足：

- 基础 research base 字段齐全
- 指定因子列齐全：`factor:<name>`
- 指定 future return 列齐全：`future_return_<horizon>d`
- 样本标记字段齐全：`is_valid_sample` / `missing_reason`

对应校验函数：

- `validate_research_dataset(df, factor_names=..., horizons=..., require_sample_flags=True)`

说明：

- `delayed_future_return_*` 与 execution 辅助列当前不是 `validate_research_dataset(...)` 的强制必填项
- 但若启用 execution-aware backtest，它们会成为实际运行口径的一部分

---

## 11. 回测输入数据集契约

回测层至少必须具备：

- `date`
- `ticker`
- 指定因子列，例如 `factor:momentum_20d`
- 指定收益列，例如：
  - `future_return_20d`
  - 或在 delayed execution 场景下使用 `delayed_future_return_20d`

对应校验函数：

- `validate_backtest_dataset(df, factor_col, return_col)`

说明：

- 回测引擎内部还会做数值化、去空值、`is_valid_sample` 过滤
- 但列存在性必须先由契约层保证

---

## 12. 标准化 helper

### `normalize_ticker(value)`

作用：

- 去首尾空格
- 转小写

示例：

- `" SH600519 " -> "sh600519"`

### `normalize_trade_date(value)`

作用：

- 统一通过 `pandas.to_datetime(...)` 解析为 `Timestamp`

---

## 13. 当前 dataset service 的真实执行顺序

当前推荐的 research dataset 构造顺序是：

1. adapter 拉取 market data
2. `validate_market_dataframe(...)`
3. adapter 拉取 fundamental data
4. 若 fundamentals 非空：
   - 补齐缺失标准列
   - `validate_fundamental_dataframe(...)`
5. merge market + fundamentals
6. attach listing days / reference data
7. `validate_research_dataset(df)` 做基础字段校验
8. 计算因子列（`factor:*`）
9. 计算 future return / delayed future return / execution 派生列
10. 计算样本有效性标记
11. 生成 dataset summary
12. `validate_research_dataset(..., require_sample_flags=True)` 做完整校验
13. 持久化 dataset metadata

这个顺序很重要，因为：

- 基础校验不应要求 factor / future return 已存在
- 完整校验应在派生列生成后再做

---

## 14. 当前契约明确不保证的内容

当前数据契约尚未冻结以下内容为统一外部发布 schema：

- benchmark 输出的最终完整公共 schema
- report JSON 的最终公共发布 schema
- 更复杂的公告滞后/财务可得性时点模型
- 多频率混合输入契约
- 所有治理/ledger 报告的统一公共 schema

这些仍在代码中逐步演进，但不影响当前 research/backtest 主链的数据契约。