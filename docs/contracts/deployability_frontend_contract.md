# Deployability 前端契约（当前实现）

这份文档描述 `QuantSandbox_v2` **当前已经实现** 的 deployability 前端契约。它不是 draft，也不是没有前端代码的纯接口草案，而是对齐当前后端 report API、前端治理页面、deployability utility/composable 的真实消费方式。

---

## 1. 目标

当前 deployability 契约的目标是：

- 前端直接消费结构化 deployability 字段
- 不再从 free-text summary / blocker prose / portfolio_actions 中反推“能不能部署”
- 让治理页、allocator 区域、working config / ledger 页面共享同一 deployability 事实源

当前真实消费入口主要是：

- `GET /api/reports/{report_id}`
- 前端页面：`web/src/App.vue`
- composable：`web/src/composables/useDeployability.ts`
- utility：`web/src/utils/deployability.ts`

---

## 2. Source API

### 主入口

`GET /api/reports/{report_id}`

当 report 是 JSON 且顶层存在 `deployability` 对象时，返回结构中会包含：

- `structured`: 完整 JSON report payload
- `deployability`: 从 `structured.deployability` 抽取出的 deployability summary

对应后端：

- `app/api/reports.py`

### 当前主要消费的 report 类型

前端当前主要在这些 report 驱动页面消费 deployability：

- `research_decision_summary`
- `strategy_line_allocator`
- 与治理面板相关的 report alias 页面

若所选 report 不含 deployability：

- API 返回 `deployability = null`

---

## 3. 当前真实 TypeScript 接口

当前可按以下接口理解：

```ts
export type AumLabel =
  | 'model_micro'
  | 'model_small'
  | 'model_medium'
  | 'model_large'
  | string

export interface DeployabilityItem {
  deployable_aum_floor: AumLabel | null
  first_light_aum: AumLabel | null
  first_medium_aum: AumLabel | null
  first_heavy_aum: AumLabel | null
  first_extreme_aum: AumLabel | null
  recommended_max_aum: AumLabel | null
  deployment_blocked: boolean | null
  blocking_reasons: string[]
}

export interface DeployabilitySummary {
  growth?: DeployabilityItem | null
  value_primary?: DeployabilityItem | null
  value_baseline_reference?: DeployabilityItem | null
}

export interface ReportApiResponse {
  report_id: string
  experiment_id: string
  task_id: string | null
  report_format: string
  report_path: string
  summary: Record<string, unknown> | null
  content_type: string
  content: string | null
  structured: Record<string, unknown> | null
  deployability: DeployabilitySummary | null
}
```

---

## 4. 字段语义

### `deployable_aum_floor`

- 最低仍被判定为 deployable 的 tested AUM bucket
- `null` 表示当前没有可部署 bucket

### `first_light_aum`

- 第一次进入 `light` impact bucket 的 AUM 档位

### `first_medium_aum`

- 第一次进入 `medium` impact bucket 的 AUM 档位

### `first_heavy_aum`

- 第一次进入 `heavy` impact bucket 的 AUM 档位

### `first_extreme_aum`

- 第一次进入 `extreme` impact bucket 的 AUM 档位
- 是最强的一类 deployability 警示字段之一

### `recommended_max_aum`

- 当前仍被建议部署的最大 tested AUM bucket

### `deployment_blocked`

- 前端最应该直接消费的布尔门控字段
- `true` 表示当前不应视为 deployable

### `blocking_reasons`

- 结构化原因列表
- 用于解释而不是取代 `deployment_blocked`

---

## 5. 当前真实显示口径

当前前端不是英文显示，而是中文治理页面，因此推荐显示口径应和当前 utility 对齐。

### AUM 标签映射

当前实际前端映射应为：

```ts
export function formatAumLabel(label: string | null | undefined): string {
  if (!label) return '—'
  if (label === 'model_micro') return '10万'
  if (label === 'model_small') return '100万'
  if (label === 'model_medium') return '500万'
  if (label === 'model_large') return '1000万'
  return label
}
```

### 状态文本映射

```ts
export function deployabilityStatusText(item?: DeployabilityItem | null): string {
  if (!item || item.deployment_blocked == null) return '未知'
  return item.deployment_blocked ? '已阻塞' : '可部署'
}

export function deployabilityStatusType(
  item?: DeployabilityItem | null,
): 'danger' | 'success' | 'warning' {
  if (!item || item.deployment_blocked == null) return 'warning'
  return item.deployment_blocked ? 'danger' : 'success'
}
```

