# Guía técnica y metodológica

## 1. Propósito y niveles del sistema

`quant_core` concentra implementaciones reutilizables de señales, optimización y analítica. Quant Portfolio Lab es la capa de aplicación: valida entradas, coordina esos componentes y transforma sus resultados en recursos JSON que la interfaz presenta de forma comparativa. La capa web no reimplementa las fórmulas de selección.

El flujo histórico tiene cuatro etapas: (1) construir un panel de precios ajustados y retornos; (2) calcular señales a la fecha de rebalanceo; (3) convertir la selección en pesos objetivo; y (4) aplicar objetivos y costos al periodo posterior. El screening contable se mantiene como flujo transversal separado hasta que existan fundamentales históricos con fechas de publicación o vintages verificables.

## 2. Métodos de selección y sus hipótesis

### 2.1 Momentum de series temporales, 12–1

El momentum de activo se estima con retorno acumulado en una ventana de formación excluyendo el periodo más reciente. Para observaciones diarias, una expresión simple es

\[
M_{i,t}(L,S)=\frac{P_{i,t-S}}{P_{i,t-L}}-1,
\]

donde \(L\) es el rezago de formación y \(S\) evita que el retorno de muy corto plazo domine la señal. La variante común 12–1 forma la señal usando aproximadamente doce meses y omite el mes reciente. Se seleccionan los mayores scores; la aplicación excluye scores no positivos en su configuración de momentum. Esta regla deriva de persistencia transversal de retornos observada en horizontes intermedios, pero puede sufrir reversión, rotación elevada y pérdidas abruptas en cambios de régimen.

### 2.2 Beta baja

Para retornos del activo \(r_i\) y del benchmark \(r_m\), se estima por mínimos cuadrados

\[
\hat\beta_i=\frac{\operatorname{Cov}(r_i,r_m)}{\operatorname{Var}(r_m)}.
\]

La selección larga ordena activos por beta ascendente. No es el factor BAB apalancado de Frazzini y Pedersen: no toma posiciones cortas ni escala las carteras a volatilidad objetivo. La estimación es inestable con muestras cortas y depende de benchmark, frecuencia y régimen.

### 2.3 Rotación sectorial

Ordena proxies de sectores por retorno acumulado de formación, con omisión de corto plazo, y asigna capital a los sectores líderes. El análisis solo representa sectores si el usuario cargó instrumentos sectoriales adecuados; el sistema no deduce sectores desde el ticker.

### 2.4 Selección por clusters

Calcula distancias a partir de dependencias de retornos para agrupar activos y limita la concentración por grupo. La intención es reducir redundancia entre activos altamente correlacionados. La solución depende de la ventana, métrica de distancia, algoritmo jerárquico y número de clusters; no identifica necesariamente sectores económicos ni garantiza baja pérdida extrema.

### 2.5 Momentum con liquidez

Combina la señal de momentum con un filtro basado en volumen negociado. El volumen por sí solo no mide liquidez ejecutable: para un modelo realista hacen falta valor negociado, spread, profundidad, capacidad de mercado y tamaño de orden. El prototipo usa volumen como señal/filtro disponible en el contrato del core.

## 3. Screening fundamental

Todos los métodos requieren columnas por empresa con unidades y fecha de corte coherentes. Los modelos generan ordenamientos, no sustituyen lectura de estados financieros. Los puntajes dependen de la calidad de datos, tratamiento contable y sector.

### 3.1 Altman Z

Para manufactura pública, con ratios sobre activos totales \(A\),

\[
Z=1.2\frac{WC}{A}+1.4\frac{RE}{A}+3.3\frac{EBIT}{A}+0.6\frac{ME}{TL}+1.0\frac{Sales}{A}.
\]

Se requieren `working_capital`, `retained_earnings`, `ebit`, `market_equity`, `total_liabilities`, `sales`, `total_assets`. Los modelos privados y no manufactureros sustituyen coeficientes y patrimonio de mercado por valor contable, de acuerdo con Z′ y Z″. Escala monetaria consistente y denominadores positivos son esenciales. Los cortes de zona son heurísticos del modelo y no probabilidades calibradas de incumplimiento para cualquier país o época.

### 3.2 Piotroski F-score

Suma nueve señales binarias (0/1): rentabilidad sobre activos positiva y creciente; flujo operativo positivo y superior a ROA; menor apalancamiento; mayor liquidez corriente; ausencia de dilución; margen bruto creciente; rotación de activos creciente. El rango es 0–9. Necesita variables de dos periodos:

