// Copy-paste composable for deployability-aware frontend pages.
// Suggested path in frontend repo: src/composables/useDeployability.ts

import { computed, type ComputedRef } from 'vue'
import type {
  DeployabilityItem,
  DeployabilitySummary,
  DeployabilityViewModel,
} from './types/deployability'
import {
  deployabilityStatusText,
  deployabilityStatusType,
  formatAumLabel,
  toDeployabilityViewModel,
} from './utils/deployability'

export interface UseDeployabilityReturn {
  growth: ComputedRef<DeployabilityItem | null>
  valuePrimary: ComputedRef<DeployabilityItem | null>
  valueBaselineReference: ComputedRef<DeployabilityItem | null>
  growthVm: ComputedRef<DeployabilityViewModel>
  valuePrimaryVm: ComputedRef<DeployabilityViewModel>
  valueBaselineReferenceVm: ComputedRef<DeployabilityViewModel>
  allocatorBlocked: ComputedRef<boolean>
  valueOverlayBlocked: ComputedRef<boolean>
  hasAnyBlockedStrategy: ComputedRef<boolean>
  summaryCards: ComputedRef<DeployabilityViewModel[]>
}

export function useDeployability(
  deployability: DeployabilitySummary | null | undefined,
): UseDeployabilityReturn {
  const growth = computed<DeployabilityItem | null>(() => deployability?.growth ?? null)
  const valuePrimary = computed<DeployabilityItem | null>(() => deployability?.value_primary ?? null)
  const valueBaselineReference = computed<DeployabilityItem | null>(
    () => deployability?.value_baseline_reference ?? null,
  )

  const growthVm = computed(() => toDeployabilityViewModel('Growth', growth.value))
  const valuePrimaryVm = computed(() => toDeployabilityViewModel('Value Primary', valuePrimary.value))
  const valueBaselineReferenceVm = computed(() =>
    toDeployabilityViewModel('Value Baseline Reference', valueBaselineReference.value),
  )

  const allocatorBlocked = computed(() => growth.value?.deployment_blocked === true)
  const valueOverlayBlocked = computed(() => valuePrimary.value?.deployment_blocked === true)
  const hasAnyBlockedStrategy = computed(
    () =>
      growth.value?.deployment_blocked === true ||
      valuePrimary.value?.deployment_blocked === true ||
      valueBaselineReference.value?.deployment_blocked === true,
  )

  const summaryCards = computed(() => [
    growthVm.value,
    valuePrimaryVm.value,
    valueBaselineReferenceVm.value,
  ])

  return {
    growth,
    valuePrimary,
    valueBaselineReference,
    growthVm,
    valuePrimaryVm,
    valueBaselineReferenceVm,
    allocatorBlocked,
    valueOverlayBlocked,
    hasAnyBlockedStrategy,
    summaryCards,
  }
}

export { deployabilityStatusText, deployabilityStatusType, formatAumLabel }
