# QuantSandbox V2 Deployability / Allocator / Pipeline 交付说明

## 概览

本次交付已把 **deployability 治理结果** 从研究脚本层，打通到：

1. 后端 report service / API
2. decision summary / config governance
3. allocator 执行层
4. 主 pipeline
5. 前端页面展示层

现在系统已经从“报告里有 deployability 字段”演进为：

> deployability 已成为后端、治理、配置、allocator、前端共同消费的统一结构化契约。

---

## 一、后端交付

### 1. report service 支持 latest / fallback 读取

已修改：
- `app/services/report_service.py`

实现方式：
- 先查数据库 report registry
- 若查不到，则 fallback 扫描 `data/reports/`

支持的文件解析方式：
- `{report_id}.json`
- `{report_id}.md`
- `{report_id}_latest.json`
- `{report_id}_latest.md`

当前可直接成功读取的典型 report id：
- `research_decision_summary_latest`
- `strategy_line_allocator_latest`

---

### 2. API 已暴露 deployability

已修改：
- `app/api/reports.py`
- `app/api/schemas.py`

`GET /api/reports/{report_id}` 当前返回：
- `structured`
- `deployability`

其中 `deployability` 已从 summary 顶层抽出，前端不需要从大 JSON 深挖。

---

### 3. CORS 已开放给前端 dev server

已修改：
- `app/main.py`

当前允许来源：
- `http://127.0.0.1:5173`
- `http://localhost:5173`

结果：
- 前端 dev server 可直接跨源访问 FastAPI `8000`

---

## 二、治理与 allocator 交付

### 4. allocator 正式消费 deployability schema

已修改：
- `scripts/run_strategy_line_allocator.py`

当前逻辑：
- 读取 `research_decision_summary_latest.json` 中的 `deployability`
- 当 `growth.deployment_blocked = true` 时，allocator 直接 blocked
- 当 `value_primary.deployment_blocked = true` 时，overlay 权重强制归零

当前真实结果：
- `allocator_status.status = blocked`
- `allocator_status.reason = growth core revgrowth_always_on_v1 is deployment_blocked by deployability schema`

---

### 5. allocator latest alias 已补齐

已修改：
- `scripts/run_strategy_line_allocator.py`

每次运行 allocator 后都会写出：
- `data/reports/strategy_line_allocator_<timestamp>.json`
- `data/reports/strategy_line_allocator_latest.json`

结果：
- 前端与其他消费者不再需要硬编码时间戳文件名

---

### 6. 主 pipeline 已纳入 allocator 步骤

已修改：
- `scripts/run_current_working_config_pipeline.py`

当前 pipeline 顺序：
1. `growth_review`
2. `value_review`
3. `realism`
4. `capacity`
5. `scale_stress`
6. `decision_summary`
7. `strategy_line_allocator`
8. `sync_working_config`

结果：
- 主流程跑完会自动刷新 summary latest、allocator latest、config

---

## 三、前端交付

### 7. 已创建真实 web 工程骨架

目录：
- `web/`

已创建基础文件：
- `web/package.json`
- `web/vite.config.ts`
- `web/tsconfig.json`
- `web/index.html`
- `web/src/main.ts`
- `web/src/App.vue`

---

### 8. deployability 类型 / 工具 / composable 已落地

已创建：
- `web/src/types/deployability.ts`
- `web/src/utils/deployability.ts`
- `web/src/composables/useDeployability.ts`

功能：
- deployability 类型定义
- AUM label 格式化
- blocked / deployable 状态格式化
- deployability 数据消费组合逻辑

---

### 9. 页面组件已落地

已创建：
- `web/src/components/DeployabilityBadge.vue`
- `web/src/components/DeployabilityCard.vue`
- `web/src/components/DeployabilityPanel.vue`

---

### 10. 前端真实 API 接入已完成

已修改：
- `web/src/App.vue`

当前默认读取：
- `research_decision_summary_latest`
- `strategy_line_allocator_latest`

当前默认 API base：
- `http://127.0.0.1:8000`

---

### 11. 前端 UI 数据绑定 bug 已修复

修复点：

#### `useDeployability`
- 之前不能正确处理 `ref/computed`
- 现在改为 `unref(...)`，支持响应式对象

#### `DeployabilityCard`
- 之前把 `vm.value` 解构成普通常量，导致后续不更新
- 现在直接读取响应式 `vm` 字段

结果：
- deployability 卡片已能显示真实字段

---

## 四、统一 deployability schema

当前统一 schema 包含：
- `deployable_aum_floor`
- `first_light_aum`
- `first_medium_aum`
- `first_heavy_aum`
- `first_extreme_aum`
- `recommended_max_aum`
- `deployment_blocked`
- `blocking_reasons`

