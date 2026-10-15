# Quant Portfolio Lab

Aplicación local para ejecutar, inspeccionar y contrastar métodos de selección y asignación implementados en `quant_core`. Se mantiene como proyecto hermano de la librería para que la interfaz no contamine su dominio ni sus dependencias.

## Arquitectura

- `backend/`: API REST con FastAPI. Orquesta los casos de uso y usa directamente los modelos de `quant_core`.
- `frontend/`: interfaz React + TypeScript + Vite. Dibuja curvas de capital y drawdown con SVG responsivo.
- `../quant_core`: librería instalada en modo editable desde el proyecto hermano; los cambios al core se reflejan sin copiar código.

La aplicación ofrece tres flujos: backtest histórico de señales calculables con precios/volúmenes, screening fundamental transversal a una fecha de corte y recomendaciones derivadas de la última comparación ejecutada. Los estados contables no se proyectan retrospectivamente en el backtest porque hacerlo sin vintages históricos causaría sesgo de anticipación.

## Requisitos

- Python 3.11 o superior.
- Node.js 22 o superior.
- `uv` para administrar el entorno de Python y `pnpm` (o npm) para el frontend.

## Instalación y ejecución

Desde el directorio `quant_portfolio_app`:

```powershell
$env:PYTHONPATH = (Resolve-Path ..\quant_core\src).Path
uv sync --extra dev
uv run uvicorn app.main:app --app-dir backend --reload
```

En otra terminal:

```powershell
cd frontend
pnpm install
pnpm dev
```

Abre <http://127.0.0.1:5173>. La API queda en <http://127.0.0.1:8000>, con documentación OpenAPI en <http://127.0.0.1:8000/docs>. La interfaz inicia sin precios precargados: selecciona proveedor, símbolos y fechas, y descarga el histórico antes de ejecutar un backtest.

Para la primera instalación sin `uv`, crea un entorno Python 3.11, instala `-e ..\quant_core` y las dependencias declaradas en `pyproject.toml`.

## Datos de entrada

### Precios y volúmenes

La aplicación puede descargar barras diarias desde Yahoo Finance (`yfinance`) o desde el terminal de MetaTrader 5. También acepta CSV ancho: una observación por fecha, columna `Date` o `Fecha`, y una columna por activo. Las fechas deben ser únicas y ascendidas. Los precios deben ser positivos. El archivo opcional de volúmenes debe usar los mismos activos, fechas y orden; los volúmenes no pueden ser negativos.

En la interfaz elige el proveedor, escribe los símbolos tal como los reconoce y configura el periodo. Yahoo Finance usa precios diarios ajustados por splits y dividendos; es un cliente de terceros del servicio de Yahoo, sujeto a disponibilidad, cambios y límites del proveedor. MetaTrader 5 consulta el historial diario disponible para el bróker conectado: instala y abre MetaTrader 5, inicia sesión y verifica los símbolos en ese terminal. No se envían órdenes. El tick volume de MT5 es un conteo de actividad, no volumen monetario negociado.

El panel final usa la intersección de fechas con precios válidos para todos los símbolos, sin rellenar días faltantes con precios repetidos. Esto evita retornos artificiales, pero puede reducir las observaciones al mezclar mercados con calendarios diferentes. Los indicadores de estados financieros siguen entrando por CSV: Yahoo no entrega vintages históricos que permitan evitar sesgo de anticipación, y MetaTrader es una fuente de barras de mercado, no de estados contables.

```csv
Date,SPY,AAA,BBB
2024-01-02,100.00,25.40,71.30
2024-01-03,100.72,25.61,70.88
```

Si se elige un benchmark, se excluye del universo invertible y se muestra como referencia. El backtest rebalancea mensualmente al cierre disponible y ejecuta el nuevo objetivo desde la siguiente sesión (`execution_lag=1`). El costo configurado se descuenta de la rotación de pesos.

### Datos fundamentales

Una fila por empresa; el identificador puede llamarse `Asset`, `Ticker`, `Symbol` o `Activo`. El nombre de cada columna financiera debe coincidir con el contrato de `quant_core`. Se incluyen nombres y ecuaciones en [la guía técnica](docs/GUIA_TECNICA.md). Los datos deben corresponder a la misma fecha de corte y escala monetaria; valores ausentes permanecen ausentes y no se rellenan con cero.

## Métodos expuestos

**Selección por series de precios:** Momentum configurable (12–1 por defecto), beta baja, rotación sectorial, selección por clusters y momentum con filtro de liquidez. La pestaña Recomendaciones ordena los portafolios comparados por crecimiento anualizado histórico sujeto a un límite de volatilidad, Sharpe y volatilidad mínima.

**Asignación:** igual ponderación, volatilidad inversa, ponderación por ranking, mínima varianza, máximo Sharpe, HRP y risk parity. La aplicación aplica el máximo peso configurado y permite una cartera parcialmente en efectivo cuando la cantidad de activos no permite invertir el 100% bajo ese límite.

**Screening fundamental:** Altman Z/Z′/Z″, Piotroski F-score, Beneish M-score, screening multifactor y ordenamiento por características de Fama–French. Este último requiere `market_cap` y `book_equity` o `pb_ratio`; la app incluye una plantilla descargable. Es una clasificación transversal de características, no una réplica de los retornos oficiales de factores Fama–French ni un backtest con fundamentales históricos.

## Validación y pruebas

```powershell
$env:PYTHONPATH = (Resolve-Path ..\quant_core\src).Path
uv run ruff check backend
uv run pytest
cd frontend
pnpm lint
pnpm build
```

El conjunto de pruebas del core cubre señales configurables de Momentum, métodos de selección, asignación y flujos integrados. Las pruebas de API cubren catálogo, datos, combinaciones de backtest y modelos de selección fundamental, incluido Fama–French.

## Alcance académico y límites

La interfaz es un laboratorio de investigación, no una recomendación de inversión. Las fuentes históricas pueden cambiar, limitar solicitudes o tener diferencias con precios ejecutables. Backtests con barras diarias no modelan impuestos, impacto de mercado, suspensiones, survivorship bias ni disponibilidad point-in-time del universo. Los resultados dependen de los símbolos, proveedor, periodo y parámetros; las métricas históricas no garantizan resultados futuros.

Consulta [la guía técnica y metodológica](docs/GUIA_TECNICA.md) para fórmulas, supuestos, formatos de datos y referencias de estudio.
