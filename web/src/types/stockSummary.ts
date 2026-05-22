export interface StockSummaryRow {
  ticker: string
  buy_count: number
  sell_count: number
  buy_shares_total: number
  sell_shares_total: number
  buy_notional_total: number
  sell_notional_total: number
  estimated_realized_pnl_total: number
  latest_estimated_shares_held: number
  latest_estimated_avg_cost: number
  latest_reference_price: number
  latest_position_notional_est: number
  latest_snapshot_date: string
  estimated_unrealized_pnl: number
  estimated_total_pnl: number
}

export interface StockSummaryReport {
  summary: {
    ticker_count: number
    note: string
  }
  rows: StockSummaryRow[]
}
