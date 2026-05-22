<template>
  <span class="badge" :class="statusClass">{{ statusText }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { deployabilityStatusText, deployabilityStatusType } from '../utils/deployability'
import type { DeployabilityItem } from '../types/deployability'

const props = defineProps<{ item?: DeployabilityItem | null }>()

const statusText = computed(() => deployabilityStatusText(props.item))
const statusClass = computed(() => deployabilityStatusType(props.item))
</script>

<style scoped>
.badge { display:inline-flex; align-items:center; padding:6px 10px; border-radius:999px; font-size:12px; font-weight:600; }
.danger { background:#3f1d24; color:#fda4af; }
.success { background:#123524; color:#86efac; }
.warning { background:#3a2f12; color:#fcd34d; }
</style>
