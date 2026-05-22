<template>
  <section class="panel">
    <div class="header">
      <div>
        <h2>{{ title }}</h2>
        <p class="muted">{{ subtitle }}</p>
      </div>
      <slot name="actions" />
    </div>
    <div class="content">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<style scoped>
.panel { background:#111827; border:1px solid #243042; border-radius:16px; padding:20px; }
.header { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:16px; }
.muted { color:#9ca3af; margin:6px 0 0; }
</style>
