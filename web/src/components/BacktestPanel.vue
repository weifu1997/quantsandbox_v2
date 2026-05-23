<template>
  <div class="backtest-panel">
    <!-- 生产配置回测 -->
    <div class="panel-section">
      <div class="section-header">
        <h3 class="section-title">生产配置回测</h3>
        <span class="badge-row">
          <span class="config-badge clickable" @click="fetchTickers()">
            📋 选股池 <span class="badge-detail">{{ tickerCount }}只</span>
          </span>
          <span class="config-badge clickable" @click="toggleWeighting()">
            ⚖️ 权重 <span class="badge-detail">liquidity_tilted_score</span>
          </span>
          <span class="config-badge">📊 策略 <span class="badge-detail">revenue_growth</span></span>
          <span class="config-badge">🔄 换手 <span class="badge-detail">3x/年</span></span>
          <span class="config-badge">📏 一手约束 <span class="badge-detail">是</span></span>
          <span class="config-badge">🏦 AUM <span class="badge-detail">¥100,000</span></span>
        </span>
      </div>
      <p class="section-desc">提交后将使用 production 批准的正式配置运行回测，完整参数将在结果中展示。</p>
    </div>

    <!-- 回测窗口 + 提交 -->
    <div class="panel-section">
      <div class="date-submit-row">
        <div class="date-input-group">
          <label>起始日期</label>
          <input v-model="backtestConfig.startDate" type="text" placeholder="YYYYMMDD" class="date-input" />
        </div>
        <div class="date-input-group">
          <label>结束日期</label>
          <input v-model="backtestConfig.endDate" type="text" placeholder="YYYYMMDD" class="date-input" />
        </div>
        <button class="submit-btn" @click="submitExperiment" :disabled="submitting">
          {{ submitting ? '运行中...' : '提交回测' }}
        </button>
      </div>
      <div v-if="submitting" class="progress-bar-container">
        <div class="progress-bar" :style="{ width: progressPercent + '%' }"></div>
        <span class="progress-text">{{ progressStatus }}</span>
      </div>
    </div>

    <!-- 回测记录 -->
    <div class="panel-section">
      <div class="section-header">
        <h3 class="section-title">回测记录</h3>
        <span class="section-desc">后端返回的最近回测/实验记录，点击可恢复查看结果。</span>
      </div>
      <div v-if="historyError" class="empty-text">{{ historyError }}</div>
      <div v-else-if="historyItems.length === 0" class="empty-text">暂无回测记录</div>
      <div v-else class="history-list history-scroll-window">
        <div
          v-for="item in historyItems"
          :key="item.experiment_id"
          class="history-item"
        >
          <button
            class="history-item-main"
            @click="loadHistoryItem(item)"
          >
            <div class="history-item-head">
              <span class="history-date">{{ item.start_date }} ~ {{ item.end_date }}</span>
              <span class="history-status" :class="statusClass(item.status)">{{ item.status }}</span>
            </div>
            <div class="history-meta">
              <span>因子：{{ (item.factors || []).join(', ') || '-' }}</span>
              <span>权重：{{ item.weighting || '-' }}</span>
              <span>TopN：{{ item.top_n ?? '-' }}</span>
            </div>
            <div class="history-meta subtle">
              <span>experiment_id: {{ item.experiment_id }}</span>
              <span>report_id: {{ item.report_id || '-' }}</span>
            </div>
          </button>
          <button
            class="history-delete-btn"
            :disabled="deletingExperimentIds[item.experiment_id]"
            @click="deleteHistoryItem(item)"
          >
            {{ deletingExperimentIds[item.experiment_id] ? '删除中...' : '删除' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 回测结果 -->
    <div v-if="hasResult" class="panel-section">
      <div class="ledger-header">
        <span class="ledger-title">revenue_growth</span>
        <span class="ledger-subtitle">Backtest Ledger</span>
      </div>

      <!-- 核心三列 -->
      <div class="summary-cards">
        <div class="summary-card">
          <div class="summary-label">Starting Capital</div>
          <div class="summary-value">¥100,000</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">Final Equity</div>
          <div class="summary-value">¥{{ equityFinal }}</div>
        </div>
        <div class="summary-card highlight">
          <div class="summary-label">Total Return</div>
          <div class="summary-value" :class="totalReturnPct >= 0 ? 'green' : 'red'">{{ totalReturnStr }}</div>
        </div>
      </div>

      <!-- 辅助指标 -->
      <div class="metrics-row">
        <div class="metric-item"><span class="m-label">净收益</span><span class="m-value green">¥{{ profitStr }}</span></div>
        <div class="metric-item"><span class="m-label">夏普</span><span class="m-value">{{ sharpeStr }}</span></div>
        <div class="metric-item"><span class="m-label">最大回撤</span><span class="m-value red">{{ ddStr }}</span></div>
        <div class="metric-item"><span class="m-label">调仓次数</span><span class="m-value">{{ periodCount }}</span></div>
        <div class="metric-item"><span class="m-label">胜率</span><span class="m-value">{{ winRateStr }}</span></div>
        <div class="metric-item"><span class="m-label">年化换手</span><span class="m-value">{{ turnoverStr }}</span></div>
      </div>

      <!-- 调仓明细表 -->
      <div v-if="sortedDates.length > 0" class="table-wrap">
        <h4 class="table-title">调仓明细</h4>
        <table class="data-table">
          <thead>
            <tr>
              <th @click="toggleSort('date')" class="sort-th">日期 {{ sortIcon('date') }}</th>
              <th @click="toggleSort('ret')" class="sort-th">收益率 {{ sortIcon('ret') }}</th>
              <th>持仓数</th>
              <th>前3只</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(date, idx) in pageDates" :key="date">
              <tr>
                <td class="cell-date">{{ date }}</td>
                <td>
                  <div class="ret-cell">
                    <div class="ret-bar" :style="{ width: barWidth(retMap[date]) + '%', background: retMap[date] >= 0 ? '#4caf50' : '#f44336' }"></div>
                    <span :class="retMap[date] >= 0 ? 'green' : 'red'">{{ pctStr(retMap[date]) }}</span>
                  </div>
                </td>
                <td>{{ (holdingsMap[date] || []).length }}</td>
                <td>
                  <span v-for="t in (holdingsMap[date] || []).slice(0,3)" :key="t" class="ticker-tag">{{ t }}</span>
                </td>
                <td>
                  <button class="expand-btn" @click="toggleExpand(date)">{{ expandState[date] ? '收起' : '展开' }}</button>
                </td>
              </tr>
              <tr v-if="expandState[date]">
                <td colspan="5" class="detail-cell">
                  <div v-if="posMap[date] && Object.keys(posMap[date]).length" class="pos-table-wrap">
                    <table class="pos-table">
                      <thead><tr><th>Ticker</th><th>名称</th><th>权重</th><th>价格</th><th>股数</th><th>市值</th></tr></thead>
                      <tbody>
                        <tr v-for="(detail, ticker) in posMap[date]" :key="ticker">
                          <td class="ticker-cell">{{ ticker }}</td>
                          <td class="name-cell">{{ stockNameMap[ticker] || '-' }}</td>
                          <td>{{ pctStr(detail.weight) }}</td>
                          <td>{{ numStr(detail.price) }}</td>
                          <td>{{ detail.shares }}</td>
                          <td>¥{{ numStr(detail.actual_notional || detail.shares * detail.price) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div v-else class="empty-text">无持仓明细</div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <div v-if="totalPages > 1" class="pagination">
          <button class="page-btn" :disabled="page === 1" @click="page--">‹ 上一页</button>
          <span class="page-info">{{ page }} / {{ totalPages }}</span>
          <button class="page-btn" :disabled="page === totalPages" @click="page++">下一页 ›</button>
        </div>
      </div>
    </div>

    <!-- 实际运行配置 -->
    <div v-if="hasResult && growthConfig" class="panel-section">
      <h3 class="section-title" style="margin-bottom:12px;">实际运行配置</h3>
      <div class="config-grid">
        <div class="cfg-item"><span class="cfg-label">因子</span><span class="cfg-val">{{ growthConfig.factor_name || 'revenue_growth_raw' }}</span></div>
        <div class="cfg-item"><span class="cfg-label">选股池</span><span class="cfg-val">{{ growthConfig.universe_name || 'amount_bottom_50pct' }}（{{ tickerCount }}只）</span></div>
        <div class="cfg-item"><span class="cfg-label">权重策略</span><span class="cfg-val">{{ growthConfig.weighting_policy || 'liquidity_tilted_score' }}</span></div>
        <div class="cfg-item"><span class="cfg-label">目标AUM</span><span class="cfg-val">¥100,000</span></div>
        <div class="cfg-item"><span class="cfg-label">持仓数量</span><span class="cfg-val">{{ growthConfig.top_n || 20 }}</span></div>
        <div class="cfg-item"><span class="cfg-label">年化换手上限</span><span class="cfg-val">{{ growthConfig.annual_turnover_limit || 3.0 }}x</span></div>
        <div class="cfg-item"><span class="cfg-label">调仓频率</span><span class="cfg-val">{{ growthConfig.rebalance_frequency || '每周' }}</span></div>
        <div class="cfg-item"><span class="cfg-label">佣金</span><span class="cfg-val">{{ growthConfig.commission_bps || 10 }} bps</span></div>
        <div class="cfg-item"><span class="cfg-label">收益窗口</span><span class="cfg-val">{{ growthConfig.horizon || 10 }}天</span></div>
        <div class="cfg-item"><span class="cfg-label">滑点</span><span class="cfg-val">{{ growthConfig.slippage_bps || 5 }} bps</span></div>
        <div class="cfg-item"><span class="cfg-label">一手约束</span><span class="cfg-val">{{ growthConfig.board_lot_enabled ? '是' : '否' }}</span></div>
        <div class="cfg-item"><span class="cfg-label">执行延迟</span><span class="cfg-val">{{ growthConfig.bar_delay || 1 }} bar</span></div>
      </div>
    </div>

    <!-- 选股池浮层 -->
    <div v-if="showTickerModal" class="modal-overlay" @click.self="showTickerModal = false">
      <div class="modal-box">
        <div class="modal-head">
          <h3>选股池（{{ tickerCount }}只）</h3>
          <button class="modal-x" @click="showTickerModal = false">✕</button>
        </div>
        <div class="ticker-grid">
          <span v-for="t in tickerList" :key="t" class="ticker-chip">{{ t }}</span>
        </div>
      </div>
    </div>

    <!-- 权重计算浮层 -->
    <div v-if="showWeightModal" class="modal-overlay" @click.self="showWeightModal = false">
      <div class="modal-box">
        <div class="modal-head">
          <h3>权重计算 — liquidity_tilted_score</h3>
          <button class="modal-x" @click="showWeightModal = false">✕</button>
        </div>
        <div class="steps">
          <div class="step">
            <div class="step-num">1</div>
            <div><strong>估值分（因子分）</strong><p>选股池按 revenue_growth 降序，取 Top N（默认20只）。</p><code>rank_score = (max_z - z) / (max_z - min_z)</code></div>
          </div>
          <div class="step">
            <div class="step-num">2</div>
            <div><strong>流动性偏转</strong><p>用近20日均成交额对数作流动性评分，与原评分加权平均 α=0.7。</p><code>final_score = α×rank_score + (1-α)×liquidity_score</code></div>
          </div>
          <div class="step">
            <div class="step-num">3</div>
            <div><strong>归一化配权重</strong><p>Softmax 归一化。</p><code>weight_i = e^{score_i} / Σe^{score_j}</code></div>
          </div>
          <div class="step">
            <div class="step-num">4</div>
            <div><strong>换手率 + 一手约束</strong><p>每期允许换手 = 3.0/52≈5.77%。股数向下取整为100的倍数。</p></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'

const API_BASE = ''

const submitting = ref(false)
const progressPercent = ref(0)
const progressStatus = ref('')
const taskId = ref(null)
const experimentId = ref(null)
const reportId = ref(null)
const hasResult = ref(false)

const growthConfig = ref(null)
const tickerList = ref([])
const tickerCount = ref(500)
const showTickerModal = ref(false)
const showWeightModal = ref(false)

const stockNameMap = ref({})
const historyItems = ref([])
const historyError = ref('')
const deletingExperimentIds = ref({})

// Core data from report
const totalReturn = ref(0)
const annualReturn = ref(0)
const sharpe = ref(0)
const maxDrawdown = ref(0)
const winRate = ref(0)
const turnover = ref(0)
const equityCurve = ref([])
const retMap = ref({})
const holdingsMap = ref({})
const posMap = ref({})
const sortedDates = ref([])

// UI state
const page = ref(1)
const pageSize = 10
const expandState = ref({})
const sortField = ref('date')
const sortAsc = ref(false)

const backtestConfig = reactive({
  startDate: '20240102',
  endDate: '20260520',
})

// Computed
const periodCount = computed(() => sortedDates.value.length)
const totalPages = computed(() => Math.ceil(sortedDates.value.length / pageSize) || 1)

const pageDates = computed(() => {
  let list = [...sortedDates.value]
  if (sortField.value === 'date') {
    list.sort((a, b) => sortAsc.value ? a.localeCompare(b) : b.localeCompare(a))
  } else if (sortField.value === 'ret') {
    list.sort((a, b) => sortAsc.value ? (retMap.value[a] || 0) - (retMap.value[b] || 0) : (retMap.value[b] || 0) - (retMap.value[a] || 0))
  }
  const start = (page.value - 1) * pageSize
  return list.slice(start, start + pageSize)
})

const totalReturnPct = computed(() => totalReturn.value * 100)
const totalReturnStr = computed(() => (totalReturn.value >= 0 ? '+' : '') + (totalReturn.value * 100).toFixed(2) + '%')
const equityFinal = computed(() => {
  const eq = equityCurve.value
  if (eq && eq.length) return Math.round(eq[eq.length - 1] * 100000).toLocaleString()
  return (100000 * (1 + totalReturn.value)).toFixed(0)
})
const profitStr = computed(() => {
  const p = (totalReturn.value * 100000)
  return Math.round(p).toLocaleString()
})
const sharpeStr = computed(() => sharpe.value.toFixed(2))
const ddStr = computed(() => (maxDrawdown.value * 100).toFixed(2) + '%')
const winRateStr = computed(() => (winRate.value * 100).toFixed(2) + '%')
const turnoverStr = computed(() => (turnover.value * 100).toFixed(2) + '%')

function pctStr(v) {
  if (v === null || v === undefined || isNaN(v)) return '0%'
  return (v * 100).toFixed(2) + '%'
}

function numStr(v) {
  if (v === null || v === undefined || isNaN(v)) return '0'
  return Number(v).toFixed(2)
}

function barWidth(v) {
  return Math.min(Math.abs(v || 0) * 500, 100)
}

function sortIcon(field) {
  if (sortField.value !== field) return ''
  return sortAsc.value ? '↑' : '↓'
}

function toggleSort(field) {
  if (sortField.value === field) {
    sortAsc.value = !sortAsc.value
  } else {
    sortField.value = field
    sortAsc.value = false
  }
}

function toggleExpand(date) {
  if (expandState.value[date]) {
    expandState.value[date] = false
  } else {
    expandState.value[date] = true
  }
}

function toggleWeighting() {
  showWeightModal.value = !showWeightModal.value
}

function statusClass(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'completed' || s === 'success') return 'green'
  if (s === 'failed' || s === 'error' || s === 'interrupted') return 'red'
  return ''
}

async function fetchTickers() {
  if (tickerList.value.length > 0) {
    showTickerModal.value = true
    return
  }
  // Try from growthConfig first
  if (growthConfig.value && growthConfig.value.tickers) {
    tickerList.value = growthConfig.value.tickers
    tickerCount.value = tickerList.value.length
    showTickerModal.value = true
    return
  }
  // Fallback: fetch from API
  try {
    const resp = await fetch(API_BASE + '/api/experiments/tickers')
    const json = await resp.json()
    const list = json?.data?.tickers || json?.tickers || []
    tickerList.value = list
    tickerCount.value = list.length
    showTickerModal.value = true
  } catch (e) {
    console.error('Failed to fetch tickers:', e)
    showTickerModal.value = true
  }
}

function calcWeights(date) {
  const pos = posMap.value[date]
  if (!pos) return {}
  const keys = Object.keys(pos)
  const totalNotional = keys.reduce((s, k) => s + (pos[k].actual_notional || pos[k].shares * pos[k].price || 0), 0)
  const result = {}
  for (const k of keys) {
    const n = pos[k].actual_notional || pos[k].shares * pos[k].price || 0
    result[k] = { ...pos[k], weight: totalNotional > 0 ? n / totalNotional : 0 }
  }
  return result
}

async function submitExperiment() {
  submitting.value = true
  progressPercent.value = 10
  progressStatus.value = '提交中...'

  try {
    const resp = await fetch(API_BASE + '/api/experiments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_date: backtestConfig.startDate,
        end_date: backtestConfig.endDate,
        universe: 'expanded_main_board_1000',
        factors: ['revenue_growth'],
        rebalance_frequency: 'W',
        top_n: 20,
        weighting: 'liquidity_tilted_score',
        commission_bps: 10,
        slippage_bps: 5,
        horizons: [10],
        annual_turnover_limit: 3.0,
        initial_aum: 100000,
        board_lot_enabled: true,
        board_lot_size: 100,
        execution_assumptions: { bar_delay: 1, min_tick: 0.01 }
      }),
    })
    const json = await resp.json()
    if (!resp.ok) {
      progressStatus.value = '提交失败: ' + (json.detail || 'unknown error')
      submitting.value = false
      return
    }
    experimentId.value = json.data?.experiment?.id || json.experiment_id
    taskId.value = json.data?.task?.task_id || json.task_id
    if (!taskId.value) {
      progressStatus.value = '提交失败: 未返回 task_id'
      submitting.value = false
      return
    }
    progressPercent.value = 20
    progressStatus.value = '任务已提交...'
    startPolling()
  } catch (e) {
    progressStatus.value = '提交失败: ' + e.message
    submitting.value = false
  }
}

