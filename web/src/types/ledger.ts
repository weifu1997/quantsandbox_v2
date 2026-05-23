export interface LedgerPeriodSummary {
  strategy_id: string
  window: { start: string; end: string }
  aum_start: number
  aum_end: number
  total_return_pct: number
  annual_return: number
  sharpe: number
  max_drawdown: number
  win_rate: number
  rebalance_count: number
}

export interface LedgerRebalanceRow {
  date: string
  start_equity: number
  gross_return_pct: number
  net_return_pct: number
  turnover_pct: number
  cost_cny: number
  end_equity: number
  hold_count: number
  buy_count: number
  sell_count: number
  buy: string
  buy_names?: string
  sell: string
  sell_names?: string
  holdings: string
  holdings_names?: string
  avg_participation_rate?: number | null
  max_participation_rate?: number | null
  impact_cost_bps?: number | null
  extreme_count?: number | null
}

export interface LedgerPeriodReport {
  summary: LedgerPeriodSummary
  rebalances: LedgerRebalanceRow[]
}

export interface StockLedgerSummary {
  strategy_id: string
  window: { start: string; end: string }
  aum_start: number
  aum_end: number
  rebalance_count: number
  trade_row_count: number
  position_snapshot_row_count: number
  closed_trade_row_count: number
  note: string
}

export interface StockTradeRow {
  date: string
  ticker: string
  name?: string
  side: 'BUY' | 'SELL'
  price: number
  shares: number
  trade_notional: number
  prev_weight: number
  new_weight: number
  delta_weight: number
  realized_pnl: number | ''
}

export interface PositionSnapshotRow {
  date: string
  ticker: string
  name?: string
  weight: number
  position_notional: number
  reference_price: number
  shares_held: number
  avg_cost: number
}

export interface ClosedTradeRow {
  date: string
  ticker: string
  name?: string
  sell_price: number
  sell_shares: number
  avg_cost: number
  realized_pnl: number
}

export interface StockLedgerReport {
  summary: StockLedgerSummary
  trades: StockTradeRow[]
  position_snapshots: PositionSnapshotRow[]
  closed_trades: ClosedTradeRow[]
}
