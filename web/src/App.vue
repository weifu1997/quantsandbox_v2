<template>
  <div class="page-shell">
    <header class="hero">
      <div>
        <p class="eyebrow">QuantSandbox / 可部署性治理</p>
        <h1>策略治理与收益核算面板</h1>
        <p class="muted">基于真实 API 的治理状态、容量压力、分配器状态与调仓账本核查页面。</p>
      </div>
      <div class="hero-stats">
        <div class="stat">
          <span class="label">接口状态</span>
          <strong :class="apiError ? 'danger-text' : 'success-text'">{{ apiError ? '异常' : '已连接' }}</strong>
        </div>
        <div class="stat">
          <span class="label">分配器</span>
          <strong :class="statusClass(allocatorBlocked)">{{ allocatorBlocked ? '阻塞' : '可用' }}</strong>
        </div>
      </div>
    </header>

    <!-- Tab 导航 -->
    <nav class="tab-bar">
      <button :class="['tab', { active: activeTab === 'governance' }]" @click="activeTab = 'governance'">治理面板</button>
      <button :class="['tab', { active: activeTab === 'backtest' }]" @click="activeTab = 'backtest'">回测实验</button>
    </nav>

    <div v-if="activeTab === 'governance'">
      <section v-if="apiError" class="panel error-panel">
        <h2>接口错误</h2>
        <p class="muted">{{ apiError }}</p>
      </section>

      <section class="panel controls">
        <div>
          <h2>数据源配置</h2>
          <p class="muted">从 FastAPI 的 reports 接口实时读取治理报告与账本报告。</p>
        </div>
        <div class="control-grid">
          <label>
            <span>决策总结 Report ID</span>
            <input v-model="decisionReportId" placeholder="research_decision_summary_latest" />
          </label>
          <label>
            <span>分配器 Report ID</span>
            <input v-model="allocatorReportId" placeholder="strategy_line_allocator_latest" />
          </label>
          <label>
            <span>账本调仓报告 ID</span>
            <input v-model="ledgerPeriodReportId" placeholder="growth_personal_100k_2024_2026_boardlot_rebalance_detail_latest" />
          </label>
          <label>
            <span>股票账本报告 ID</span>
            <input v-model="ledgerStockReportId" placeholder="growth_personal_100k_turnover_v2_1_stock_ledger_latest" />
          </label>
          <label>
            <span>股票汇总报告 ID</span>
            <input v-model="ledgerStockSummaryReportId" placeholder="growth_personal_100k_turnover_v2_1_stock_summary_latest" />
          </label>
        </div>
        <div class="actions">
          <button @click="reloadAll" :disabled="loading">{{ loading ? '加载中…' : '重新加载全部' }}</button>
        </div>
      </section>

      <main class="grid">
        <section class="panel">
          <h2>研究决策总结</h2>
          <p class="muted">从 <code>/api/reports/{report_id}</code> 读取结构化可部署性字段。</p>
          <div class="cards">
            <DeployabilityCard title="成长线" :item="growth" />
            <DeployabilityCard title="价值主线" :item="valuePrimary" />
            <DeployabilityCard title="价值基线参考" :item="valueBaselineReference" />
          </div>
        </section>

        <section class="panel">
          <h2>分配器 / 组合状态</h2>
          <div class="callout" :class="allocatorBlocked ? 'danger' : 'success'">
            <strong>{{ allocatorBlocked ? '分配器被阻塞' : '分配器可运行' }}</strong>
            <span>{{ allocatorMessage }}</span>
          </div>
          <div class="callout" :class="valueOverlayBlocked ? 'danger' : 'success'">
            <strong>{{ valueOverlayBlocked ? '价值叠加已禁用' : '价值叠加已启用' }}</strong>
            <span>{{ valueOverlayBlocked ? '叠加权重被强制设为 0。' : '允许对价值叠加进行分配。' }}</span>
          </div>
          <div v-if="allocatorStatus" class="allocator-meta">
            <div><span class="label">分配器状态</span><strong>{{ allocatorStatus.status ?? '—' }}</strong></div>
            <div><span class="label">原因</span><strong>{{ allocatorStatus.reason ?? '—' }}</strong></div>
          </div>
        </section>

        <LedgerDashboard
          :period-report="ledgerPeriodReport"
          :stock-ledger="ledgerStockReport"
          :stock-summary="ledgerStockSummaryReport"
          :loading="loading"
          :error="ledgerError"
          :period-report-id="ledgerPeriodReportId"
          :stock-ledger-report-id="ledgerStockReportId"
          :stock-summary-report-id="ledgerStockSummaryReportId"
          @reload-ledger="reloadLedgerOnly"
        />
      </main>
    </div>

    <BacktestPanel v-if="activeTab === 'backtest'" :apiBase="API_BASE" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import DeployabilityCard from './components/DeployabilityCard.vue'