function startPolling() {
  if (!taskId.value) return
  progressPercent.value = 30
  progressStatus.value = '执行中...'
  const interval = setInterval(async () => {
    try {
      const resp = await fetch(API_BASE + `/api/tasks/${taskId.value}`)
      const json = await resp.json()
      if (!resp.ok) {
        clearInterval(interval)
        progressStatus.value = '查询失败'
        submitting.value = false
        return
      }
      const td = json.data || json
      const status = String(td.status || td.task_status || '').toLowerCase()
      if (status === 'completed' || status === 'success') {
        clearInterval(interval)
        progressPercent.value = 100
        progressStatus.value = '回测完成！'
        submitting.value = false
        const resultRef = td.result?.result_ref || td.result_ref
        reportId.value = resultRef
        if (reportId.value) {
          await fetchResult(reportId.value)
        }
        await fetchHistory()
      } else if (status === 'failed' || status === 'error' || status === 'interrupted') {
        clearInterval(interval)
        progressStatus.value = '回测失败: ' + (td.result?.error || td.error || '未知错误')
        submitting.value = false
      } else {
        progressPercent.value = Math.min(progressPercent.value + 2, 95)
      }
    } catch (e) {}
  }, 2000)
}

async function fetchResult(rid) {
  try {
    const resp = await fetch(API_BASE + `/api/reports/${rid}`)
    const json = await resp.json()
    if (!resp.ok) return
    const payload = json.data || json
    const report = payload.structured || payload

    // Navigate: backtest_results.revenue_growth
    let bt = report
    if (bt.backtest_results) {
      const keys = Object.keys(bt.backtest_results)
      if (keys.length > 0) {
        bt = bt.backtest_results[keys[0]]
      }
    }

    // Extract metrics
    totalReturn.value = bt.total_return || 0
    annualReturn.value = bt.annual_return || 0
    sharpe.value = bt.sharpe || 0
    maxDrawdown.value = bt.max_drawdown || 0
    winRate.value = bt.win_rate || 0
    turnover.value = bt.annualized_one_way_turnover || 0
    equityCurve.value = bt.equity_curve || []

    // Period returns: {"2024-01-02": -0.00049, ...}
    const returns = bt.returns_by_rebalance_date || {}
    const holdings = bt.holdings_by_rebalance_date || {}
    const positions = bt.position_details_by_rebalance_date || {}

    retMap.value = returns
    holdingsMap.value = holdings
    posMap.value = positions
    sortedDates.value = Object.keys(returns).sort()

    // Compute weights for each period's positions
    for (const date of sortedDates.value) {
      if (posMap.value[date]) {
        const pos = posMap.value[date]
        const keys = Object.keys(pos)
        const totalNotional = keys.reduce((s, k) => {
          const p = pos[k]
          return s + (p.actual_notional || p.shares * p.price || 0)
        }, 0)
        for (const k of keys) {
          const n = pos[k].actual_notional || pos[k].shares * pos[k].price || 0
          posMap.value[date][k].weight = totalNotional > 0 ? n / totalNotional : 0
        }
      }
    }

    // Ticker list from growthConfig
    const gc = bt._growth_config || report._growthConfig
    if (gc) {
      growthConfig.value = gc
      if (gc.tickers && Array.isArray(gc.tickers)) {
        tickerList.value = gc.tickers
        tickerCount.value = gc.tickers.length
      } else if (gc.tickers_used) {
        tickerCount.value = gc.tickers_used
      }
    }

    hasResult.value = true
  } catch (e) {
    console.error('fetchResult error:', e)
  }
}

