import type { DeployabilityItem, DeployabilityViewModel } from '@/types/deployability'

export function formatAumLabel(label: string | null | undefined): string {
  if (!label) return '—'
  if (label === 'model_micro') return '10万'
  if (label === 'model_small') return '100万'
  if (label === 'model_medium') return '500万'
  if (label === 'model_large') return '1000万'
  return label
}

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

export function isAllocatorBlocked(item?: DeployabilityItem | null): boolean {
  return item?.deployment_blocked === true
}

export function isOverlayBlocked(item?: DeployabilityItem | null): boolean {
  return item?.deployment_blocked === true
}

export function recommendedAumText(item?: DeployabilityItem | null): string {
  return formatAumLabel(item?.recommended_max_aum)
}

export function extremeAumText(item?: DeployabilityItem | null): string {
  return formatAumLabel(item?.first_extreme_aum)
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
