<template>
  <section class="panel ledger-panel">
    <div class="section-head">
      <div>
        <h2>调仓账本 / Ledger</h2>
        <p class="muted">直接读取后端 reports 接口，展示调仓、逐笔交易、已平仓盈亏、按股票汇总，方便你人工核算收益。</p>
      </div>
      <div class="ledger-controls">
        <label>
          <span>调仓报告 ID</span>
          <input v-model="periodReportIdLocal" placeholder="growth_personal_100k_turnover_v2_1_rebalance_detail_latest" />
        </label>
        <label>
          <span>股票账本报告 ID</span>
          <input v-model="stockLedgerReportIdLocal" placeholder="growth_personal_100k_2024_2026_boardlot_stock_ledger_closed_latest" />
        </label>
        <label>
          <span>股票汇总报告 ID</span>
          <input v-model="stockSummaryReportIdLocal" placeholder="growth_personal_100k_2024_2026_boardlot_stock_summary_closed_latest" />
        </label>
        <button @click="$emit('reload-ledger', periodReportIdLocal, stockLedgerReportIdLocal, stockSummaryReportIdLocal)" :disabled="loading">{{ loading ? '加载中…' : '加载账本' }}</button>
      </div>
    </div>

    <div v-if="error" class="callout danger">
      <strong>账本加载失败</strong>
      <span>{{ error }}</span>
    </div>

    <template v-if="periodReport && stockLedger && stockSummary">
      <div class="summary-grid">
        <div class="stat-card">
          <span class="label">起始本金</span>
          <strong>{{ fmtCurrency(periodReport.summary.aum_start) }}</strong>
        </div>
        <div class="stat-card">
          <span class="label">最终资金</span>
          <strong>{{ fmtCurrency(periodReport.summary.aum_end) }}</strong>
        </div>
        <div class="stat-card">
          <span class="label">总收益率</span>
          <strong>{{ fmtPct(periodReport.summary.total_return_pct) }}</strong>
        </div>
        <div class="stat-card">
          <span class="label">调仓次数</span>
          <strong>{{ periodReport.summary.rebalance_count }}</strong>
        </div>
      </div>

      <div class="subsection">
        <h3>人工核算说明</h3>
        <ul class="muted checklist">
          <li>组合层核算：逐行检查 <code>期末资金 = 期初资金 × (1 + 净收益率)</code>。</li>
          <li>股票层核算：优先看“按股票汇总表”，快速判断每只股票累计赚亏多少。</li>
          <li>如需追溯单笔：先在“按股票汇总表”定位股票，再去“逐笔交易/已平仓盈亏”核细节。</li>
        </ul>
      </div>

      <div class="subsection filters-grid">
        <label>
          <span>股票筛选</span>
          <input v-model="tickerFilter" placeholder="例如 sh600009 / 600009 / 上海机场" />
        </label>
        <label>
          <span>日期筛选</span>
          <input v-model="dateFilter" placeholder="例如 2025-03 或 2025-03-10" />
        </label>
      </div>

      <div class="subsection">
        <h3>按股票汇总表</h3>
        <div class="table-wrap slim">
          <table>
            <thead>
              <tr>
                <th>股票</th>
                <th>股票名称</th>
                <th>累计买入金额</th>
                <th>累计卖出金额</th>
                <th>已实现盈亏</th>
                <th>未实现盈亏</th>
                <th>总盈亏</th>
                <th>当前持仓股数</th>
                <th>当前持仓成本</th>
                <th>最新参考价</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredStockSummary" :key="row.ticker">
                <td>{{ row.ticker }}</td>
                <td>{{ row.name ?? '—' }}</td>
                <td>{{ fmtCurrency(row.buy_notional_total) }}</td>
                <td>{{ fmtCurrency(row.sell_notional_total) }}</td>
                <td>{{ fmtCurrency(row.estimated_realized_pnl_total) }}</td>
                <td>{{ fmtCurrency(row.estimated_unrealized_pnl) }}</td>
                <td :class="row.estimated_total_pnl >= 0 ? 'success-text' : 'danger-text'">{{ fmtCurrency(row.estimated_total_pnl) }}</td>
                <td>{{ fmtNumber(row.latest_estimated_shares_held) }}</td>
                <td>{{ fmtNumber(row.latest_estimated_avg_cost) }}</td>
                <td>{{ fmtNumber(row.latest_reference_price) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="subsection">
        <div class="table-head">
          <h3>调仓列表</h3>
          <label class="compact-filter">
            <span>按日期筛选</span>
            <input v-model="rebalanceDateFilter" placeholder="例如 2025-01 或 2025-01-06" />
          </label>
        </div>
        <div class="table-wrap slim">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>期初资金</th>
                <th>净收益率</th>
                <th>成本</th>
                <th>期末资金</th>
                <th>持仓数</th>
                <th>买入</th>
                <th>卖出</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredRebalances" :key="row.date">
                <td>{{ row.date }}</td>
                <td>{{ fmtCurrency(row.start_equity) }}</td>
                <td>{{ fmtPct(row.net_return_pct) }}</td>
                <td>{{ fmtCurrency(row.cost_cny) }}</td>
                <td>{{ fmtCurrency(row.end_equity) }}</td>
                <td>{{ row.hold_count }}</td>
                <td>{{ row.buy_count }}</td>
                <td>{{ row.sell_count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="subsection">
        <h3>逐笔交易</h3>
        <div class="table-wrap slim">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>股票</th>
                <th>股票名称</th>
                <th>方向</th>
                <th>价格</th>
                <th>股数</th>
                <th>金额</th>
                <th>估算已实现盈亏</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredTrades" :key="`${row.date}-${row.ticker}-${row.side}-${row.price}-${row.shares}`">
                <td>{{ row.date }}</td>
                <td>{{ row.ticker }}</td>
                <td>{{ row.name ?? '—' }}</td>
                <td>{{ row.side }}</td>
                <td>{{ fmtNumber(row.price) }}</td>
                <td>{{ fmtNumber(row.shares) }}</td>
                <td>{{ row.estimated_realized_pnl === '' ? '—' : fmtCurrency(Number(row.estimated_realized_pnl)) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="subsection">
        <h3>已平仓盈亏</h3>
        <div class="table-wrap slim">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>股票</th>
                <th>股票名称</th>
                <th>卖出价</th>
                <th>卖出股数</th>
                <th>均价成本</th>
                <th>估算已实现盈亏</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredClosedTrades" :key="`${row.date}-${row.ticker}-${row.sell_price}-${row.sell_shares}`">
                <td>{{ row.date }}</td>
                <td>{{ row.ticker }}</td>
                <td>{{ row.name ?? '—' }}</td>
                <td>{{ fmtNumber(row.sell_price) }}</td>
                <td>{{ fmtNumber(row.sell_shares) }}</td>
                <td>{{ fmtNumber(row.avg_cost) }}</td>
                <td>{{ fmtCurrency(row.estimated_realized_pnl) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ClosedTradeRow, LedgerPeriodReport, StockLedgerReport, StockTradeRow } from '../types/ledger'
import type { StockSummaryReport, StockSummaryRow } from '../types/stockSummary'

const props = defineProps<{
  periodReport: LedgerPeriodReport | null
  stockLedger: StockLedgerReport | null
  stockSummary: StockSummaryReport | null
  loading: boolean
  error: string | null
  periodReportId: string
  stockLedgerReportId: string
  stockSummaryReportId: string
}>()

const periodReportIdLocal = ref(props.periodReportId)
const stockLedgerReportIdLocal = ref(props.stockLedgerReportId)
const stockSummaryReportIdLocal = ref(props.stockSummaryReportId)
const tickerFilter = ref('')
const dateFilter = ref('')
const rebalanceDateFilter = ref('')

watch(() => props.periodReportId, value => { periodReportIdLocal.value = value })
watch(() => props.stockLedgerReportId, value => { stockLedgerReportIdLocal.value = value })
watch(() => props.stockSummaryReportId, value => { stockSummaryReportIdLocal.value = value })

const filteredRebalances = computed(() => {
  const rows = props.periodReport?.rebalances ?? []
  const q = rebalanceDateFilter.value.trim().toLowerCase()
  if (!q) return rows
  return rows.filter(row => row.date.toLowerCase().includes(q))
})

function rowMatchTickerAndDate(row: { ticker: string; date: string }) {
  const tq = tickerFilter.value.trim().toLowerCase()
  const dq = dateFilter.value.trim().toLowerCase()
  const tickerOk = !tq || row.ticker.toLowerCase().includes(tq)
  const dateOk = !dq || row.date.toLowerCase().includes(dq)
  return tickerOk && dateOk
}

const filteredTrades = computed<StockTradeRow[]>(() => {
  const rows = props.stockLedger?.trades ?? []
  return rows.filter(rowMatchTickerAndDate)
})

const filteredClosedTrades = computed<ClosedTradeRow[]>(() => {
  const rows = props.stockLedger?.closed_trades ?? []
  return rows.filter(rowMatchTickerAndDate)
})

const filteredStockSummary = computed<StockSummaryRow[]>(() => {
  const rows = props.stockSummary?.rows ?? []
  const tq = tickerFilter.value.trim().toLowerCase()
  if (!tq) return rows
  return rows.filter(row => {
    const hay = `${row.ticker} ${row.name ?? ''}`.toLowerCase()
    return hay.includes(tq)
  })
})

function fmtCurrency(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY', maximumFractionDigits: 2 }).format(value)
}

function fmtPct(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '—'
  return `${Number(value).toFixed(4)}%`
}

function fmtNumber(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '—'
  return Number(value).toFixed(4)
}
</script>

<style scoped>
.ledger-panel { display: grid; gap: 18px; }
.section-head { display: grid; gap: 16px; }
.ledger-controls { display: flex; gap: 12px; flex-wrap: wrap; align-items: end; }
.ledger-controls label, .filters-grid label, .compact-filter { display: grid; gap: 8px; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.stat-card { background: #0f172a; border: 1px solid #243042; border-radius: 16px; padding: 14px; }
.subsection { display: grid; gap: 12px; }
.table-head { display: flex; justify-content: space-between; gap: 12px; align-items: end; flex-wrap: wrap; }
.table-wrap { overflow: auto; border: 1px solid #243042; border-radius: 16px; }
.table-wrap.slim { max-height: 460px; }
.filters-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
table { width: 100%; border-collapse: collapse; min-width: 980px; }
th, td { padding: 10px 12px; border-bottom: 1px solid #1f2937; text-align: left; vertical-align: top; font-size: 13px; }
thead th { position: sticky; top: 0; background: #111827; z-index: 1; }
.checklist { margin: 0; padding-left: 18px; }
input, button { background: #111827; border: 1px solid #243042; border-radius: 12px; color: #e5e7eb; padding: 10px 12px; }
button { cursor: pointer; }
</style>
