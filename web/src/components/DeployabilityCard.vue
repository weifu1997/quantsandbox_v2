<template>
  <article class="card" :class="blockedClass">
    <div class="top-row">
      <div>
        <h3>{{ title }}</h3>
        <p class="muted">{{ vm.blockedText }}</p>
      </div>
      <DeployabilityBadge :item="item" />
    </div>

    <dl class="grid">
      <div><dt>是否阻塞部署</dt><dd>{{ vm.blocked === null ? '未知' : vm.blocked ? '是' : '否' }}</dd></div>
      <div><dt>建议最大资金档</dt><dd>{{ vm.recommendedMaxAum }}</dd></div>
      <div><dt>首次进入极端压力档</dt><dd>{{ vm.firstExtremeAum }}</dd></div>
      <div><dt>可部署资金下限</dt><dd>{{ vm.deployableAumFloor }}</dd></div>
      <div><dt>首次进入轻压力档</dt><dd>{{ vm.firstLightAum }}</dd></div>
      <div><dt>首次进入重压力档</dt><dd>{{ vm.firstHeavyAum }}</dd></div>
    </dl>

    <div v-if="vm.blockingReasons.length" class="reasons">
      <strong>阻塞原因</strong>
      <ul>
        <li v-for="reason in vm.blockingReasons" :key="reason">{{ reason }}</li>
      </ul>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DeployabilityBadge from './DeployabilityBadge.vue'
import type { DeployabilityItem } from '../types/deployability'
import { toDeployabilityViewModel } from '../utils/deployability'

const props = defineProps<{ title: string; item?: DeployabilityItem | null }>()
const vm = computed(() => toDeployabilityViewModel(props.title, props.item))
const blockedClass = computed(() => (vm.value.blocked ? 'blocked' : 'open'))
</script>

<style scoped>
.card { border:1px solid #243042; border-radius:16px; padding:16px; background:#0f172a; }
.blocked { box-shadow: inset 0 0 0 1px rgba(248,113,113,.15); }
.open { box-shadow: inset 0 0 0 1px rgba(134,239,172,.12); }
.top-row { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
.muted { color:#94a3b8; margin:4px 0 0; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:10px 16px; margin:16px 0 0; }
dt { font-size:12px; color:#94a3b8; }
dd { margin:4px 0 0; font-weight:600; }
.reasons { margin-top:14px; }
ul { margin:8px 0 0 16px; color:#fecaca; }
</style>