当前消费方：
- `strategy_scale_stress_summary`
- `research_decision_summary`
- `current_working_strategy_config`
- `strategy_line_allocator`
- 前端 deployability dashboard

---

## 五、当前系统行为说明

### 1. 后端 report 读取行为

`/api/reports/{report_id}` 当前逻辑：
1. 先查数据库 report registry
2. 找不到时，从 `data/reports/` 用 latest/fallback 规则查文件

---

### 2. 当前 governance 行为

#### growth
如果 growth deployability 被判 blocked：
- summary 会 stop / degrade
- allocator 会 blocked
- 前端显示 blocked

#### value
如果 value primary deployability 被判 blocked：
- additive eligibility 会降级
- promotion blockers 增加 scale-stress blocker
- allocator overlay 会强制归零
- 前端显示 value blocked

---

### 3. 当前前端页面行为

前端 dev server：
- `http://127.0.0.1:5173`

后端 API：
- `http://127.0.0.1:8000`

当前页面展示：
- API Connected / Error
- Allocator Blocked / Open
- Growth / Value Primary / Value Baseline Reference 三张 deployability 卡片
- allocator / portfolio 状态与原因

每张 deployability 卡片展示：
- `Deployment Blocked`
- `Recommended Max AUM`
- `First Extreme AUM`
- `Deployable AUM Floor`
- `First Light AUM`
- `First Heavy AUM`
- `Blocking Reasons`

---

## 六、当前真实结果

### 1. decision summary
当前 latest：
- `data/reports/research_decision_summary_latest.json`

当前结论：
- `growth`: blocked
- `value_primary`: blocked
- `value_baseline_reference`: blocked

---

### 2. allocator
当前 latest：
- `data/reports/strategy_line_allocator_latest.json`

当前结果：
- `allocator_status.status = blocked`
- `allocator_status.reason = growth core revgrowth_always_on_v1 is deployment_blocked by deployability schema`

---

### 3. 前端页面当前真实显示

#### Growth
- `Deployment Blocked`: `Yes`
- `Recommended Max AUM`: `—`
- `First Extreme AUM`: `1M`

#### Value Primary
- `Deployment Blocked`: `Yes`
- `Recommended Max AUM`: `—`
- `First Extreme AUM`: `1M`

#### Value Baseline Reference
- `Deployment Blocked`: `Yes`
- `Recommended Max AUM`: `—`
- `First Extreme AUM`: `1M`

#### Allocator
- `Allocator blocked`
- `Value overlay disabled`

---

## 七、测试与验证

### Python 测试
已通过关键测试：
- `tests/scripts/test_run_current_working_config_pipeline.py`
- `tests/scripts/test_run_strategy_line_allocator.py`
- `tests/unit/api/test_reports_deployability.py`

关键结果：
- `10 passed`

### 前端构建
已通过：
```bash
cd /root/project/quantsandbox_v2/web && npm run build
```

### 浏览器联调
已验证：
- 前端页面可打开
- 可请求真实后端 API
- 无 API Error
- deployability cards 显示真实数据
- allocator status 显示真实结果

---

## 八、常用入口

### 关键报告文件
- `data/reports/research_decision_summary_latest.json`
- `data/reports/strategy_line_allocator_latest.json`
- `data/reports/strategy_scale_stress_summary_latest.json`
- `data/reports/current_working_strategy_config.json`

### 关键脚本
- `scripts/build_research_decision_summary.py`
- `scripts/run_strategy_scale_stress_summary.py`
- `scripts/run_strategy_line_allocator.py`
- `scripts/sync_current_working_config.py`
- `scripts/run_current_working_config_pipeline.py`

### 前端目录
- `web/`

---

## 九、如何重新运行

### 1. 跑主流程
```bash
cd /root/project/quantsandbox_v2
. .venv/bin/activate
python scripts/run_current_working_config_pipeline.py
```

该命令会刷新：
- summary latest
- allocator latest
- config

### 2. 启后端
```bash
cd /root/project/quantsandbox_v2
. .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. 启前端
```bash
cd /root/project/quantsandbox_v2/web
npm run dev -- --host 127.0.0.1 --port 5173
```

---

## 十、已知限制

1. `strategy_line_allocator` 当前只输出 json / latest json，没有 markdown alias
2. 前端当前是单页 dashboard，不是完整多页面产品化 UI
3. 当前 allocator 结果稳定 blocked，不是前端 bug，而是 deployability 的真实治理结论

---

## 一句话总览

本次交付已经把：

> `scale-stress -> decision summary -> config -> allocator -> API -> frontend`

整条链路打通，并用真实数据验证成功。当前系统会基于统一 deployability schema，自动阻断不可部署策略，并在前后端同时体现这一治理结论。
