import { useEffect, useMemo, useState, type ChangeEvent, type CSSProperties, type ReactNode } from 'react'
import {
  Activity, ArrowDownRight, ArrowUpRight, BarChart3, Check, CircleHelp,
  Database, Download, FileSpreadsheet, Gauge, Layers3, LoaderCircle, Play,
  ShieldCheck, SlidersHorizontal, Sparkles, Target, Upload, X,
} from 'lucide-react'
import { compareBacktests, downloadMarketData, getMarketDataProviders, getMethods, screenFundamentals } from './lib/api'
import { parseFundamentalsCsv, parsePriceCsv } from './lib/csv'
import type { BacktestMethod, BacktestResult, FundamentalMethod, FundamentalResponse, MarketDataProvider, MarketDataProviderStatus, MethodCatalog, Optimizer, PricePanel } from './lib/types'

type Page = 'backtest' | 'fundamental' | 'recommendations'

const defaultMethods: BacktestMethod[] = ['momentum', 'low_beta', 'cluster_selection']
const defaultOptimizers: Optimizer[] = ['equal', 'inverse_volatility']
const optimizerColors = ['#69e0c0', '#7b9cff', '#f5bd67', '#bc91ff', '#ff8c9e', '#69c9ed', '#e4dc78']
const localDateString = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
const fiveYearsAgo = () => { const value = new Date(); value.setFullYear(value.getFullYear() - 5); return localDateString(value) }

