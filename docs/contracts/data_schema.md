# 数据契约（Phase 1）

## 标准行情字段

必需字段：
- `date`
- `ticker`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`

说明：
- `date` 使用可解析为 pandas Timestamp 的日期值
- `ticker` 在进入 dataset 前统一归一化为小写字符串
- `amount` 为成交额，作为后续流动性/约束扩展预留字段

## 研究数据集附加字段

由 dataset service 统一补充：
- `factor:<name>`
- `future_return_<horizon>d`
- `is_valid_sample`
- `missing_reason`

## 因子字段命名

统一使用：
- `factor:momentum_20d`
- `factor:momentum_60d`
- `factor:reversal_5d`
- `factor:pe`
- `factor:pb`
- `factor:roe`

## 未来收益字段命名

统一使用：
- `future_return_5d`
- `future_return_20d`
- `future_return_60d`
