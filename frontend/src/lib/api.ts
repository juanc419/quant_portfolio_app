import type { BacktestMethod, CompareResponse, FundamentalMethod, FundamentalResponse, MarketDataProvider, MarketDataProviderStatus, MarketDataResponse, MethodCatalog, Optimizer, PricePanel } from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new Error('No fue posible conectar con la API. Verifica que el backend esté ejecutándose en el puerto 8000.')
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const validationDetails = Array.isArray(body.detail)
      ? body.detail.map((issue: {loc?: unknown[]; msg?: unknown}) => {
        const location = Array.isArray(issue.loc) ? issue.loc.slice(1).map(String).join('.') : ''
        const message = typeof issue.msg === 'string' ? issue.msg : 'dato inválido'
        return location ? `${location}: ${message}` : message
      }).join(' · ')
      : ''
    const detail = typeof body.detail === 'string'
      ? body.detail
      : validationDetails || 'La solicitud no pudo completarse.'
    throw new Error(detail)
  }
  return body as T
}

export const getMethods = () => request<MethodCatalog>('/methods')
export const getMarketDataProviders = async () => request<{providers: MarketDataProviderStatus[]}>('/market-data/providers')
export const downloadMarketData = (payload: {
  provider: MarketDataProvider
  symbols: string[]
  start_date: string
  end_date: string
}) => request<MarketDataResponse>('/market-data/download', { method: 'POST', body: JSON.stringify(payload) })

export async function compareBacktests(payload: {
  panel: PricePanel
  benchmark_asset: string | null
  methods: BacktestMethod[]
  optimizers: Optimizer[]
  top_n: number
  lookback_months: number
  skip_months: number
  transaction_cost_bps: number
  initial_capital: number
  max_weight: number
}) {
  return request<CompareResponse>('/backtests/compare', { method: 'POST', body: JSON.stringify(payload) })
}

export const screenFundamentals = (payload: {
  method: FundamentalMethod
  fundamentals: Record<string, Record<string, string | number | null>>
  top_n: number
  min_score: number
}) => request<FundamentalResponse>('/selection/fundamental', { method: 'POST', body: JSON.stringify(payload) })
