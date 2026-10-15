export type PricePanel = {
  dates: string[]
  prices: Record<string, number[]>
  volumes?: Record<string, number[]> | null
}

export type MarketDataProvider = 'yfinance' | 'metatrader5'
export type MarketDataProviderStatus = {
  id: MarketDataProvider
  label: string
  available: boolean
  note: string
}
export type MarketDataResponse = PricePanel & {
  provider: MarketDataProvider
  symbols: string[]
  observations: number
  start_date: string
  end_date: string
  interval: '1d'
}

export type BacktestMethod = 'momentum' | 'low_beta' | 'sector_rotation' | 'cluster_selection' | 'liquidity_momentum'
export type Optimizer = 'equal' | 'inverse_volatility' | 'momentum' | 'minimum_variance' | 'maximum_sharpe' | 'hrp' | 'risk_parity'
export type FundamentalMethod = 'altman_public' | 'altman_private' | 'altman_non_manufacturing' | 'piotroski' | 'beneish' | 'factor_screening' | 'fama_french'

export type MethodOption<T extends string = string> = { id: T; label: string }
export type MethodCatalog = {
  backtest_selection: MethodOption<BacktestMethod>[]
  optimizers: MethodOption<Optimizer>[]
  fundamental_selection: MethodOption<FundamentalMethod>[]
}

export type BacktestResult = {
  method: BacktestMethod
  optimizer: Optimizer
  label: string
  metrics: Record<string, number | null>
  latest_signal_date: string
  latest_holdings: { asset: string; weight: number }[]
  series: { dates: string[]; equity: (number | null)[]; drawdown: (number | null)[]; benchmark_equity: (number | null)[] | null }
}

export type CompareResponse = { results: BacktestResult[]; errors: { method: string; optimizer: string; error: string }[] }
export type FundamentalResponse = {
  method: FundamentalMethod
  score_name: string
  rows: Record<string, string | number | boolean | null>[]
  selected: { asset: string; score: number | null; rank: number | null }[]
  metadata: Record<string, unknown>
}