async function fetchHistory() {
  historyError.value = ''
  try {
    const resp = await fetch(API_BASE + '/api/experiments/history?limit=20')
    const json = await resp.json()
    if (!resp.ok) {
      historyError.value = json?.detail || '回测记录加载失败'
      return
    }
    historyItems.value = json?.data?.items || []
  } catch (e) {
    historyError.value = '回测记录加载失败'
  }
}

async function loadHistoryItem(item) {
  backtestConfig.startDate = item.start_date || backtestConfig.startDate
  backtestConfig.endDate = item.end_date || backtestConfig.endDate
  experimentId.value = item.experiment_id || null
  taskId.value = item.task_id || null
  reportId.value = item.report_id || item.result_ref || null
  if (reportId.value) {
    await fetchResult(reportId.value)
  }
}

async function deleteHistoryItem(item) {
  const experimentIdToDelete = item?.experiment_id
  if (!experimentIdToDelete) return

  const confirmed = window.confirm(`确认删除这条回测记录吗？\n\nexperiment_id: ${experimentIdToDelete}\n\n这会同时删除后端数据库中的 experiment/task/report 记录及相关生成文件。`)
  if (!confirmed) return

  deletingExperimentIds.value = {
    ...deletingExperimentIds.value,
    [experimentIdToDelete]: true,
  }

  try {
    const resp = await fetch(API_BASE + `/api/experiments/${experimentIdToDelete}`, {
      method: 'DELETE',
    })
    const json = await resp.json()
    if (!resp.ok) {
      window.alert(json?.detail || '删除失败')
      return
    }

    historyItems.value = historyItems.value.filter((historyItem) => historyItem.experiment_id !== experimentIdToDelete)

    if (experimentId.value === experimentIdToDelete) {
      experimentId.value = null
      taskId.value = null
      reportId.value = null
      hasResult.value = false
      progressPercent.value = 0
      progressStatus.value = ''
    }

    await fetchHistory()
  } catch (e) {
    window.alert('删除失败')
  } finally {
    deletingExperimentIds.value = {
      ...deletingExperimentIds.value,
      [experimentIdToDelete]: false,
    }
  }
}
onMounted(async () => {
  await fetchHistory()

  const latestHistoryItem = historyItems.value?.[0]
  const latestStatus = String(latestHistoryItem?.status || '').toLowerCase()
  if (latestHistoryItem?.task_id && ['pending', 'queued', 'running'].includes(latestStatus)) {
    experimentId.value = latestHistoryItem.experiment_id || null
    taskId.value = latestHistoryItem.task_id || null
    reportId.value = latestHistoryItem.report_id || latestHistoryItem.result_ref || null
    submitting.value = true
    progressPercent.value = 30
    progressStatus.value = '执行中...'
    startPolling()
  }

  // Try to restore latest report on page load
  try {
    const resp = await fetch(API_BASE + '/api/experiments/latest/report')
    if (resp.ok) {
      const json = await resp.json()
      const rid = json?.data?.report_id || json?.report_id
      if (rid) {
        reportId.value = rid
        await fetchResult(rid)
      }
    }
  } catch (e) {
    // Silently fail - no prior result to restore
  }

  // Fetch stock names for holdings display
  try {
    const resp = await fetch(API_BASE + '/api/experiments/stock-names')
    if (resp.ok) {
      const json = await resp.json()
      stockNameMap.value = json?.data || {}
    }
  } catch (e) {}
})
</script>