function App() {
  const [page, setPage] = useState<Page>('backtest')
  const [catalog, setCatalog] = useState<MethodCatalog | null>(null)
  const [panel, setPanel] = useState<PricePanel | null>(null)
  const [panelLabel, setPanelLabel] = useState('Sin datos cargados')
  const [panelSource, setPanelSource] = useState('—')
  const [dataLoading, setDataLoading] = useState(true)
  const [apiStatus, setApiStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking')
  const [providers, setProviders] = useState<MarketDataProviderStatus[]>([])
  const [dataProvider, setDataProvider] = useState<MarketDataProvider>('yfinance')
  const [symbolsInput, setSymbolsInput] = useState('SPY, QQQ, IWM')
  const [startDate, setStartDate] = useState(fiveYearsAgo)
  const [endDate, setEndDate] = useState(() => localDateString(new Date()))
  const [priceFile, setPriceFile] = useState<File | null>(null)
  const [volumeFile, setVolumeFile] = useState<File | null>(null)
  const [methods, setMethods] = useState<BacktestMethod[]>(defaultMethods)
  const [optimizers, setOptimizers] = useState<Optimizer[]>(defaultOptimizers)
  const [benchmark, setBenchmark] = useState('')
  const [topN, setTopN] = useState(3)
  const [lookback, setLookback] = useState(12)
  const [skip, setSkip] = useState(1)
  const [cost, setCost] = useState(10)
  const [capital, setCapital] = useState(100_000)
  const [maxWeight, setMaxWeight] = useState(0.6)
  const [recommendationVolatilityLimit, setRecommendationVolatilityLimit] = useState(0.25)
  const [results, setResults] = useState<BacktestResult[]>([])
  const [compareErrors, setCompareErrors] = useState<{method: string; optimizer: string; error: string}[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [fundamentalFile, setFundamentalFile] = useState<File | null>(null)
  const [fundamentalMethod, setFundamentalMethod] = useState<FundamentalMethod>('piotroski')
  const [fundamentalTopN, setFundamentalTopN] = useState(20)
  const [minScore, setMinScore] = useState(7)
  const [fundamentalResults, setFundamentalResults] = useState<FundamentalResponse | null>(null)

  useEffect(() => {
    Promise.all([getMethods(), getMarketDataProviders()])
      .then(([methodsResponse, providerResponse]) => {
        setCatalog(methodsResponse)
        setProviders(providerResponse.providers)
        setApiStatus('connected')
      })
      .catch((cause: unknown) => {
        setApiStatus('disconnected')
        setError(cause instanceof Error ? cause.message : 'No se pudo iniciar la aplicación.')
      })
      .finally(() => setDataLoading(false))
  }, [])

  const assetNames = useMemo(() => Object.keys(panel?.prices ?? {}), [panel])
  const nonBenchmarkAssets = assetNames.filter((asset) => asset !== benchmark)
  const selectedCombinations = methods.length * optimizers.length
  const selectedProviderStatus = providers.find((provider) => provider.id === dataProvider)
  const fundamentalsTemplate = fundamentalMethod === 'fama_french'
    ? {href: '/ejemplo_fama_french.csv', label: 'Descargar plantilla Fama–French'}
    : fundamentalMethod === 'piotroski'
      ? {href: '/ejemplo_piotroski.csv', label: 'Descargar plantilla Piotroski'}
      : null

  async function downloadPrices() {
    const symbols = symbolsInput.split(/[\s,;]+/).map((symbol) => symbol.trim()).filter(Boolean)
    if (symbols.length < 2) {
      setError('Escribe al menos dos símbolos separados por coma.')
      return
    }
    setDataLoading(true)
    setError('')
    try {
      const response = await downloadMarketData({ provider: dataProvider, symbols, start_date: startDate, end_date: endDate })
      // Keep only the PricePanel contract; download metadata must not be sent to strict backtest schemas.
      setPanel({ dates: response.dates, prices: response.prices, volumes: response.volumes })
      setPanelLabel(`${dataProvider === 'yfinance' ? 'Yahoo Finance' : 'MetaTrader 5'} · ${response.symbols.join(', ')}`)
      setPanelSource(dataProvider === 'yfinance' ? 'YAHOO FINANCE' : 'METATRADER 5')
      setBenchmark((current) => response.prices[current] ? current : response.prices.SPY ? 'SPY' : '')
      setPriceFile(null)
      setVolumeFile(null)
      setResults([])
      setCompareErrors([])
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudieron descargar los precios.')
    } finally {
      setDataLoading(false)
    }
  }

  async function usePriceFiles() {
    if (!priceFile) return
    setDataLoading(true)
    setError('')
    try {
      const parsed = await parsePriceCsv(priceFile, volumeFile ?? undefined)
      setPanel(parsed)
      setPanelLabel(priceFile.name)
      setPanelSource('CSV')
      setBenchmark('')
      setResults([])
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudieron validar los archivos.')
    } finally {
      setDataLoading(false)
    }
  }

  async function runComparison() {
    if (!panel || !methods.length || !optimizers.length) return
    setBusy(true)
    setError('')
    setCompareErrors([])
    try {
      const response = await compareBacktests({
        panel, benchmark_asset: benchmark || null, methods, optimizers, top_n: topN,
        lookback_months: lookback, skip_months: skip, transaction_cost_bps: cost,
        initial_capital: capital, max_weight: maxWeight,
      })
      setResults(response.results)
      setCompareErrors(response.errors)
      if (!response.results.length) setError('No hubo resultados válidos; revisa los datos y parámetros.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'La comparación no pudo ejecutarse.')
    } finally {
      setBusy(false)
    }
  }

  async function runFundamental() {
    if (!fundamentalFile) return
    setBusy(true)
    setError('')
    try {
      const fundamentals = await parseFundamentalsCsv(fundamentalFile)
      const response = await screenFundamentals({ method: fundamentalMethod, fundamentals, top_n: fundamentalTopN, min_score: minScore })
      setFundamentalResults(response)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo ejecutar el screening.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><Activity size={21} /></div><div><strong>QUANT<span>CORE</span></strong><small>PORTFOLIO LAB</small></div></div>
        <div className="sidebar-label">WORKSPACE</div>
        <button className={`nav-item ${page === 'backtest' ? 'active' : ''}`} onClick={() => { setPage('backtest'); setError('') }}><BarChart3 size={17} /> Backtest y comparación</button>
        <button className={`nav-item ${page === 'fundamental' ? 'active' : ''}`} onClick={() => { setPage('fundamental'); setError('') }}><Target size={17} /> Selección fundamental</button>
        <button className={`nav-item ${page === 'recommendations' ? 'active' : ''}`} onClick={() => { setPage('recommendations'); setError('') }}><Sparkles size={17} /> Recomendaciones</button>
        <div className="sidebar-note"><div className="note-icon"><ShieldCheck size={16} /></div><div><b>Motor cuantitativo</b><p>Los cálculos se ejecutan con la librería local <code>quant_core</code>.</p></div></div>
        <div className="sidebar-footer"><span className="status-dot" /> API local <span className="version">v0.1</span></div>
      </aside>

      <main className="main-area">
        <header className="topbar"><div className="breadcrumbs">Quant Research <span>/</span> {page === 'backtest' ? 'Backtest y comparación' : page === 'fundamental' ? 'Selección fundamental' : 'Recomendaciones'}</div><div className="topbar-right"><div className={`api-status ${apiStatus}`}><span className={`status-dot ${apiStatus}`}/> {apiStatus === 'connected' ? 'API conectada' : apiStatus === 'checking' ? 'Conectando API' : 'API desconectada'}</div><div className="avatar">JQ</div></div></header>

        <div className="content">
          {page === 'backtest' ? <>
            <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line"/> RESEARCH WORKBENCH</div><h1>Comparación de portafolios</h1><p>Evalúa señales de selección y esquemas de asignación sobre el mismo universo histórico.</p></div></div>

            {error && <div className="alert alert-error"><CircleHelp size={17}/><span>{error}</span><button onClick={() => setError('')} aria-label="Cerrar"><X size={15}/></button></div>}
            <div className="workbench-grid">
              <section className="panel controls-panel">
                <div className="panel-heading"><div className="panel-heading-icon"><SlidersHorizontal size={17}/></div><div><h2>Configuración del experimento</h2><p>Define datos, universo y supuestos del backtest</p></div></div>
                <div className="control-section"><div className="section-title"><span>01</span><b>Datos de mercado</b><span className="section-rule"/></div>
                  <div className="data-source-card"><div className="source-icon"><Database size={17}/></div><div className="source-copy"><b>{panelLabel}</b><small>{panel ? `${panel.dates.length.toLocaleString('es-CO')} observaciones · ${assetNames.length} activos` : dataLoading ? 'Conectando con el servicio de datos…' : 'Elige una fuente y descarga precios históricos.'}</small></div><span className="source-badge">{panelSource}</span></div>
                  <Field label="Fuente de precios"><select value={dataProvider} onChange={(event) => setDataProvider(event.target.value as MarketDataProvider)}><option value="yfinance">Yahoo Finance · yfinance</option><option value="metatrader5">MetaTrader 5 · bróker</option></select></Field>
                  {selectedProviderStatus && <p className={`hint provider-hint ${selectedProviderStatus.available ? '' : 'unavailable'}`}>{selectedProviderStatus.available ? selectedProviderStatus.note : `${selectedProviderStatus.note} Falta instalar o configurar el conector en el backend.`}</p>}
                  <Field label="Símbolos" hint="Separados por coma"><input type="text" value={symbolsInput} onChange={(event) => setSymbolsInput(event.target.value)} placeholder={dataProvider === 'yfinance' ? 'SPY, QQQ, IWM' : 'EURUSD, GBPUSD, USDJPY'}/></Field>
                  <div className="two-fields"><Field label="Fecha inicial"><input type="date" value={startDate} max={endDate} onChange={(event) => setStartDate(event.target.value)}/></Field><Field label="Fecha final"><input type="date" value={endDate} min={startDate} onChange={(event) => setEndDate(event.target.value)}/></Field></div>
                  <button className="button button-primary full-width market-download" onClick={downloadPrices} disabled={dataLoading || !startDate || !endDate}><Download size={14}/>{dataLoading ? 'Descargando históricos…' : 'Descargar precios diarios'}</button>
                  <p className="hint">Yahoo usa precios diarios ajustados por dividendos y splits. MetaTrader usa cierres y tick volume del bróker; el terminal debe estar instalado y conectado.</p>
                  <div className="manual-source-label">O valida precios desde un archivo</div>
                  <label className="file-drop"><Upload size={16}/><span>{priceFile ? priceFile.name : 'Cargar precios CSV'}</span><input type="file" accept=".csv,text/csv" onChange={(event: ChangeEvent<HTMLInputElement>) => setPriceFile(event.target.files?.[0] ?? null)}/></label>
                  <label className="file-drop secondary"><FileSpreadsheet size={16}/><span>{volumeFile ? volumeFile.name : 'Volúmenes (opcional)'}</span><input type="file" accept=".csv,text/csv" onChange={(event: ChangeEvent<HTMLInputElement>) => setVolumeFile(event.target.files?.[0] ?? null)}/></label>
                  <button className="button button-outline full-width" onClick={usePriceFiles} disabled={!priceFile || dataLoading}><Check size={14}/> Validar y usar archivos</button>
                  <p className="hint">CSV ancho: una fila por fecha, una columna por activo. La primera columna debe llamarse Date o Fecha.</p>
                  <Field label="Activo de referencia" hint="Se excluye del universo invertible"><select value={benchmark} onChange={(event) => setBenchmark(event.target.value)}><option value="">Sin benchmark</option>{assetNames.map((asset) => <option key={asset}>{asset}</option>)}</select></Field>
                </div>
                <div className="control-section"><div className="section-title"><span>02</span><b>Selección de activos</b><span className="section-rule"/></div>
                  <div className="choice-list">{catalog?.backtest_selection.map((method) => <label className="choice-row" key={method.id}><input type="checkbox" checked={methods.includes(method.id)} onChange={() => setMethods((current) => toggleItem(current, method.id))}/><span className="checkbox-ui"><Check size={12}/></span><span>{method.id === 'momentum' ? `Momentum ${lookback}–${skip}` : method.id === 'liquidity_momentum' ? `Momentum + liquidez (${lookback}–${skip})` : method.label}</span><span className="choice-tag">{method.id === 'momentum' ? 'RETORNO' : method.id === 'low_beta' ? 'RIESGO' : method.id === 'liquidity_momentum' ? 'LIQUIDEZ' : 'DIVERSIFICACIÓN'}</span></label>)}</div>
                  <p className="hint">Momentum usa 12–1 por defecto. Cambia la ventana y los meses de omisión para probar otras variantes.</p>
                  <div className="two-fields"><Field label="Activos objetivo"><input type="number" min={1} max={50} value={topN} onChange={(event) => setTopN(Number(event.target.value))}/></Field><Field label="Ventana de señal (meses)"><input type="number" min={2} max={60} value={lookback} onChange={(event) => { const value = Number(event.target.value); setLookback(value); setSkip((current) => Math.min(current, Math.max(0, value - 1))) }}/></Field></div>
                  <Field label="Meses de omisión"><input type="number" min={0} max={lookback - 1} value={skip} onChange={(event) => setSkip(Number(event.target.value))}/></Field>
                </div>
                <div className="control-section"><div className="section-title"><span>03</span><b>Asignación de pesos</b><span className="section-rule"/></div>
                  <div className="optimizer-grid">{catalog?.optimizers.map((optimizer, index) => <label className={`optimizer-choice ${optimizers.includes(optimizer.id) ? 'selected' : ''}`} key={optimizer.id} style={{'--opt-color': optimizerColors[index % optimizerColors.length]} as CSSProperties}><input type="checkbox" checked={optimizers.includes(optimizer.id)} onChange={() => setOptimizers((current) => toggleItem(current, optimizer.id))}/><span className="optimizer-radio"><span/></span>{optimizer.label}</label>)}</div>
                  <Field label="Peso máximo por activo"><div className="range-wrap"><input type="range" min="0.2" max="1" step="0.05" value={maxWeight} onChange={(event) => setMaxWeight(Number(event.target.value))}/><span>{(maxWeight * 100).toFixed(0)}%</span></div></Field>
                  <div className="two-fields"><Field label="Costo (pb) por rebalanceo"><input type="number" min="0" max="9999" value={cost} onChange={(event) => setCost(Number(event.target.value))}/></Field><Field label="Capital inicial"><input type="number" min="1" step="10000" value={capital} onChange={(event) => setCapital(Number(event.target.value))}/></Field></div>
                </div>
                <button className="button button-primary run-button" onClick={runComparison} disabled={busy || dataLoading || !panel || !methods.length || !optimizers.length || selectedCombinations > 12}><span>{busy ? <LoaderCircle className="spin" size={16}/> : <Play size={15} fill="currentColor"/>}</span>{busy ? 'Ejecutando comparación…' : 'Ejecutar comparación'}<span className="run-count">{selectedCombinations}/12</span></button>
                {selectedCombinations > 12 && <p className="limit-error">Reduce la selección a 12 combinaciones como máximo.</p>}
              </section>

              <section className="results-column">
                <div className="summary-strip"><SummaryItem icon={<Layers3 size={16}/>} label="COMBINACIONES" value={results.length ? String(results.length) : '—'}/><SummaryItem icon={<Database size={16}/>} label="ACTIVOS" value={panel ? String(nonBenchmarkAssets.length) : '—'}/><SummaryItem icon={<Activity size={16}/>} label="PERÍODO" value={panel ? `${panel.dates[0]} — ${panel.dates.at(-1)}` : '—'}/><SummaryItem icon={<Gauge size={16}/>} label="FRECUENCIA" value="Mensual"/></div>
                {results.length ? <ResultsView results={results} benchmarkName={benchmark || undefined}/> : <div className="empty-state panel"><div className="empty-illustration"><div className="empty-ring ring-one"/><div className="empty-ring ring-two"/><div className="empty-chart"><BarChart3 size={28}/></div><Sparkles className="sparkle" size={15}/></div><h2>Tu espacio de análisis</h2><p>Configura los métodos en el panel izquierdo y ejecuta una comparación. Cada portafolio compartirá el mismo histórico, costos y fecha de rebalanceo.</p><div className="empty-steps"><span><b>1</b> Carga datos</span><span><b>2</b> Elige métodos</span><span><b>3</b> Compara resultados</span></div></div>}
                {compareErrors.length > 0 && <div className="alert alert-warning"><CircleHelp size={16}/><span>{compareErrors.length} combinaciones no se pudieron ejecutar. La comparación muestra los resultados válidos.</span></div>}
              </section>
            </div>
          </> : page === 'fundamental' ? <>
            <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line"/> FUNDAMENTAL RESEARCH</div><h1>Selección fundamental</h1><p>Calcula scores financieros y compara empresas usando datos contables transversales.</p></div></div>
            {error && <div className="alert alert-error"><CircleHelp size={17}/><span>{error}</span><button onClick={() => setError('')} aria-label="Cerrar"><X size={15}/></button></div>}
            <div className="fundamental-layout">
              <section className="panel fundamental-controls">
                <div className="panel-heading"><div className="panel-heading-icon"><Target size={17}/></div><div><h2>Screening de empresas</h2><p>Selecciona el modelo y carga las variables requeridas</p></div></div>
                <Field label="Modelo de selección"><select value={fundamentalMethod} onChange={(event) => setFundamentalMethod(event.target.value as FundamentalMethod)}>{catalog?.fundamental_selection.map((method) => <option key={method.id} value={method.id}>{method.label}</option>)}</select></Field>
                <label className="fundamental-drop"><Upload size={19}/><b>{fundamentalFile?.name ?? 'Selecciona un archivo CSV'}</b><span>Una fila por empresa con columnas de datos financieros</span><input type="file" accept=".csv,text/csv" onChange={(event) => { setFundamentalFile(event.target.files?.[0] ?? null); setFundamentalResults(null) }}/></label>
                {fundamentalsTemplate && <a className="sample-download" href={fundamentalsTemplate.href} download><Download size={13}/> {fundamentalsTemplate.label}</a>}
                <div className="two-fields"><Field label="Número máximo de seleccionadas"><input type="number" min={1} max={100} value={fundamentalTopN} onChange={(event) => setFundamentalTopN(Number(event.target.value))}/></Field><Field label="F-score mínimo"><input type="number" min={0} max={9} value={minScore} onChange={(event) => setMinScore(Number(event.target.value))}/></Field></div>
                <button className="button button-primary run-button" onClick={runFundamental} disabled={busy || !fundamentalFile}><span>{busy ? <LoaderCircle className="spin" size={16}/> : <Play size={15} fill="currentColor"/>}</span>{busy ? 'Calculando scores…' : 'Ejecutar selección'}</button>
                <div className="method-info"><CircleHelp size={15}/><span>{fundamentalMethod === 'fama_french' ? <>Fama–French necesita <code>market_cap</code> y <code>book_equity</code> o <code>pb_ratio</code>. Rentabilidad operativa y crecimiento de activos afinan el score. Es una clasificación transversal por características, no una regresión histórica de factores.</> : <>Las variables necesarias dependen del modelo. Usa nombres de columnas documentados por <code>quant_core</code>; no completes datos ausentes con ceros.</>}</span></div>
              </section>
              <section className="panel fundamental-results">{fundamentalResults ? <FundamentalTable result={fundamentalResults}/> : <div className="empty-state compact"><div className="empty-illustration"><div className="empty-ring ring-one"/><div className="empty-ring ring-two"/><div className="empty-chart"><Target size={26}/></div></div><h2>Resultados del screening</h2><p>Carga un CSV con columnas contables y el sistema presentará puntajes, ranking y activos seleccionados.</p><div className="csv-example">Activo, current_assets, total_assets, …</div></div>}</section>
            </div>
          </> : <RecommendationsView
            results={results}
            maxAnnualVolatility={recommendationVolatilityLimit}
            onMaxAnnualVolatilityChange={setRecommendationVolatilityLimit}
            onConfigureComparison={() => setPage('backtest')}
          />}
          <footer className="page-footer"><span>QUANT PORTFOLIO LAB</span><span>Investigación cuantitativa · Los resultados no constituyen recomendación de inversión</span></footer>
        </div>
      </main>
    </div>
  )
}

function Field({label, hint, children}: {label: string; hint?: string; children: ReactNode}) {
  return <label className="field"><span className="field-label">{label}{hint && <small>{hint}</small>}</span>{children}</label>
}

function SummaryItem({icon, label, value}: {icon: ReactNode; label: string; value: string}) {
  return <div className="summary-item"><span className="summary-icon">{icon}</span><div><small>{label}</small><b>{value}</b></div></div>
}

function ResultsView({results, benchmarkName}: {results: BacktestResult[]; benchmarkName?: string}) {
  const best = [...results].sort((a,b) => (b.metrics.sharpe_ratio ?? -Infinity) - (a.metrics.sharpe_ratio ?? -Infinity))[0]
  const equitySeries = results.map((result, index) => ({
    name: result.label,
    values: result.series.equity,
    color: optimizerColors[index % optimizerColors.length],
    width: result === best ? 2.7 : 1.7,
  }))
  const benchmarkSeries = results.find((result) => result.series.benchmark_equity)?.series.benchmark_equity
  if (benchmarkSeries) equitySeries.push({ name: benchmarkName ?? 'Benchmark', values: benchmarkSeries, color: '#738093', width: 1.5 })
  const drawdownSeries = results.map((result, index) => ({
    name: result.label,
    values: result.series.drawdown,
    color: optimizerColors[index % optimizerColors.length],
    width: 1.4,
  }))
  const dates = results[0]?.series.dates ?? []
  return <>
    <div className="metric-cards">
      <MetricCard label="MEJOR SHARPE" value={fmt(best?.metrics.sharpe_ratio, '0.00')} sub={best?.label ?? '—'} positive={(best?.metrics.sharpe_ratio ?? 0) >= 0} icon={<Gauge size={16}/>}/>
      <MetricCard label="MEJOR CAGR" value={fmtPercent(best?.metrics.cagr)} sub="Según Sharpe ratio" positive={(best?.metrics.cagr ?? 0) >= 0} icon={<ArrowUpRight size={16}/>}/>
      <MetricCard label="MENOR DRAWDOWN" value={fmtPercent(best?.metrics.max_drawdown)} sub="Del líder por Sharpe" positive icon={<ArrowDownRight size={16}/>}/>
      <MetricCard label="VOLATILIDAD ANUAL" value={fmtPercent(best?.metrics.annualized_volatility)} sub={best?.label ?? '—'} icon={<Activity size={16}/>}/>
    </div>
    <div className="panel chart-panel"><div className="chart-title"><div><h2>Evolución del capital</h2><p>Valor neto después de costos de transacción</p></div><div className="chart-legend-label"><span className="legend-dot"/> {results.length} portafolios</div></div><LineChart series={equitySeries} dates={dates} height={328} format="currency"/></div>
    <div className="panel chart-panel drawdown-panel"><div className="chart-title"><div><h2>Drawdown histórico</h2><p>Pérdida desde el máximo acumulado</p></div></div><LineChart series={drawdownSeries} dates={dates} height={232} format="percent" fillToZero/></div>
    <div className="panel table-panel"><div className="chart-title"><div><h2>Tabla comparativa</h2><p>Métricas anualizadas salvo retorno total y drawdown</p></div><span className="date-chip">Último rebalanceo · {results[0]?.latest_signal_date}</span></div><div className="table-scroll"><table><thead><tr><th>PORTAFOLIO</th><th>RETORNO TOTAL</th><th>CAGR</th><th>VOLATILIDAD</th><th>SHARPE</th><th>MAX DRAWDOWN</th><th>CVaR 95%</th><th>TURNOVER ANUAL</th></tr></thead><tbody>{[...results].sort((a,b) => (b.metrics.sharpe_ratio ?? -Infinity) - (a.metrics.sharpe_ratio ?? -Infinity)).map((result, index) => <tr key={`${result.method}-${result.optimizer}`}><td><span className="rank-chip">{index + 1}</span><b>{result.label}</b><small>{result.method} / {result.optimizer}</small></td><td>{fmtPercent(result.metrics.total_return)}</td><td>{fmtPercent(result.metrics.cagr)}</td><td>{fmtPercent(result.metrics.annualized_volatility)}</td><td className="sharpe-cell">{fmt(result.metrics.sharpe_ratio, '0.000')}</td><td className="negative-cell">{fmtPercent(result.metrics.max_drawdown)}</td><td>{fmtPercent(result.metrics.historical_cvar_95)}</td><td>{fmt(result.metrics.annual_turnover, '0.00')}×</td></tr>)}</tbody></table></div></div>
    <div className="panel holdings-panel"><div className="chart-title"><div><h2>Composición más reciente</h2><p>Pesos objetivo al último rebalanceo generado</p></div></div><div className="holdings-grid">{results.slice(0, Math.min(results.length, 6)).map((result, index) => <div className="holding-card" key={`${result.method}-${result.optimizer}`}><div className="holding-head"><span className="holding-color" style={{backgroundColor: optimizerColors[index % optimizerColors.length]}}/><b>{result.label}</b></div>{result.latest_holdings.map((holding) => <div className="holding-row" key={holding.asset}><span>{holding.asset}</span><div className="holding-bar"><i style={{width: `${Math.min(100, holding.weight * 100 / Math.max(...result.latest_holdings.map((row) => row.weight), 0.01))}%`, backgroundColor: optimizerColors[index % optimizerColors.length]}}/></div><b>{(holding.weight * 100).toFixed(1)}%</b></div>)}</div>)}</div></div>
  </>
}

function MetricCard({label, value, sub, positive, icon}: {label:string; value:string; sub:string; positive?:boolean; icon:ReactNode}) {
  return <div className="panel metric-card"><div className="metric-head"><span>{label}</span><span className={`metric-icon ${positive ? 'green' : ''}`}>{icon}</span></div><strong className={positive === false ? 'metric-negative' : ''}>{value}</strong><small>{sub}</small></div>
}

function RecommendationsView({results, maxAnnualVolatility, onMaxAnnualVolatilityChange, onConfigureComparison}: {
  results: BacktestResult[]
  maxAnnualVolatility: number
  onMaxAnnualVolatilityChange: (value: number) => void
  onConfigureComparison: () => void
}) {
  const metric = (result: BacktestResult, name: string) => {
    const value = result.metrics[name]
    return typeof value === 'number' && Number.isFinite(value) ? value : null
  }
  const validResults = results.filter((result) => metric(result, 'annualized_volatility') !== null)
  const withinLimit = validResults.filter((result) => (metric(result, 'annualized_volatility') ?? Infinity) <= maxAnnualVolatility)
  const growthCandidates = withinLimit.filter((result) => metric(result, 'cagr') !== null)
  const bestGrowth = [...growthCandidates].sort((a, b) => (metric(b, 'cagr') ?? -Infinity) - (metric(a, 'cagr') ?? -Infinity))[0]
  const sharpeCandidates = validResults.filter((result) => metric(result, 'sharpe_ratio') !== null)
  const bestSharpe = [...sharpeCandidates].sort((a, b) => (metric(b, 'sharpe_ratio') ?? -Infinity) - (metric(a, 'sharpe_ratio') ?? -Infinity))[0]
  const lowestVolatility = [...validResults].sort((a, b) => (metric(a, 'annualized_volatility') ?? Infinity) - (metric(b, 'annualized_volatility') ?? Infinity))[0]
  const dates = results[0]?.series.dates ?? []

  return <>
    <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line"/> PORTFOLIO DISCOVERY</div><h1>Recomendaciones de portafolios</h1><p>Encuentra configuraciones con crecimiento histórico y volatilidad acorde a tu límite.</p></div></div>
    <section className="panel recommendation-controls">
      <div><b>Volatilidad anual máxima</b><p>El primer perfil solo considera portafolios que cumplen este límite.</p></div>
      <div className="range-wrap"><input aria-label="Volatilidad anual máxima" type="range" min="0.05" max="0.60" step="0.01" value={maxAnnualVolatility} onChange={(event) => onMaxAnnualVolatilityChange(Number(event.target.value))}/><span>{fmtPercent(maxAnnualVolatility)}</span></div>
    </section>

    {!results.length ? <section className="panel recommendation-empty">
      <div className="empty-chart"><Sparkles size={25}/></div><h2>Ejecuta una comparación primero</h2>
      <p>Carga precios y compara métodos de selección y asignación. Esta pestaña ordenará los resultados con el mismo histórico y costos.</p>
      <button className="button button-primary" onClick={onConfigureComparison}>Ir a backtest y comparación</button>
    </section> : !validResults.length ? <div className="alert alert-warning"><CircleHelp size={16}/><span>Los resultados no incluyen volatilidad anual válida para generar recomendaciones.</span></div> : <>
      <div className="recommendation-context">Última comparación · {dates[0] ?? '—'} — {dates.at(-1) ?? '—'} · {results.length} portafolios evaluados</div>
      {!bestGrowth && <div className="alert alert-warning"><CircleHelp size={16}/><span>Ninguna estrategia cumple el límite de volatilidad de {fmtPercent(maxAnnualVolatility)}. Aumenta el umbral para ver opciones de crecimiento dentro del límite.</span></div>}
      <div className="recommendation-grid">
        {bestGrowth && <RecommendationCard
          title="Mayor crecimiento bajo el límite"
          rationale="Mayor CAGR histórica entre los portafolios que cumplen tu máximo de volatilidad."
          result={bestGrowth}
          primaryMetric="cagr"
          maxAnnualVolatility={maxAnnualVolatility}
          metric={metric}
          icon={<ArrowUpRight size={15}/>}
        />}
        {bestSharpe && <RecommendationCard
          title="Mejor retorno ajustado por riesgo"
          rationale="Mayor Sharpe histórico entre las estrategias comparadas."
          result={bestSharpe}
          primaryMetric="sharpe_ratio"
          maxAnnualVolatility={maxAnnualVolatility}
          metric={metric}
          icon={<Gauge size={15}/>}
        />}
        {lowestVolatility && <RecommendationCard
          title="Menor volatilidad"
          rationale="La trayectoria histórica más estable dentro de los resultados disponibles."
          result={lowestVolatility}
          primaryMetric="annualized_volatility"
          maxAnnualVolatility={maxAnnualVolatility}
          metric={metric}
          icon={<Activity size={15}/>}
        />}
      </div>
      <div className="panel recommendation-methodology"><b>Cómo leer estas sugerencias</b><p>El CAGR y la volatilidad resumen el periodo probado después de costos; el Sharpe compara retorno con riesgo. Son métricas históricas y pueden cambiar con el periodo, los datos y los supuestos. No son pronósticos de rentabilidad futura.</p></div>
    </>}
  </>
}

function RecommendationCard({title, rationale, result, primaryMetric, maxAnnualVolatility, metric, icon}: {
  title: string
  rationale: string
  result: BacktestResult
  primaryMetric: 'cagr' | 'sharpe_ratio' | 'annualized_volatility'
  maxAnnualVolatility: number
  metric: (result: BacktestResult, name: string) => number | null
  icon: ReactNode
}) {
  const annualVolatility = metric(result, 'annualized_volatility')
  const primaryValue = metric(result, primaryMetric)
  const primaryLabel = primaryMetric === 'cagr' ? 'CAGR HISTÓRICA' : primaryMetric === 'sharpe_ratio' ? 'SHARPE HISTÓRICO' : 'VOLATILIDAD ANUAL'
  const formattedValue = primaryValue === null ? '—' : primaryMetric === 'sharpe_ratio' ? fmt(primaryValue, '0.000') : fmtPercent(primaryValue)
  return <article className="panel recommendation-card">
    <div className="recommendation-card-title"><span>{icon}</span><div><small>{title}</small><b>{result.label}</b></div></div>
    <p>{rationale}</p>
    <div className="recommendation-primary"><small>{primaryLabel}</small><strong>{formattedValue}</strong></div>
    <div className="recommendation-stats"><span>Volatilidad <b>{fmtPercent(annualVolatility)}</b></span><span>CAGR <b>{fmtPercent(metric(result, 'cagr'))}</b></span><span>Sharpe <b>{fmt(metric(result, 'sharpe_ratio'), '0.000')}</b></span></div>
    {annualVolatility !== null && <span className={`recommendation-status ${annualVolatility <= maxAnnualVolatility ? 'within' : 'over'}`}>{annualVolatility <= maxAnnualVolatility ? 'Dentro del límite' : 'Supera el límite'}</span>}
    <div className="recommendation-holdings"><small>COMPOSICIÓN RECIENTE</small>{result.latest_holdings.slice(0, 4).map((holding) => <span key={holding.asset}>{holding.asset}<b>{fmtPercent(holding.weight)}</b></span>)}</div>
  </article>
}

function FundamentalTable({result}: {result: FundamentalResponse}) {
  const allColumns = Array.from(new Set(result.rows.flatMap((row) => Object.keys(row))))
  const famaFrenchColumns = ['composite_score', 'size', 'value', 'profitability', 'investment', 'size_bucket', 'value_bucket', 'annualized_volatility']
  const columns = result.method === 'fama_french'
    ? famaFrenchColumns.filter((key) => allColumns.includes(key))
    : allColumns.filter((key) => key !== 'selected').slice(0, 8)
  return <><div className="chart-title"><div><h2>Empresas clasificadas</h2><p>Score: <code>{result.score_name}</code> · {result.rows.length} activos evaluados · {result.selected.length} seleccionados</p></div><span className="source-badge">{result.method}</span></div><div className="table-scroll fundamental-table-wrap"><table><thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll('_',' ').toUpperCase()}</th>)}<th>ESTADO</th></tr></thead><tbody>{result.rows.map((row, index) => <tr key={String(row.asset ?? index)}>{columns.map((column) => <td key={column}>{typeof row[column] === 'number' ? fmt(row[column] as number, '0.000') : String(row[column] ?? '—')}</td>)}<td>{row.selected ? <span className="selected-pill"><Check size={12}/> Seleccionada</span> : <span className="muted-pill">Fuera de corte</span>}</td></tr>)}</tbody></table></div></>
}

type ChartSeries = {name: string; values: (number | null)[]; color: string; width: number}

function LineChart({series, dates, height, format, fillToZero = false}: {
  series: ChartSeries[]; dates: string[]; height: number; format: 'currency' | 'percent'; fillToZero?: boolean
}) {
  const width = 1000
  const margin = {top: 16, right: 18, bottom: 34, left: 72}
  const plotWidth = width - margin.left - margin.right
  const plotHeight = height - margin.top - margin.bottom
  const values = series.flatMap((line) => line.values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value)))
  const dataMin = values.reduce((current, value) => Math.min(current, value), fillToZero ? 0 : Infinity)
  const dataMax = values.reduce((current, value) => Math.max(current, value), fillToZero ? 0 : -Infinity)
  const span = Math.max(dataMax - dataMin, format === 'percent' ? 0.01 : 1)
  const min = fillToZero ? dataMin : dataMin - span * 0.06
  const max = dataMax + span * 0.06
  const y = (value: number) => margin.top + (max - value) / (max - min || 1) * plotHeight
  const x = (index: number, count: number) => margin.left + (count <= 1 ? 0 : index / (count - 1)) * plotWidth
  const ticks = Array.from({length: 5}, (_, index) => max - (max - min) * index / 4)
  const formatter = format === 'percent'
    ? (value: number) => `${(value * 100).toFixed(0)}%`
    : (value: number) => new Intl.NumberFormat('es-CO', {notation: 'compact', maximumFractionDigits: 1}).format(value)
  const dateAt = (index: number) => dates[index] ?? ''

  return <div className="line-chart-wrap">
    <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={format === 'percent' ? 'Gráfico de drawdown por fecha' : 'Gráfico de evolución del capital por fecha'}>
      {ticks.map((tick, index) => <g key={index}>
        <line x1={margin.left} x2={width - margin.right} y1={y(tick)} y2={y(tick)} stroke="#202a38" strokeWidth="1"/>
        <text x={margin.left - 10} y={y(tick) + 3} textAnchor="end" fill="#8491a2" fontSize="10">{formatter(tick)}</text>
      </g>)}
      <line x1={margin.left} x2={width - margin.right} y1={height - margin.bottom} y2={height - margin.bottom} stroke="#293444"/>
      {dates.length > 0 && <>
        <text x={margin.left} y={height - 10} fill="#8491a2" fontSize="10">{dateAt(0)}</text>
        <text x={width - margin.right} y={height - 10} textAnchor="end" fill="#8491a2" fontSize="10">{dateAt(dates.length - 1)}</text>
      </>}
      {series.map((line) => {
        const validPoints = line.values.flatMap((value, index) => typeof value === 'number' && Number.isFinite(value)
          ? [[x(index, line.values.length), y(value)] as [number, number]]
          : [])
        const points = validPoints.map(([pointX, pointY], index) => `${index ? 'L' : 'M'} ${pointX.toFixed(1)} ${pointY.toFixed(1)}`).join(' ')
        const fillPath = fillToZero && validPoints.length
          ? `${points} L ${validPoints[validPoints.length - 1]![0]} ${y(0)} L ${validPoints[0]![0]} ${y(0)} Z`
          : undefined
        return <g key={line.name}>
          {fillPath && <path d={fillPath} fill={line.color} fillOpacity="0.07"/>}
          <path d={points} fill="none" stroke={line.color} strokeWidth={line.width} strokeLinejoin="round" strokeLinecap="round">
            <title>{line.name}</title>
          </path>
        </g>
      })}
    </svg>
    <div className="chart-series-legend">{series.map((line) => <span key={line.name}><i style={{backgroundColor: line.color}}/>{line.name}</span>)}</div>
  </div>
}

function toggleItem<T extends string>(current: T[], value: T) { return current.includes(value) ? current.filter((item) => item !== value) : [...current, value] }
function fmt(value: unknown, format = '0.00') { return typeof value === 'number' && Number.isFinite(value) ? new Intl.NumberFormat('es-CO', {minimumFractionDigits: format.endsWith('000') ? 3 : 2, maximumFractionDigits: format.endsWith('000') ? 3 : 2}).format(value) : '—' }
function fmtPercent(value: unknown) { return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toLocaleString('es-CO', {minimumFractionDigits: 2, maximumFractionDigits: 2})}%` : '—' }

export default App
