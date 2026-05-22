# 真正收益导向长期实施总纲（QuantSandbox v2）

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 把当前分散的研究结论、working config、decision/realism/capacity 报告层，收敛成一套围绕“真正收益”“长期稳定赚钱”“growth 作为可执行主线”“value 作为可选增益”的正式实施总纲，并据此驱动后续开发、评审、验证与运行治理。

**Architecture:** 不新增花哨策略表面，不先做复杂 allocator，而是在现有 `current_working_config → decision_summary → realism_stress → capacity_constraints → pipeline` 的链条上，补齐统一目标、统一数据契约、统一治理门槛，让系统从“能做研究”进化到“能持续产出更可信的真实回报判断”。

**Tech Stack:** Python、现有 `scripts/` 报告/流水线脚本、`data/reports/` 工件、Markdown 设计文档、pytest。

---

## 1. 当前已落定状态（Current Settled State）

### 1.1 当前 working config 已明确
配置文件：`data/reports/current_working_strategy_config.json`

当前正式运行态：
- `working_universe_policy = amount_bottom_30pct`
- `weighting_policy = equal_weight`
- `growth_core = revgrowth_always_on_v1`
- `value_primary = pbindlow_downtrend_narrow_quality_v1`
- `value_status = watch`

### 1.2 已有工程/研究结论
已确认：
- `tail30 + equal-weight` 是当前 working config
- growth 线是当前执行锚点（execution anchor）
- value 线目前仍不能作为主执行线，只能维持 `watch`
- `liquidity-aware reweighting v1` 已被否决，不应重新默认引回主线
- `entry-gating v1` 已被否决，不应重新作为当前主线路径
- soft-penalty 仅保留为未来研究方向，不进入当前正式执行逻辑

### 1.3 已有脚本与报告层
当前关键脚本：
- `scripts/run_current_working_config_pipeline.py`
- `scripts/build_research_decision_summary.py`
- `scripts/build_research_realism_stress.py`
- `scripts/build_research_capacity_constraints.py`

当前关键文档：
- `docs/research-decision-summary-design.md`
- `docs/research-realism-stress-design.md`
- `docs/research-capacity-constraints-design.md`
- `docs/relative-liquidity-tail-pruning-plan.md`
- `docs/filtered-rerun-amount-bottom-20pct-plan.md`
- `docs/value-line-future-review-plan-topn20.md`

### 1.4 当前系统的真实缺口
真正妨碍“长期稳定收益”的，不是少一个花哨策略，而是：
1. 收益主叙事仍主要依赖 growth 单线
2. value 当前还不能证明能带来稳定可执行增益
3. 流动性/容量风险虽然已被发现，但还没有完全转成硬治理门槛
4. 研究收益还没有被系统性证明能稳定转成真实可执行收益
5. 现有文档是分层专题设计，缺少一份以“真正收益”为最高目标的统一正式总纲

---

## 2. 目标状态（Target State）

### 2.1 总目标
系统的核心目标，不再是“研究结果好不好看”，而是：
- 稳定赚钱
- 避免假收益
- 把 growth 真正变成可执行主线
- 把 value 从拖累变成可选增益
- 把系统升级成长期能滚动生存的赚钱机器

### 2.2 系统最终应该能稳定回答的问题
每次正式运行后，系统必须能明确回答：
1. 当前 working config 是什么
2. 当前 working config 是否还应该继续 keep
3. growth 是否仍是主执行线
4. value 目前是 watch、additive，还是应降回 reference-only
5. 当前收益判断在 realism / capacity / liquidity 约束下是否仍成立
6. 当前阶段最值得做的是继续执行、继续观察、还是调整配置

### 2.3 非目标（本总纲不鼓励的方向）
- 不以扩大策略表面数量为优先
- 不以复杂 allocator 替代核心 alpha 主线判断
- 不允许用“更漂亮的研究报告”掩盖真实执行性不足
- 不允许单次实验结果直接改写正式 working config

---

## 3. 核心原则

### 原则 1：真正收益优先于研究美观
先问“真实世界下还能不能赚”，再问“研究指标是不是更好看”。

### 原则 2：主线收敛优先于策略扩张
默认只维护少数明确角色：
- growth core
- value primary
- value baseline/reference

### 原则 3：working config 必须是唯一正式执行口径
文档、脚本、报告三者必须围绕同一个 working config，不允许各说各话。

### 原则 4：研究结论必须落到可执行工件
任何研究结论，如果不能最终落到以下至少一项，就不能算完成：
- config 字段
- report 字段
- pipeline 输出
- review gate
- promotion / demotion 规则