<style scoped>
.backtest-panel {
  max-width: 1380px;
  width: 100%;
  margin: 0 auto;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  box-sizing: border-box;
  background: #111827;
  border-radius: 16px;
  padding: 20px;
}

.panel-section {
  background: #111827;
  border: 1px solid #2a2a4a;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  box-sizing: border-box;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #e0e0f0;
  margin: 0;
}

.section-desc {
  font-size: 13px;
  color: #888;
  margin: 4px 0 0 0;
}

.badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.config-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  padding: 3px 10px;
  background: #16213e;
  border: 1px solid #2a2a4a;
  border-radius: 20px;
  color: #e0e0f0;
  white-space: nowrap;
}

.config-badge.clickable {
  cursor: pointer;
  border-color: #4a6fa5;
  color: #7eb8ff;
}
.config-badge.clickable:hover {
  background: #1a2a4a;
}

.badge-detail {
  font-size: 10px;
  color: #888;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.history-scroll-window {
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}

.history-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 72px;
  gap: 12px;
  align-items: stretch;
  width: 100%;
}

.history-item-main {
  min-width: 0;
  width: 100%;
  text-align: left;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid #2a2a4a;
  background: #0f0f23;
  color: #e0e0f0;
  cursor: pointer;
}

.history-item-main:hover {
  background: #16213e;
}

