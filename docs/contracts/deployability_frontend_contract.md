# Deployability Frontend Contract Draft

## Scope
This document defines the frontend-facing contract for deployability after the backend/API/output-layer integration completed in QuantSandbox V2.

The goal is to let UI code consume structured deployability fields directly instead of inferring deployability from prose, blocker lists, or free-text portfolio recommendations.

---

## 1. Source API

### Primary endpoint
`GET /api/reports/{report_id}`

When the referenced report is JSON and contains a top-level `deployability` object, the API response now includes:

- `structured`: full JSON report payload
- `deployability`: extracted deployability summary for direct frontend consumption

### Expected report types
Frontend consumers should expect deployability to be available primarily on these report-backed pages:

- `research_decision_summary`
- `strategy_scale_stress_summary`

If the selected report does not carry deployability, the API returns `deployability = null`.

---

## 2. TypeScript Interfaces

```ts
export type AumLabel = 'model_small' | 'model_medium' | 'model_large' | string

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

## 3. Field Semantics

### `deployable_aum_floor`
- The lowest tested AUM bucket that is still considered deployable.
- `null` means no currently tested bucket is deployable.

### `first_light_aum`
- First AUM bucket where the strategy enters the `light` impact bucket.

### `first_medium_aum`
- First AUM bucket where the strategy enters the `medium` impact bucket.

### `first_heavy_aum`
- First AUM bucket where the strategy enters the `heavy` impact bucket.

### `first_extreme_aum`
- First AUM bucket where the strategy enters the `extreme` impact bucket.
- This is one of the strongest deployability warning fields.

### `recommended_max_aum`
- Highest tested AUM bucket still considered acceptable for deployment.
- `null` usually means there is no recommended tested bucket.

### `deployment_blocked`
- Direct boolean that the frontend/execution layer should treat as the main deployability gate.
- `true` means this strategy should not be treated as deployable.

### `blocking_reasons`
- Structured machine-readable explanation list.
- Example:
```json
[
  "model_small:stop_using",
  "model_medium:stop_using",
  "model_large:stop_using"
]
```

---

## 4. Recommended Frontend Utilities

```ts
export function formatAumLabel(label: string | null | undefined): string {
  if (!label) return '—'
  if (label === 'model_small') return '1M'
  if (label === 'model_medium') return '5M'
  if (label === 'model_large') return '10M'
  return label
}

export function deployabilityStatusText(item?: DeployabilityItem | null): string {
  if (!item || item.deployment_blocked == null) return 'Unknown'
  return item.deployment_blocked ? 'Blocked' : 'Deployable'
}