---

## 6. 当前 composable 行为

对应代码：

- `web/src/composables/useDeployability.ts`

当前 composable 的真实职责：

- 从 `DeployabilitySummary` 中拆出：
  - `growth`
  - `valuePrimary`
  - `valueBaselineReference`
- 生成 view model：
  - `growthVm`
  - `valuePrimaryVm`
  - `valueBaselineReferenceVm`
- 推导布尔状态：
  - `allocatorBlocked`
  - `valueOverlayBlocked`
  - `hasAnyBlockedStrategy`
- 汇总 `summaryCards`

### 当前关键规则

- `allocatorBlocked` 由 `growth.deployment_blocked === true` 决定
- `valueOverlayBlocked` 由 `value_primary.deployment_blocked === true` 决定

这意味着前端当前不是“平铺展示 deployability”，而是已经把 deployability 用作治理控制输入。

---

## 7. 当前页面级消费方式

## 7.1 治理面板（当前主页面）

对应代码：

- `web/src/App.vue`

当前治理面板会：

1. 读取 `research_decision_summary_latest`
2. 读取 `strategy_line_allocator_latest`
3. 从 decision summary report 中取：
   - `deployability`
4. 从 allocator report 中取：
   - `allocator_status`

然后页面渲染：

- 成长线 deployability card
- 价值主线 deployability card
- 价值基线参考 deployability card
- allocator blocked / available 状态
- value overlay blocked / enabled 状态

## 7.2 Allocator 区域

当前页面没有单独 allocator app，但在治理面板中已经体现出 allocator 的真实消费规则：

### 若 `growth.deployment_blocked === true`

前端当前应视为：

- 分配器被阻塞
- Growth 主线不可继续作为正常 working line 展示为“可运行”

### 若 `value_primary.deployment_blocked === true`

前端当前应视为：

- Value overlay 已禁用
- 页面应明确给用户一个可读的治理状态，而不是让用户自行推断

## 7.3 Governance / current working config 页面

当前页面会同时展示：

- deployability 状态
- allocator 状态
- ledger / 实盘化收益核算相关报告

因此 deployability 在前端中不再是“研究结果附属信息”，而是治理页面的一级输入。

---

## 8. 当前建议的组件契约

### `DeployabilityCard`

```ts
interface DeployabilityCardProps {
  title: string
  item?: DeployabilityItem | null
}
```

当前建议展示字段：

- `deployment_blocked`
- `recommended_max_aum`
- `deployable_aum_floor`
- `first_light_aum`
- `first_medium_aum`
- `first_heavy_aum`
- `first_extreme_aum`
- `blocking_reasons`

### `DeployabilityPanel`

```ts
interface DeployabilityPanelProps {
  deployability?: DeployabilitySummary | null
}
```

建议展示：

- Growth
- Value Primary
- Value Baseline Reference

---

## 9. Null handling 规则

这些字段可能为 `null`：

- `deployable_aum_floor`
- `recommended_max_aum`
- `first_light_aum`
- `first_medium_aum`
- `first_heavy_aum`
- `first_extreme_aum`

前端规则：

- 显示为 `—`
- 不直接显示字面量 `null`

---

## 10. 优先级规则

当前前端逻辑应优先使用：

1. `deployment_blocked`
2. `recommended_max_aum`
3. `deployable_aum_floor`
4. `first_extreme_aum`
5. `blocking_reasons`

说明：

- `blocking_reasons` 是解释字段，不应取代 `deployment_blocked`
- 前端不要从 free-text summary 推导 deployability

---

## 11. 当前最小安全消费子集

如果某个新前端区域只想做最小接入，至少应消费这 4 个字段：

- `deployment_blocked`
- `recommended_max_aum`
- `first_extreme_aum`
- `blocking_reasons`

这已经足够支持：

- blocked / not blocked 状态显示
- 最大建议 AUM 显示
- 最早硬风险档位显示
- tooltip / reason list 解释

---

## 12. 当前最重要的前端红线

前端当前必须坚持：

1. **不要从 prose 推导 deployability**
   - 不要从 `portfolio_actions`
   - 不要从 `research_actions`
   - 不要从 free-text summary
   - 不要从 blocker 文案本身

2. **以 `deployability` 字段为 source of truth**

3. **治理页与 allocator 状态必须能直接消费结构化 deployability 字段**

4. **中文 UI 使用中文状态文本与中文 AUM 映射**

这几条就是当前前端 deployability 契约最核心的部分。