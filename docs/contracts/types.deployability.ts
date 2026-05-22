// Copy-paste frontend type definitions for deployability-aware report consumption.
// Suggested path in frontend repo: src/types/deployability.ts

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