export function deployabilityStatusType(item?: DeployabilityItem | null): 'danger' | 'success' | 'warning' {
  if (!item || item.deployment_blocked == null) return 'warning'
  return item.deployment_blocked ? 'danger' : 'success'
}
```

---

## 5. Suggested Component Props

### 5.1 `DeployabilityBadge`
```ts
interface DeployabilityBadgeProps {
  item?: DeployabilityItem | null
  label?: string
}
```

**Display**
- Badge color from `deployment_blocked`
- Label text: `Blocked`, `Deployable`, or `Unknown`

---

### 5.2 `DeployabilityCard`
```ts
interface DeployabilityCardProps {
  title: string
  item?: DeployabilityItem | null
  showBlockingReasons?: boolean
}
```

**Suggested fields shown on card**
- `deployment_blocked`
- `recommended_max_aum`
- `deployable_aum_floor`
- `first_light_aum`
- `first_medium_aum`
- `first_heavy_aum`
- `first_extreme_aum`
- `blocking_reasons`

---

### 5.3 `DeployabilityPanel`
```ts
interface DeployabilityPanelProps {
  deployability?: DeployabilitySummary | null
}
```

**Suggested rendering**
- Growth card
- Value Primary card
- Value Baseline Reference card

---

## 6. Suggested Page-Level Consumption

### A. Research Decision Summary page
Show a dedicated section:
- `Deployability Summary`
- 3 strategy cards:
  - Growth
  - Value Primary
  - Value Baseline Reference

Recommended fields per card:
- blocked status
- recommended max AUM
- deployable AUM floor
- first extreme AUM
- blocking reasons

---

### B. Allocator page
Use deployability as executable control, not advisory copy.

#### If `deployability.growth.deployment_blocked === true`
- Show top-level alert: `Allocator blocked by growth deployability`
- Disable / hide allocator run action
- Render reason summary from `blocking_reasons`

#### If `deployability.value_primary.deployment_blocked === true`
- Show overlay status: `Value overlay disabled`
- If allocation trace is rendered, annotate it as `deployability_override=value_blocked`

---

### C. Current Working Config / Portfolio page
Display:
- Growth deployability status
- Value deployability status
- `recommended_max_aum`
- `deployment_blocked`
- `first_extreme_aum`

This page should visually align with `keep_rule_status` so users can immediately see:
- governance status
- deployability status
- whether config is effectively deployable

---

## 7. Rendering Rules

### Null handling
These fields may be null:
- `deployable_aum_floor`
- `recommended_max_aum`
- `first_light_aum`
- `first_medium_aum`
- `first_heavy_aum`
- `first_extreme_aum`

**Frontend rule:**
- Render as `—` or `N/A`
- Never render literal `null`

### Priority rule
Frontend logic should prioritize:
1. `deployment_blocked`
2. `recommended_max_aum`
3. `deployable_aum_floor`
4. `first_extreme_aum`

`blocking_reasons` is explanatory only.

---

## 8. Example UI ViewModel

```ts
export interface DeployabilityViewModel {
  title: string
  blocked: boolean | null
  blockedText: string
  blockedType: 'danger' | 'success' | 'warning'
  deployableAumFloor: string
  recommendedMaxAum: string
  firstLightAum: string
  firstMediumAum: string
  firstHeavyAum: string
  firstExtremeAum: string
  blockingReasons: string[]
}

export function toDeployabilityViewModel(
  title: string,
  item?: DeployabilityItem | null,
): DeployabilityViewModel {
  return {
    title,
    blocked: item?.deployment_blocked ?? null,
    blockedText: deployabilityStatusText(item),
    blockedType: deployabilityStatusType(item),
    deployableAumFloor: formatAumLabel(item?.deployable_aum_floor),
    recommendedMaxAum: formatAumLabel(item?.recommended_max_aum),
    firstLightAum: formatAumLabel(item?.first_light_aum),
    firstMediumAum: formatAumLabel(item?.first_medium_aum),
    firstHeavyAum: formatAumLabel(item?.first_heavy_aum),
    firstExtremeAum: formatAumLabel(item?.first_extreme_aum),
    blockingReasons: item?.blocking_reasons ?? [],
  }
}
```

---

## 9. Minimal First UI Pass
If frontend wants the smallest safe integration first, only consume these 4 fields:

- `deployment_blocked`
- `recommended_max_aum`
- `first_extreme_aum`
- `blocking_reasons`

That is enough to support:
- blocked/not blocked UI state
- max allowed AUM display
- earliest hard failure display
- explanatory tooltip or detail list

---

## 10. Important Frontend Rule
Do **not** infer deployability from:
- prose in `portfolio_actions`
- prose in `research_actions`
- free-text summary blocks
- promotion blocker strings alone

Use `deployability` as the source of truth.

---

## 11. Current Limitation
The current repository does not contain the actual frontend source tree (`src/`, `frontend/`, `.vue`, `package.json`, etc.), so this document is a contract draft rather than a patched UI implementation.

Once the frontend repo/path is available, the next concrete step is:
- create the TypeScript interface file
- add deployability cards/panels to summary and allocator pages
- wire badge/disable logic into buttons and overlays