### 原则 5：先防开发错，再追求做更多
每一阶段必须先定义数据契约、代码职责、验证门槛，再进入实现。

---

## 4. 目标架构：真正收益操作系统（Real-Returns Operating System）

### 4.1 决策层（Decision Layer）
负责把候选研究状态汇总成结构化决策。

主要脚本：
- `scripts/build_research_decision_summary.py`

主要职责：
- 汇总 tracked candidates 的状态
- 生成 `research_actions` / `portfolio_actions`
- 输出 working config 是否仍应 keep
- 明确 growth / value 当前系统角色

### 4.2 现实层（Realism Layer）
负责把“研究收益”翻译成“现实可执行性判断”。

主要脚本：
- `scripts/build_research_realism_stress.py`

主要职责：
- 成本敏感性
- 集中度风险
- 流动性风险
- 执行现实性

### 4.3 容量层（Capacity Layer）
负责把现实风险转换成资本规模下的约束。

主要脚本：
- `scripts/build_research_capacity_constraints.py`

主要职责：
- 在不同 capital assumptions 下评估容量
- 给出 `constraint_breach` 与建议动作
- 为 working config 是否可长期运行提供容量依据

### 4.4 运行层（Operating Layer）
负责表达“当前正式执行主线”。

主要脚本：
- `scripts/run_current_working_config_pipeline.py`

主要职责：
- 串联 current working config 下的 review → realism → capacity → decision summary
- 作为当前正式主线的单一入口

### 4.5 治理层（Governance Layer）
负责定义进入/保留/退出 working config 的规则。

治理对象：
- growth core
- value primary
- value baseline reference
- working_universe_policy
- weighting_policy
- promotion / demotion rules

---

## 5. P0 / P1 / P2 路线图

## P0：把“当前真实主线”正式化

### 目标
先不扩策略，不重做 allocator，先把当前已落定主线写成正式 operating doctrine，并让代码与报告明确表达出来。

### 范围
- 固化当前 working config 的正式语义
- 明确 growth 是 execution anchor
- 明确 value 目前仅是 watch / optional additive candidate
- 统一 decision / realism / capacity / working config 的交叉引用
- 补齐“真正收益导向”的统一 report/config contract

### P0 交付物
1. 本正式总纲文档
2. `current_working_strategy_config.json` 字段契约增强
3. `research_decision_summary` 中新增真正收益导向字段
4. 对应测试与 Markdown 输出更新

### P0 通过标准
- 只看 current working config + 最新三类报告，就能明确知道“当前真正执行什么、为什么这样执行、还该不该继续 keep”

---

## P1：把“真实回报判断”变成硬门槛

### 目标
让主线判断不再停留在描述层，而进入结构化 gating。

### 范围
- 把 realism / capacity 的结果正式并入 decision summary 的主判断
- 定义 value 从 `watch` 升级为 `additive` 的条件
- 定义 growth 主线被挑战或降级的条件
- 把 promotion / demotion blockers 做成机器可读字段

### P1 交付物
- 状态迁移规则
- 升级/降级阻塞项字段
- 更严格的 config recommendation 规则

### P1 通过标准
- 任一候选是否应进入主线，可由报告字段和治理规则一致推出，而不是靠口头判断

---

## P2：把系统推进为长期赚钱机器

### 目标
在不偏离 growth 主线的前提下，形成长期复利运营系统。

### 范围
- 建立周期化 review cadence
- 建立研究 → 决策 → 执行 → 复盘闭环
- 只有在通过真实回报/现实性/容量门槛后，value 才可作为 additive 模块接入
- 为未来更高级执行层预留接口，但不抢跑实现

### P2 通过标准
- 系统可持续输出：当前执行状态、风险状态、下一步动作
- 可以长期滚动，而不是靠临时人工解释维持

---

## 6. 代码触点与职责边界

### 6.1 当前已确认的核心触点
- `scripts/run_current_working_config_pipeline.py`
  - 权威入口：当前正式主线运行
- `scripts/build_research_decision_summary.py`
  - 权威汇总：研究判断 → 决策动作
- `scripts/build_research_realism_stress.py`
  - 权威现实层：研究结果 → 现实约束判断
- `scripts/build_research_capacity_constraints.py`
  - 权威容量层：现实约束 → 资本规模边界

### 6.2 研究脚本的边界
以下脚本可以继续产出研究证据，但不能直接改写正式主线：
- `run_revgrowth_*`
- `run_pbindlow_*`
- `run_growth_line_robustness.py`
- `run_growth_value_head_to_head.py`
- 各类 filtered / tail-pruning / rerun 实验脚本

