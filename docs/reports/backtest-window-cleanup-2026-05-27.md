# Backtest Window Cleanup — 2026-05-27

## 本次目标

本次交付只处理以下范围：

1. 回测窗口语义记录；
2. 回测覆盖摘要；
3. 长区间报告展示 requested / effective / data 三层窗口；
4. 清理工作区中与本次任务无关的既存脏改动。

严格未做：

- 未修改 mark-to-market PnL 计算逻辑；
- 未修改 `dataset_service.add_future_returns`；
- 未修改 `rebalance_calendar` 调仓日规则；
- 未恢复或引入超出本次范围的旧引擎行为增强。

---

## 本次实际保留的代码改动

当前工作区应只剩以下相关文件：

- `app/domain/data_contracts.py`
- `app/domain/backtest/engine.py`
- `scripts/build_research_realism_stress.py`
- `scripts/run_growth_v3_long_window_backtest.py`

### 改动摘要

#### 1. `app/domain/data_contracts.py`
新增：

- `BacktestWindow`
- `BacktestCoverageSummary`

用于表达：

- requested start/end；
- effective first/last rebalance；
- data start/end；
- rebalance count；
- tail truncated rebalance count；
- dropped tail dates。

#### 2. `app/domain/backtest/engine.py`
新增 payload 字段：

- `backtest_window`
- `backtest_coverage_summary`

说明：

- 只新增字段，不改旧字段名；
- 不改现有收益、成本、持仓、会计口径；
- 继续使用当前已有的 mark-to-market close 口径。

#### 3. `scripts/build_research_realism_stress.py`
为 candidate dataset 注入 attrs：

- `requested_start_date`
- `requested_end_date`
- `data_start_date`
- `data_end_date`

用于让回测 payload 能正确生成窗口摘要。

#### 4. `scripts/run_growth_v3_long_window_backtest.py`
将原 `tmp/` 下长窗口脚本正式迁移到 `scripts/`，并在输出中展示：

- requested window；
- effective rebalance window；
- data coverage window；
- `backtest_coverage_summary`。

---

## 工作区清理结果

### 备份位置

本次清理前已备份到：

`/tmp/quantsandbox_cleanup_20260527_174619`

包含：

- `worktree_tracked.patch`
- `git_status_short.txt`
- `git_deleted_tracked.txt`
- `git_untracked.txt`
- `untracked_files.tar.gz`
- `untracked_selected/`

### 已执行的清理动作

1. 备份 tracked diff 与 untracked 文件；
2. 将 `tmp/run_growth_v3_long_window_backtest.py` 迁移为 `scripts/run_growth_v3_long_window_backtest.py`；
3. 恢复与本次任务无关的 tracked 修改和 tracked 删除；
4. 归档并清理与本次任务无关的 untracked 文件与临时脚本；
5. 恢复误删的 tracked 文档文件；
6. 最终将工作区收敛到只剩本次相关改动。

---

## 为什么现在测试是 24 个，不是之前会话里看到的 30 个

### 当前事实

当前运行：

```bash
.venv/bin/python -m pytest tests/unit/domain/test_backtest_engine.py tests/unit/domain/test_data_contracts.py -q
```

结果为：

```text
24 passed
```

### 原因说明

清理前的工作区备份中，`tests/unit/domain/test_backtest_engine.py` 确实存在额外未提交测试改动；
这些额外测试主要覆盖：

- hysteresis 选股行为；
- newcomer persistence gate；
- newcomer quota；
- 更复杂的 board lot 可执行性筛选；
- 可执行性 rank penalty；
- 以及部分测试改名。

但这些测试依赖的是另一批更大的未提交回测引擎增强逻辑，已经超出本次“只改窗口语义记录和展示”的范围。

因此，本次清理过程中没有把那批测试恢复回当前工作树，而是保留了当前仓库基线下可自洽、可回归的 24 个测试。

### 结论

- **24 个测试通过** 是当前交付版本的真实状态；
- 之前会话里看到的“30 个测试”来自清理前更大的未提交工作区，不应与本次纯窗口语义交付混合。

---

## 如果未来需要恢复那批历史未提交测试

只建议在明确要恢复“更大范围的回测引擎增强”时执行。

信息来源：

- 备份 patch：`/tmp/quantsandbox_cleanup_20260527_174619/worktree_tracked.patch`
- 重点文件：`tests/unit/domain/test_backtest_engine.py`

恢复原则：

1. 不要只恢复测试，不恢复其依赖逻辑；
2. 先分离“窗口语义交付”和“引擎行为增强”两个主题；
3. 若要恢复，应单开一轮任务，专门处理：
   - selection hysteresis；
   - newcomer gating / quota；
   - board lot 可执行性筛选增强；
   - 对应测试集回归。

---

## 当前建议状态

建议把本次交付视为：

- **窗口语义与报告诚实展示修复**：完成；
- **工作区脏状态清理**：完成；
- **历史大范围未提交引擎增强恢复**：未做，且不建议混入本次交付。