`roa_current`, `roa_prior`, `cfo_to_assets_current`, `long_term_debt_ratio_current`, `long_term_debt_ratio_prior`, `current_ratio_current`, `current_ratio_prior`, `shares_outstanding_current`, `shares_outstanding_prior`, `gross_margin_current`, `gross_margin_prior`, `asset_turnover_current`, `asset_turnover_prior`.

El score original se usa como filtro de calidad, en particular dentro de universos de valoración. Un score alto no es por sí mismo una señal completa de precio razonable.

### 3.3 Beneish M-score

Combina ocho índices contables que incluyen cuentas por cobrar, margen bruto, calidad de activos, crecimiento de ventas, depreciación, gastos de ventas y administración, apalancamiento y devengos. El contrato de entrada está formado por variables con sufijos `_current` y `_prior` (más `income_before_extraordinary_current` y `cash_flow_operations_current`). El M-score es una bandera de revisión de riesgo de manipulación, no una prueba de fraude. La interpretación exige dos periodos consistentes y cuidado con ceros/valores faltantes.

### 3.4 Screening multifactor

Calcula rangos percentiles combinando value, quality, profitability, momentum, size y low volatility. Admite medidas fundamentales como `pe_ratio`, `pb_ratio`, `ev_ebitda`, `ps_ratio`, `roe`, `roa`, `debt_to_equity`, `altman_z_score`, `gross_margin`, `roic`, `operating_margin` y `market_cap`; el histórico de precios puede proveer momentum y volatilidad en usos de la librería que entreguen tal panel. El API web de esta primera versión recibe fundamentales transversales, por lo que no estima momentum ni volatilidad históricos implícitamente.

### 3.5 Características Fama–French

Clasifica empresas por tamaño, valor, rentabilidad e inversión. La entrada mínima es `market_cap` y `book_equity` o `pb_ratio`; se agregan `operating_profitability` o `operating_income` con `book_equity`, y `asset_growth` para ampliar características. Este ordenamiento transversal es un proxy educativo de características. No reconstruye por sí mismo las series de factores SMB, HML, RMW y CMA ni reproduce las carteras de investigación originales.

## 4. Asignación de pesos

- **Igual ponderación:** \(w_i=1/N\); transparente y de baja dependencia de estimaciones, pero no equipondera riesgo.
- **Volatilidad inversa:** \(w_i\propto1/\hat\sigma_i\); equilibra parcialmente riesgo marginal solo bajo supuestos simplificadores.
- **Ranking momentum:** asigna más peso a posiciones con mejor rango de señal.
- **Mínima varianza:** minimiza \(w^T\Sigma w\) bajo restricciones largas y límites de peso.
- **Máximo Sharpe:** maximiza retorno excedente estimado por unidad de volatilidad; especialmente sensible al error en retornos esperados.
- **HRP:** ordena activos por jerarquía de correlación y reparte riesgo recursivamente; evita invertir directamente la matriz de covarianza.
- **Risk parity:** busca contribuciones de riesgo más equilibradas; depende de la covarianza estimada.

La aplicación limita el peso individual. Si `N × max_weight < 1`, queda parte del capital en efectivo sin rendimiento supuesto. En la versión inicial las estimaciones se calculan con la ventana disponible a cada rebalanceo; no se deben interpretar como parámetros conocidos con certeza.

## 5. Simulación y métricas

Las señales se generan al último día hábil disponible de cada mes y la cartera ejecuta en la sesión siguiente. Esta demora reduce look-ahead de ejecución, pero no modela precios intradía. El backtest aplica costos en puntos básicos a la rotación del portafolio. Faltan dividendos, impuestos, spread, impacto de mercado, restricciones de negociación y errores de proveedor.

Para retornos netos periódicos \(r_t\):

- Retorno total: \(\prod_t(1+r_t)-1\).
- CAGR: \(\left[\prod_t(1+r_t)\right]^{A/T}-1\), con \(A\) periodos anuales y \(T\) observaciones.
- Volatilidad anualizada: \(s(r)\sqrt{A}\).
- Sharpe: retorno medio excedente dividido por desviación estándar, anualizado; la implementación actual usa tasa libre de riesgo cero.
- Drawdown: \(V_t/\max_{u\le t}V_u-1\); máximo drawdown es el mínimo de esa trayectoria.
- VaR/CVaR históricos al 95%: cuantiles/cola empírica de pérdidas y retornos, sujetos a que la muestra represente adecuadamente la cola.
- Turnover anualizado: rotación media multiplicada por la frecuencia anual declarada.

