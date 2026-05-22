export interface ExperimentTask {
  task_id: string
  experiment_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: {
    current: number
    total: number
    message: string
  }
  stage: string | null
  error: string | null
  result_ref: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ExperimentResponse {
  experiment: {
    experiment_id: string
    start_date: string
    end_date: string
    factors: string[]
    horizons: number[]
    rebalance_frequency: string
    top_n: number
    weighting: string
    benchmark: string
    created_at: string | null
  }
  task: ExperimentTask
}

export interface BacktestConfig {
  start_date: string
  end_date: string
  universe: string
  factors: string
  horizons: string
  rebalance_frequency: string
  top_n: number
  weighting: string
  benchmark: string
  commission_bps: number
  slippage_bps: number
  annual_turnover_limit: number | null
  initial_aum: number
  board_lot_enabled: boolean
  board_lot_size: number
}

export interface BacktestResult {
  factor_name: string
  annual_return: number
  total_return: number
  sharpe: number
  max_drawdown: number
  turnover: number
  win_rate: number
  rebalance_count: number
  returns_by_date: Record<string, number>
  equity_curve: number[]
  holdings_by_date: Record<string, string[]>
}

export interface ExperimentDetail {
  experiment_id: string
  name: string | null
  universe: string | null
  start_date: string
  end_date: string
  factors: string[]
  horizons: number[]
  rebalance_frequency: string
  top_n: number
  weighting: string
  benchmark: string
  created_at: string | null
}