import LedgerDashboard from './components/LedgerDashboard.vue'
import BacktestPanel from './components/BacktestPanel.vue'
import { useDeployability } from './composables/useDeployability'
import type {
  AllocatorStatus,
  DeployabilitySummary,
  ReportApiResponse,
  StrategyLineAllocatorReport,
} from './types/deployability'
import type { LedgerPeriodReport, StockLedgerReport } from './types/ledger'
import type { StockSummaryReport } from './types/stockSummary'

const DEFAULT_DECISION_REPORT_ID = 'research_decision_summary_latest'
const DEFAULT_ALLOCATOR_REPORT_ID = 'strategy_line_allocator_latest'
const DEFAULT_LEDGER_PERIOD_REPORT_ID = 'growth_personal_100k_2024_2026_boardlot_rebalance_detail_latest'
const DEFAULT_LEDGER_STOCK_REPORT_ID = 'growth_personal_100k_2024_2026_boardlot_stock_ledger_closed_latest'
const DEFAULT_LEDGER_STOCK_SUMMARY_REPORT_ID = 'growth_personal_100k_2024_2026_boardlot_stock_summary_closed_latest'
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

const activeTab = ref<'governance' | 'backtest'>('governance')

const decisionReportId = ref(DEFAULT_DECISION_REPORT_ID)
const allocatorReportId = ref(DEFAULT_ALLOCATOR_REPORT_ID)
const ledgerPeriodReportId = ref(DEFAULT_LEDGER_PERIOD_REPORT_ID)
const ledgerStockReportId = ref(DEFAULT_LEDGER_STOCK_REPORT_ID)
const ledgerStockSummaryReportId = ref(DEFAULT_LEDGER_STOCK_SUMMARY_REPORT_ID)
const loading = ref(false)
const apiError = ref<string | null>(null)
const ledgerError = ref<string | null>(null)
const deployabilityRef = ref<DeployabilitySummary | null>(null)
const allocatorStatus = ref<AllocatorStatus | null>(null)
const ledgerPeriodReport = ref<LedgerPeriodReport | null>(null)
const ledgerStockReport = ref<StockLedgerReport | null>(null)
const ledgerStockSummaryReport = ref<StockSummaryReport | null>(null)