Compare resultados solo si usan las mismas fechas, universo, benchmark, capital, costos, frecuencia y reglas de datos. El Sharpe máximo ex post puede premiar sobreajuste; seleccione hiperparámetros fuera de muestra y reporte estabilidad por subperiodos.

## 6. Fuentes de precios y construcción del panel

La aplicación descarga barras diarias desde Yahoo Finance mediante `yfinance` o desde el terminal MetaTrader 5 conectado a un bróker. También permite cargar CSV. No se precarga información de demostración. Los proveedores entregan datos para investigación: no son precios garantizados de ejecución ni una referencia única e inmutable.

Para Yahoo Finance se solicita `Ticker.history` con `auto_adjust=True`; el cierre usado por el motor refleja los ajustes históricos de acciones corporativas que expone el proveedor. Esto facilita calcular retornos comparables, aunque el proveedor puede revisar datos y sus límites de acceso o condiciones pueden cambiar. Para MetaTrader se usa `copy_rates_range` con `TIMEFRAME_D1`: el cierre y tick volume corresponden al historial disponible en el servidor del bróker. El tick volume cuenta cambios/actividad del precio y no debe interpretarse como volumen monetario centralizado. MetaTrader almacena las barras en UTC y la aplicación conserva la fecha UTC de cada barra.

Interfaces de referencia: [historial de precios en yfinance](https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/history.py), [copy_rates_range de MetaTrader 5](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py) y [conexión initialize de MetaTrader 5](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py).

La fecha final seleccionada se incluye en la consulta. Para formar el panel, los cierres y volúmenes se alinean por la intersección de fechas, se descartan observaciones con precio ausente y no se imputan precios por arrastre. Así se evita crear retornos cero artificiales; a cambio, el periodo efectivo depende del calendario común de todos los instrumentos y puede acortarse con activos de mercados distintos. Se requieren al menos dos activos y dos fechas comunes.

El motor de backtest interpreta las filas como observaciones diarias y usa aproximadamente 21 sesiones por mes en sus ventanas. Por ello, el proveedor web expone frecuencia diaria. Al comparar resultados, registra fuente, símbolos exactos del proveedor/bróker, rango solicitado y rango efectivo de fechas. Los estados fundamentales continúan en CSV con fecha de corte explícita: ni el historial de barras de MT5 ni las cifras actuales de Yahoo sustituyen estados financieros point-in-time con fechas de publicación/vintages.

## 7. Controles de calidad y prevención de sesgo

Antes de aceptar un universo real, documenta si los precios están ajustados, moneda y zona horaria, fechas de publicación, tratamiento de activos desaparecidos, universo conocido en cada fecha, faltantes y acciones corporativas. Para fundamentales, crea vintages y fechas de disponibilidad antes de habilitarlos en un backtest. Aplique validación walk-forward, costos conservadores, análisis de sensibilidad, pruebas unitarias de fórmulas y controles de pesos/sumas. Mantenga una muestra final de evaluación sin usar para selección de parámetros.

## 8. Referencias para profundización

- Jegadeesh, N. y Titman, S. (1993). *Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency*. Journal of Finance, 48(1), 65–91.
- Frazzini, A. y Pedersen, L. H. (2014). *Betting Against Beta*. Journal of Financial Economics, 111(1), 1–25.
- Markowitz, H. (1952). *Portfolio Selection*. Journal of Finance, 7(1), 77–91.
- López de Prado, M. (2016). *Building Diversified Portfolios that Outperform Out of Sample*. Journal of Portfolio Management, 42(4), 59–69. (HRP).
- Altman, E. I. (1968). *Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy*. Journal of Finance, 23(4), 589–609.
- Piotroski, J. D. (2000). *Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers*. Journal of Accounting Research, 38, 1–41.
- Beneish, M. D. (1999). *The Detection of Earnings Manipulation*. Financial Analysts Journal, 55(5), 24–36.
- Fama, E. F. y French, K. R. (1993). *Common Risk Factors in the Returns on Stocks and Bonds*. Journal of Financial Economics, 33(1), 3–56.
- Fama, E. F. y French, K. R. (2015). *A Five-Factor Asset Pricing Model*. Journal of Financial Economics, 116(1), 1–22.

Las implementaciones y configuraciones concretas se definen en el código y pruebas de `quant_core`; esta guía describe el marco conceptual y sus límites, no una promesa de desempeño.
