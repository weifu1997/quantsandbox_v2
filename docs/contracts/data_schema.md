# 数据契约（Phase 1）

这份文档描述 Phase 1 的**标准化数据契约**。目标不是覆盖所有未来扩展字段，而是先冻结一条最小但可信的研究主链口径，让：

- adapter
- dataset service
- factor research
- backtest
- report

都依赖同一套字段规范，而不是各自发明一套口径。

---

## 1. 标准行情字段（Market DataFrame）

标准行情输入必须至少包含：

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
- `ticker` 在进入 dataset 前统一归一化为小写字符串，例如 `sh600519`
- `amount` 为成交额，作为后续流动性/容量/约束扩展预留字段

对应代码常量：
- `PRICE_COLUMNS`
- `REQUIRED_PRICE_COLUMNS`

对应校验函数：
- `validate_market_dataframe(df)`

---

## 2. 标准财务字段（Fundamental DataFrame）

标准财务输入必须至少包含：

- `date`
- `ticker`
- `pe`
- `pb`
- `roe`

说明：

- 当前 Phase 1 先只冻结最小经典估值/质量字段
- 后续可以扩展更多财务列，但不应破坏现有最小契约
- `date` / `ticker` 的标准化规则与行情数据保持一致

对应代码常量：
- `FUNDAMENTAL_COLUMNS`
- `REQUIRED_FUNDAMENTAL_COLUMNS`

对应校验函数：
- `validate_fundamental_dataframe(df)`

---

## 3. 标准研究数据集基础字段（Research Base Dataset）

行情与财务 merge 后，研究主数据集在最小口径上必须至少包含：

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

说明：

- 这是 research dataset 的**基础层字段**
- 因子列、未来收益列、样本有效性标记列由 dataset service 在后续步骤统一补充

对应代码常量：
- `RESEARCH_BASE_COLUMNS`

对应校验函数：
- `validate_research_dataset(df)`

> 注意：基础 research dataset 校验不要求已经存在 factor 列、future return 列、sample flag 列。

---

## 4. 因子字段命名规范

所有因子列必须统一命名为：

- `factor:<name>`

例如：
- `factor:momentum_20d`
- `factor:momentum_60d`
- `factor:reversal_5d`
- `factor:pe`
- `factor:pb`
- `factor:roe`

统一 helper：
- `factor_column(name)`

约束：
- `name` 不能为空
- 下游 service / validation / backtest 不应手写拼接 `f"factor:{name}"`，而应尽量通过 helper 生成

---

## 5. 未来收益字段命名规范

所有未来收益列必须统一命名为：

- `future_return_<horizon>d`

例如：
- `future_return_5d`
- `future_return_20d`
- `future_return_60d`

统一 helper：
- `future_return_column(horizon)`

约束：
- `horizon` 必须为正整数
- dataset service / validation / backtest 不应散落手写列名格式，优先通过 helper 生成

---

## 6. 样本标记字段规范

Phase 1 的研究数据集在完成 future return 构造后，还应包含：

- `is_valid_sample`
- `missing_reason`

说明：

- `is_valid_sample`：布尔标记，表示当前样本是否可以进入后续研究/回测
- `missing_reason`：字符串，记录样本失效原因

当前最常见原因示例：
- `missing_future_return_20d`
- `missing_future_return_60d`

对应代码常量：
- `SAMPLE_FLAG_COLUMNS`

当需要校验“完整研究数据集”时，应显式要求这些列存在。

---

## 7. 完整研究数据集（Full Research Dataset）

当数据集已经完成以下步骤后：

1. merge 行情与财务
2. 计算因子列
3. 计算 future return 列
4. 补充样本有效性标记

则完整研究数据集应满足：

- 基础 research base 字段齐全
- 指定因子列齐全：`factor:<name>`
- 指定 future return 列齐全：`future_return_<horizon>d`
- 样本标记字段齐全：`is_valid_sample` / `missing_reason`

对应校验函数：
- `validate_research_dataset(df, factor_names=..., horizons=..., require_sample_flags=True)`

---

## 8. 回测输入数据集契约

回测层并不要求完整 research dataset 的所有列，但至少必须具备：

- `date`
- `ticker`
- 指定因子列，例如 `factor:momentum_20d`
- 指定未来收益列，例如 `future_return_20d`

对应校验函数：
- `validate_backtest_dataset(df, factor_col, return_col)`

说明：

- 回测引擎内部仍会进一步做数值化、去空值、按 `is_valid_sample` 过滤
- 但列存在性应先由契约层保证

---

## 9. 标准化 helper

### `normalize_ticker(value)`

作用：
- 去首尾空格
- 转小写

示例：
- `" SH600519 " -> "sh600519"`

### `normalize_trade_date(value)`

作用：
- 统一通过 `pandas.to_datetime(...)` 解析为 `Timestamp`

示例：
- `"2024-01-02" -> Timestamp('2024-01-02 00:00:00')`

---

## 10. 当前主链执行顺序（重要）

当前 Phase 1 推荐按以下顺序构建并校验研究数据集：

1. adapter 拉取市场数据
2. `validate_market_dataframe(...)`
3. adapter 拉取财务数据
4. 若财务非空，`validate_fundamental_dataframe(...)`
5. merge 得到基础 research dataset
6. `validate_research_dataset(df)` 只校验基础字段
7. 计算因子列（`factor:*`）
8. 计算 future return 列（`future_return_*d`）
9. 补 `is_valid_sample` / `missing_reason`
10. `validate_research_dataset(df, factor_names=..., horizons=..., require_sample_flags=True)` 做完整校验

这样可以避免在 factor / future return 还未生成前就误触发完整契约校验。

---

## 11. Phase 1 明确不做的事

本阶段先**不**在数据契约层冻结以下内容：

- 更复杂的财务字段全集
- 公告滞后/财务可得性建模的最终口径
- benchmark 输出结构的最终统一 schema
- report JSON 的最终外部发布 schema
- 多频率（日/周/月）混合数据契约

这些会在后续阶段逐步补，但不应影响当前最小可信主链的统一口径。