.history-delete-btn {
  width: 72px;
  min-width: 72px;
  border: 1px solid #7f1d1d;
  background: #2b1114;
  color: #fca5a5;
  border-radius: 8px;
  cursor: pointer;
}

.history-delete-btn:hover {
  background: #3f151a;
}

.history-delete-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.history-item-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.history-date {
  font-size: 13px;
  font-weight: 600;
}

.history-status {
  font-size: 12px;
  font-weight: 600;
}

.history-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: #b7bfd6;
}

.history-meta.subtle {
  margin-top: 4px;
  font-size: 11px;
  color: #888;
}

.history-status.green { color: #4caf50; }
.history-status.red { color: #f44336; }

.date-submit-row {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
}

.date-input-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.date-input-group label {
  font-size: 12px;
  color: #888;
}

.date-input {
  padding: 8px 12px;
  border: 1px solid #2a2a4a;
  border-radius: 6px;
  background: #0f0f23;
  color: #e0e0f0;
  font-size: 14px;
  width: 120px;
  outline: none;
}
.date-input:focus {
  border-color: #4a6fa5;
}

.submit-btn {
  padding: 8px 24px;
  background: #4a6fa5;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}
.submit-btn:hover:not(:disabled) {
  background: #5a7fb5;
}
.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.progress-bar-container {
  margin-top: 12px;
  height: 24px;
  background: #16213e;
  border-radius: 12px;
  position: relative;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #4a6fa5, #6a9fc5);
  border-radius: 12px;
  transition: width 0.5s;
}
.progress-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 12px;
  color: #e0e0f0;
}

.ledger-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.ledger-title {
  font-size: 18px;
  font-weight: 700;
  color: #e0e0f0;
}
.ledger-subtitle {
  font-size: 13px;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.summary-cards {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}
.summary-card {
  flex: 1;
  background: #16213e;
  border-radius: 10px;
  padding: 16px;
  text-align: center;
}
.summary-card.highlight {
  background: #1a2a1e;
  border: 1px solid #2a5a2a;
}
.summary-label {
  font-size: 11px;
  color: #888;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.summary-value {
  font-size: 20px;
  font-weight: 700;
  color: #e0e0f0;
}
.summary-value.green { color: #4caf50; }
.summary-value.red { color: #f44336; }

.metrics-row {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.metric-item {
  flex: 1;
  min-width: 90px;
  background: #0f0f23;
  border: 1px solid #2a2a4a;
  border-radius: 8px;
  padding: 10px 8px;
  text-align: center;
}
.m-label {
  display: block;
  font-size: 10px;
  color: #888;
  margin-bottom: 2px;
}
.m-value {
  font-size: 15px;
  font-weight: 600;
  color: #e0e0f0;
}
.m-value.green { color: #4caf50; }
.m-value.red { color: #f44336; }

.table-wrap {
  margin-top: 16px;
}
.table-title {
  font-size: 14px;
  font-weight: 600;
  color: #e0e0f0;
  margin-bottom: 12px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}
.data-table th {
  font-size: 11px;
  color: #888;
  text-align: left;
  padding: 8px 6px;
  border-bottom: 1px solid #2a2a4a;
  white-space: nowrap;
}
.sort-th {
  cursor: pointer;
  user-select: none;
}
.sort-th:hover { color: #e0e0f0; }
.data-table td {
  padding: 8px 6px;
  border-bottom: 1px solid #2a2a4a;
  font-size: 13px;
  color: #e0e0f0;
}
.cell-date { font-family: monospace; white-space: nowrap; width: 120px; }

.ret-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ret-bar {
  height: 8px;
  border-radius: 4px;
  min-width: 3px;
  flex-shrink: 0;
  max-width: 80%;
}
.green { color: #4caf50; }
.red { color: #f44336; }

.ticker-tag {
  display: inline-block;
  padding: 1px 5px;
  margin: 1px;
  font-size: 10px;
  font-family: monospace;
  background: #16213e;
  border-radius: 3px;
  color: #aaa;
}

.expand-btn {
  padding: 3px 10px;
  font-size: 11px;
  background: transparent;
  border: 1px solid #2a2a4a;
  border-radius: 4px;
  color: #e0e0f0;
  cursor: pointer;
}
.expand-btn:hover { background: #16213e; }

.detail-cell {
  padding: 16px !important;
  background: #0f0f23;
}
.pos-table-wrap {
  max-height: 280px;
  overflow-y: auto;
}
.pos-table {
  width: 100%;
  border-collapse: collapse;
}
.pos-table th {
  font-size: 10px;
  color: #888;
  text-align: left;
  padding: 5px 8px;
  border-bottom: 1px solid #2a2a4a;
}
.pos-table td {
  padding: 5px 8px;
  font-size: 12px;
  border-bottom: 1px solid #2a2a4a;
}
.ticker-cell { font-family: monospace; font-weight: 600; }
.name-cell { font-size: 12px; color: #aaa; white-space: nowrap; }
.empty-text {
  text-align: center;
  color: #888;
  padding: 20px;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 16px;
}
.page-btn {
  padding: 5px 14px;
  background: #16213e;
  border: 1px solid #2a2a4a;
  border-radius: 6px;
  color: #e0e0f0;
  font-size: 12px;
  cursor: pointer;
}
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.page-btn:hover:not(:disabled) { background: #4a6fa5; }
.page-info { font-size: 12px; color: #888; }

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 8px;
}
.cfg-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px;
  background: #0f0f23;
  border: 1px solid #2a2a4a;
  border-radius: 6px;
}
.cfg-label { font-size: 10px; color: #888; }
.cfg-val { font-size: 13px; color: #e0e0f0; font-weight: 500; }

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0; left: 0;
  width: 100%; height: 100%;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-box {
  background: #1a1a2e;
  border: 1px solid #2a2a4a;
  border-radius: 12px;
  max-width: 650px;
  width: 90%;
  max-height: 75vh;
  overflow-y: auto;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid #2a2a4a;
}
.modal-head h3 { font-size: 15px; color: #e0e0f0; margin: 0; }
.modal-x { background: none; border: none; color: #888; font-size: 18px; cursor: pointer; }
.modal-x:hover { color: #e0e0f0; }

.ticker-grid {
  padding: 16px 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.ticker-chip {
  padding: 3px 8px;
  font-size: 11px;
  font-family: monospace;
  background: #16213e;
  border: 1px solid #2a2a4a;
  border-radius: 12px;
  color: #e0e0f0;
}

.steps { padding: 16px 20px; }
.step {
  display: flex;
  gap: 14px;
  margin-bottom: 20px;
}
.step:last-child { margin-bottom: 0; }
.step-num {
  width: 30px; height: 30px;
  border-radius: 50%;
  background: #4a6fa5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}
.step strong { font-size: 14px; color: #e0e0f0; }
.step p { font-size: 12px; color: #aaa; margin: 4px 0; line-height: 1.4; }
.step code {
  display: block;
  font-family: monospace;
  font-size: 11px;
  color: #7eb8ff;
  background: #0f0f23;
  padding: 6px 10px;
  border-radius: 4px;
  margin-top: 4px;
}
</style>