async function fetchJson(url: string) {
  const response = await fetch(url)
  const text = await response.text()
  const contentType = response.headers.get('content-type') ?? ''
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${text.slice(0, 120)}`)
  if (!contentType.includes('application/json')) throw new Error(`Non-JSON response from ${url}: ${text.slice(0, 80)}`)
  return JSON.parse(text)
}

async function fetchReport(reportId: string): Promise<ReportApiResponse | null> {
  const data = await fetchJson(`${API_BASE}/api/reports/${reportId}`)
  return data as ReportApiResponse
}

async function reloadCore() {
  const decisionReport = await fetchReport(decisionReportId.value)
  deployabilityRef.value = decisionReport?.deployability ?? null

  const allocatorReport = await fetchReport(allocatorReportId.value)
  const allocatorStructured = allocatorReport?.structured as StrategyLineAllocatorReport | null
  allocatorStatus.value = allocatorStructured?.allocator_status ?? null
}

async function reloadLedger(periodId = ledgerPeriodReportId.value, stockId = ledgerStockReportId.value, stockSummaryId = ledgerStockSummaryReportId.value) {
  ledgerError.value = null
  try {
    const period = await fetchReport(periodId)
    ledgerPeriodReport.value = (period?.structured as LedgerPeriodReport | null) ?? null
    const stock = await fetchReport(stockId)
    ledgerStockReport.value = (stock?.structured as StockLedgerReport | null) ?? null
    const stockSummary = await fetchReport(stockSummaryId)
    ledgerStockSummaryReport.value = (stockSummary?.structured as StockSummaryReport | null) ?? null
    ledgerPeriodReportId.value = periodId
    ledgerStockReportId.value = stockId
    ledgerStockSummaryReportId.value = stockSummaryId
  } catch (error) {
    ledgerError.value = error instanceof Error ? error.message : String(error)
  }
}

async function reloadAll() {
  loading.value = true
  apiError.value = null
  ledgerError.value = null
  try {
    await reloadCore()
    await reloadLedger()
  } catch (error) {
    apiError.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

async function reloadLedgerOnly(periodId: string, stockId: string, stockSummaryId: string) {
  loading.value = true
  await reloadLedger(periodId, stockId, stockSummaryId)
  loading.value = false
}

onMounted(reloadAll)

const { growth, valuePrimary, valueBaselineReference, allocatorBlocked, valueOverlayBlocked } =
  useDeployability(deployabilityRef)

const allocatorMessage = computed(() => {
  if (allocatorStatus.value?.reason) {
    return allocatorStatus.value.reason
  }
  return allocatorBlocked.value
    ? '成长核心策略被 deployability schema 判定为 deployment_blocked。'
    : '分配器可以运行。'
})

function statusClass(blocked: boolean) {
  return blocked ? 'danger-text' : 'success-text'
}
</script>

<style scoped>
:global(body) { margin: 0; font-family: Inter, system-ui, sans-serif; background: #0b1020; color: #e5e7eb; }
:global(code) { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.page-shell { max-width: 1380px; margin: 0 auto; padding: 32px; }
.hero { display: flex; justify-content: space-between; gap: 24px; align-items: end; margin-bottom: 24px; }
.eyebrow { text-transform: uppercase; letter-spacing: .12em; color: #93c5fd; font-size: 12px; }
h1, h2 { margin: 0 0 8px; }
.muted { color: #9ca3af; }
.hero-stats, .control-grid, .allocator-meta { display: flex; gap: 12px; flex-wrap: wrap; }
.stat, .panel, .callout, input, button { background: #111827; border: 1px solid #243042; border-radius: 16px; }
.stat, .panel, .callout { padding: 16px; }
.label { display: block; color: #9ca3af; font-size: 12px; margin-bottom: 6px; }
.grid { display: grid; gap: 16px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
.callout { display: flex; flex-direction: column; gap: 4px; margin-top: 12px; }
.danger { border-color: #7f1d1d; background: #1f0f14; }
.success { border-color: #14532d; background: #0d1f17; }
.error-panel { border-color: #7f1d1d; }
.danger-text { color: #f87171; }
.success-text { color: #86efac; }
.controls { display: grid; gap: 16px; margin-bottom: 16px; }
.control-grid label { display: grid; gap: 8px; min-width: 280px; }
input { color: #e5e7eb; padding: 12px 14px; outline: none; }
button { color: #e5e7eb; padding: 12px 18px; cursor: pointer; }
.actions { display: flex; justify-content: flex-end; }
.allocator-meta > div { min-width: 260px; }
.tab-bar { display: flex; gap: 4px; margin-bottom: 16px; background: #111827; border: 1px solid #243042; border-radius: 16px; padding: 4px; }
.tab { flex: 1; background: transparent; border: none; border-radius: 12px; color: #9ca3af; padding: 10px 16px; cursor: pointer; font-size: 14px; }
.tab.active { background: #1e3a5f; color: #93c5fd; }
.tab:hover:not(.active) { background: #1f2937; }
@media (max-width: 800px) { .hero { flex-direction: column; align-items: start; } .actions { justify-content: start; } }
</style>