### 6.3 禁止职责混杂
- 研究脚本不应悄悄承担治理决定
- decision summary 不应偷偷重算 realism
- capacity 不应绕过 decision summary 直接改写 working config
- working pipeline 不应引入未被正式治理接受的默认路径

---

## 7. 需要新增或强化的数据契约

## 7.1 current_working_strategy_config.json 需要强化的字段
建议新增或标准化：
- `operating_mode`
  - 例：`growth_mainline_with_value_watch`
- `decision_basis`
  - 指向最新 decision summary
- `realism_basis`
  - 指向最新 realism report
- `capacity_basis`
  - 指向最新 capacity report
- `promotion_ruleset_version`
- `demotion_ruleset_version`
- `keep_rule_status`
  - 当前 working config 为什么还能 keep
- `mainline_thesis`
  - 当前主线收益逻辑

## 7.2 research_decision_summary 需要强化的字段
建议新增：
- `real_return_priority`
- `mainline_role`
- `additive_eligibility`
- `promotion_blockers`
- `demotion_triggers`
- `working_config_recommendation`
- `true_return_thesis`
- `single_line_dependency_risk`

## 7.3 realism stress 需要强化的字段
不只输出 flag，还要输出：
- `blocks_mainline`
- `blocks_additive`
- `supports_keep`
- `supports_promotion`

## 7.4 capacity constraints 需要强化的字段
建议新增：
- `mainline_feasibility`
- `additive_feasibility`
- `capital_scale_scope`
- `constraint_action`
- `capacity_blockers`

---

## 8. 开发与代码审查门槛（防止开发错）

## 8.1 Gate 0：先文档后实现
任何涉及主线治理语义的改动，必须先在本总纲中找到对应章节和术语。

## 8.2 Gate 1：不得绕过 current working state
新脚本、新字段、新报告，不能绕过 `current_working_strategy_config.json` 私自定义“当前主线”。

## 8.3 Gate 2：每次代码审查必须回答四个问题
1. 这次改动是在增强真正收益判断，还是只是在美化研究输出？
2. 这次改动是否改变了 growth / value 的系统角色？
3. 这次改动是否引入了新的默认执行假设？
4. 这次改动是否破坏了 decision / realism / capacity / working config 一致性？

## 8.4 Gate 3：报告一致性校验
以下工件必须互相可引用且不冲突：
- decision summary
- realism stress
- capacity constraints
- current working config

## 8.5 Gate 4：升级/降级必须有显式证据
- value 从 `watch` 升为 `additive`，必须满足明确门槛
- growth 主线被挑战，必须基于结构化报告，不允许靠单次实验情绪化切换

## 8.6 Gate 5：研究结论不得直通生产
单次 robustness、tail-pruning、filtered rerun 的结果，不能直接替换 working config。
必须经过：
1. decision summary 汇总
2. realism 检查
3. capacity 检查
4. 正式 review sign-off

---

## 9. 端到端验证要求

### 9.1 配置验证
- working config 字段是否完整
- 是否能被主流水线完整消费
- 是否与最新 decision / realism / capacity 报告引用一致

### 9.2 报告验证
- 三类报告是否都引用同一组 tracked candidates
- 是否都能表达 growth 主线 / value watch 状态
- 是否都能给出“keep / review / block / promote”层面的清晰信号

### 9.3 治理验证
- 当报告建议与 current working config 冲突时，系统必须显式暴露冲突，不能静默覆盖

### 9.4 回归验证
新开发不得重新引入已否决方案作为默认路径：
- `liquidity-aware reweighting v1`
- `entry-gating v1`

### 9.5 面向操作者的验证
每个正式报告顶部都应能让操作者快速看到：
- 当前主线是什么
- 还该不该 keep
- 当前最主要的真实回报风险是什么
- 下一步建议动作是什么

---

## 10. 正式开发顺序（从本总纲开始）

### 第一步（本轮应立即开始）
围绕 P0 先做最小但关键的契约升级：
1. 为 `current_working_strategy_config.json` 增加“真正收益导向”的治理字段
2. 为 `build_research_decision_summary.py` 增加对应输出字段
3. 增加测试，确保 working config 与 summary 同步
4. 更新 Markdown 输出，让操作者一眼看到主线、keep 理由、promotion blockers

### 第二步
把 realism / capacity 的机器可读阻塞项接到 decision summary。

### 第三步
再定义 value additive 升级规则与 growth 主线挑战规则。

---

## 11. 本文档与已有专题文档的关系
- 本文档是总纲
- `research-decision-summary-design.md`、`research-realism-stress-design.md`、`research-capacity-constraints-design.md` 是下层专题设计
- 后续开发任务都必须显式引用本总纲的章节编号，避免再次回到“局部修补、全局失焦”的状态
