# Manual de usuario — Quant Portfolio Lab

## 1. Para qué sirve

Quant Portfolio Lab permite comparar métodos cuantitativos de selección y asignación de activos sobre precios históricos, ejecutar un screening fundamental transversal y revisar perfiles derivados de la última comparación.

La aplicación usa la librería local `quant_core` para los cálculos. Inicia sin precios precargados: debes descargar datos reales o cargar tus propios CSV. El screening fundamental usa la fecha de corte de los datos que entregues; no construye por sí solo un historial point-in-time.

La herramienta es un laboratorio de investigación. Sus resultados describen el periodo y los supuestos evaluados; no son pronósticos ni recomendaciones personalizadas de inversión.

## 2. Requisitos y puesta en marcha

Requisitos: Python 3.11 o superior, Node.js 22 o superior, `uv`, `pnpm` y acceso local al proyecto `quant_core`.

### Iniciar la API

Abre una terminal de PowerShell en la carpeta `quant_portfolio_app` y ejecuta:

    $env:PYTHONPATH = (Resolve-Path ..\quant_core\src).Path
    uv sync --extra dev
    uv run uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

Mantén esta terminal abierta. La documentación interactiva de la API está en http://127.0.0.1:8000/docs.

### Iniciar la interfaz

Abre otra terminal en `quant_portfolio_app`:

    Set-Location frontend
    pnpm install
    pnpm dev

Abre la dirección que muestre Vite; normalmente es http://127.0.0.1:5173. La barra superior debe indicar “API conectada”. Para apagar cada proceso, usa Ctrl+C en su terminal.

En PowerShell, si ya estás dentro de `frontend`, no repitas `Set-Location frontend`; ejecuta directamente `pnpm dev`.

## 3. Comparación y backtest

La primera pestaña es **Backtest y comparación**. Organiza el trabajo en tres etapas: cargar datos, elegir métodos y comparar los portafolios.

### 3.1 Cargar precios

Elige una de estas fuentes:

- **Yahoo Finance:** escribe al menos dos símbolos reconocidos por Yahoo, por ejemplo `SPY, QQQ, IWM`, define las fechas y pulsa **Descargar precios diarios**. La fuente entrega cierres diarios ajustados por dividendos y splits, sujeto a la disponibilidad del servicio.
- **MetaTrader 5:** abre el terminal de escritorio, inicia sesión en tu bróker y confirma que los símbolos estén disponibles allí. Usa los nombres exactos del bróker, incluidos sufijos si los tiene. La aplicación consulta barras diarias; no envía órdenes. El tick volume es una medida de actividad y no equivale a volumen monetario negociado.
- **CSV:** carga un archivo de precios y, si vas a usar Momentum + liquidez, otro archivo de volúmenes. Luego pulsa **Validar y usar archivos**.

Para una descarga se requieren al menos dos símbolos. El panel de precios CSV admite entre 2 y 100 activos y entre 2 y 5.000 fechas. El panel debe incluir al menos dos activos invertibles; si seleccionas un benchmark, ese activo se excluye del universo invertible.

Formato ancho de precios: una fila por fecha y una columna por activo. La fecha puede llamarse Date, Fecha, DateTime o Timestamp. Usa fechas ordenadas, únicas y en formato AAAA-MM-DD; precios numéricos positivos y sin celdas vacías.

    Date,SPY,QQQ,IWM
    2024-01-02,472.65,408.12,195.34
    2024-01-03,470.42,409.01,194.77

Si cargas volúmenes, el CSV debe tener las mismas fechas, en el mismo orden, y las mismas columnas de activos. Los valores deben ser numéricos y no negativos. El CSV no debe incluir separadores de miles; usa punto para los decimales.

Al descargar varios instrumentos, la aplicación alinea sus históricos por fechas comunes y no rellena precios faltantes arrastrando el último valor. Por eso, el rango efectivo puede ser menor que el solicitado.

### 3.2 Benchmark y universo

El selector **Activo de referencia** ofrece los símbolos presentes en el panel. El benchmark se excluye de la cartera y se dibuja como referencia en la curva de capital. Si no eliges uno, no aparece una curva de referencia y el método Beta baja no podrá generar resultado; las demás combinaciones compatibles pueden ejecutarse.

Para que la comparación sea justa, usa la misma fuente, universo, periodo, benchmark y costos al contrastar diferentes métodos.

### 3.3 Métodos de selección

Puedes combinar los métodos disponibles con los esquemas de asignación:

| Método | Lectura práctica |
|---|---|
| Momentum | Ordena activos por retorno histórico. El valor inicial es 12–1: ventana de 12 meses y omisión del último mes. |
| Beta baja | Favorece activos con menor beta histórica; requiere que selecciones un benchmark. |
| Rotación sectorial | Selecciona los activos con mejor señal relativa de la ventana configurada. |
| Selección por clusters | Agrupa activos según patrones de retornos para limitar concentraciones en grupos similares. |
| Momentum + liquidez | Aplica momentum y usa volumen para filtrar liquidez; requiere volúmenes. |

Los campos **Ventana de señal** y **Meses de omisión** parametrizan Momentum y Momentum + liquidez. Por ejemplo, 12–1 compara el precio de hace aproximadamente 12 meses con el de hace aproximadamente un mes, dejando fuera el mes más reciente. El motor aproxima cada mes a 21 sesiones bursátiles.

**Activos objetivo** determina cuántos nombres intenta seleccionar en cada rebalanceo. Si hay pocos activos elegibles, la cartera puede contener menos. Las señales se generan en la última observación disponible de cada mes y el motor ejecuta el nuevo objetivo desde la sesión siguiente.

### 3.4 Esquemas de asignación

| Esquema | Qué hace |
|---|---|
| Igual ponderación | Reparte el peso por igual entre los activos seleccionados. |
| Volatilidad inversa | Da más peso a los activos con menor volatilidad histórica. |
| Peso por ranking | Asigna más peso a los activos mejor clasificados. |
| Mínima varianza | Busca una combinación de menor varianza usando retornos y covarianzas históricos. |
| Máximo Sharpe | Optimiza el Sharpe estimado con la muestra de retornos usada en cada rebalanceo. |
| HRP | Usa agrupación jerárquica para distribuir riesgo sin depender de una inversión matricial tradicional. |
| Risk parity | Busca repartir la contribución al riesgo entre activos. |

**Peso máximo por activo** limita la exposición individual. Si la suma de los máximos permitidos no alcanza 100% para la cantidad seleccionada, el remanente puede quedar en efectivo. **Costo (pb) por rebalanceo** descuenta el costo configurado según la rotación de la cartera; 100 puntos básicos equivalen a 1%. **Capital inicial** escala la curva de capital mostrada.

La comparación admite hasta 12 combinaciones entre métodos de selección y asignación. Por ejemplo, 3 selecciones × 4 asignaciones son 12 combinaciones.

### 3.5 Ejecutar e interpretar

Pulsa **Ejecutar comparación**. La vista presenta:

- **Evolución del capital:** trayectoria histórica después de los costos configurados.
- **Drawdown:** caída desde el máximo acumulado.
- **Tabla comparativa:** retorno total, CAGR, volatilidad anualizada, Sharpe, máximo drawdown, CVaR 95% y turnover anual.
- **Composición más reciente:** pesos objetivo del último rebalanceo generado.

CAGR, volatilidad, Sharpe y turnover se anualizan según la frecuencia diaria que usa el motor. El Sharpe compara retorno con variabilidad; interpreta el valor junto con el periodo, benchmark, costos y drawdown. No leas la ordenación de la tabla como una garantía de superioridad futura.

Si una combinación no puede ejecutarse pero otras sí, la aplicación conserva los resultados válidos y muestra una advertencia. Si no hay resultados, revisa el mensaje de error, la longitud del histórico, los activos válidos y los parámetros.

## 4. Selección fundamental

La pestaña **Selección fundamental** calcula puntajes para un conjunto de empresas en una fecha de corte. No descarga estados financieros: debes proporcionarlos en un CSV con una fila por activo.

El identificador puede llamarse Asset, Ticker, Symbol, Activo o Emisora. Los identificadores deben ser únicos. Usa los nombres de columnas documentados para el modelo elegido y expresa los valores contables en una escala monetaria coherente. Los datos faltantes no deben reemplazarse por cero; pueden impedir que se calcule el puntaje de una empresa.

Escoge el modelo, carga el CSV, configura **Número máximo de seleccionadas** y pulsa **Ejecutar selección**. **F-score mínimo** se aplica al modelo Piotroski; en los demás modelos no determina el corte de selección. La interfaz ofrece plantillas para Piotroski y Fama–French cuando eliges esos modelos. También puedes abrirlas directamente: [plantilla Piotroski](../frontend/public/ejemplo_piotroski.csv) y [plantilla Fama–French](../frontend/public/ejemplo_fama_french.csv).

| Modelo | Datos principales requeridos |
|---|---|
| Altman Z · manufactura pública | working_capital, retained_earnings, ebit, market_equity, total_liabilities, sales, total_assets |
| Altman Z′ · manufactura privada | Los anteriores, usando book_equity en lugar de market_equity. |
| Altman Z″ · no manufactura | working_capital, retained_earnings, ebit, book_equity, total_liabilities, total_assets |
| Piotroski F-score | Señales contables del periodo actual y anterior; descarga la plantilla para ver los encabezados exactos. El puntaje va de 0 a 9. |
| Beneish M-score | Variables contables del año actual y anterior; consulta la sección Beneish de la guía técnica para los encabezados y definiciones exactos. Un puntaje alto amerita revisión, no demuestra fraude. |
| Screening multifactor | Puede combinar múltiplos, calidad, rentabilidad y tamaño, por ejemplo pe_ratio, pb_ratio, ev_ebitda, ps_ratio, roe, roa, debt_to_equity, gross_margin, roic, operating_margin y market_cap. La pantalla actual recibe solo fundamentales, no precios. |
| Fama–French · características | Requiere market_cap y book_equity o pb_ratio. operating_profitability (o operating_income junto con book_equity) y asset_growth (o activos actuales/anteriores) refinan el score. |

La selección Fama–French de esta aplicación es un ordenamiento transversal por características de empresas. No replica las series oficiales de retornos de factores SMB, HML, RMW y CMA. Consulta la [guía técnica](GUIA_TECNICA.md) para las fórmulas, todos los campos y las limitaciones de cada método.

Los resultados muestran scores, ranking, clasificación y empresas seleccionadas. Un screening en una fecha no equivale a un backtest: para evaluar una estrategia con fundamentales históricos se necesitan estados financieros point-in-time con su fecha de publicación y versiones disponibles en cada fecha.

## 5. Recomendaciones de portafolio

La pestaña **Recomendaciones** usa los resultados de la última comparación ejecutada en la sesión actual. Si la vista aparece vacía, vuelve al backtest, carga datos y ejecuta una comparación.

El control **Volatilidad anual máxima** va de 5% a 60% y comienza en 25%. La página muestra tres perfiles:

1. **Mayor crecimiento bajo el límite:** mayor CAGR histórico entre los portafolios cuya volatilidad cumple el umbral.
2. **Mejor retorno ajustado por riesgo:** mayor Sharpe histórico entre los resultados, aunque puede exceder el umbral de volatilidad.
3. **Menor volatilidad:** menor volatilidad histórica entre los resultados; también puede superar el límite.

Las tarjetas incluyen métricas y una parte de la composición más reciente. Cambiar el límite vuelve a filtrar las métricas de la comparación existente; no recalcula el backtest. Si recargas el navegador, los resultados en memoria se pierden y tendrás que ejecutar la comparación otra vez.

Estas sugerencias describen el histórico probado. No estiman crecimiento futuro ni incorporan objetivos, restricciones o situación personal de un inversionista.

## 6. Flujo de trabajo sugerido

1. Define de antemano el universo, benchmark, periodo y fuente.
2. Carga datos y revisa la cantidad de observaciones y fechas efectivas.
3. Ejecuta un conjunto pequeño de métodos y asignaciones; amplíalo después.
4. Registra los parámetros, costos y fuente para poder repetir el análisis.
5. Compara rendimiento con volatilidad, drawdown, CVaR y turnover; no uses una única métrica.
6. Repite con periodos y supuestos alternativos y reserva datos fuera de muestra para evaluación.
7. Interpreta el resultado como investigación histórica, no como promesa de rentabilidad.

## 7. Solución de problemas

| Síntoma | Qué revisar |
|---|---|
| La interfaz dice “API desconectada” | Confirma que la terminal del backend siga ejecutándose en el puerto 8000 y abre http://127.0.0.1:8000/docs. Comprueba que PYTHONPATH apunta a la carpeta src de quant_core. |
| Yahoo Finance o MetaTrader aparece como no disponible | En la carpeta quant_portfolio_app ejecuta uv sync --extra dev. Para MetaTrader, abre el terminal e inicia sesión en el bróker antes de descargar. |
| Yahoo no encuentra un símbolo | Verifica el símbolo y el rango de fechas en Yahoo Finance; el proveedor puede cambiar disponibilidad o limitar solicitudes. |
| MetaTrader no obtiene barras | Confirma conexión del terminal, disponibilidad exacta del símbolo en el bróker y que exista historial diario para el periodo. |
| Error de validación al cargar precios | Revisa encabezado de fecha, fechas ISO ascendidas sin repetición, números positivos, activos distintos y ausencia de celdas vacías. Si cargas volúmenes, deben coincidir las fechas y los nombres de activos. |
| No se generaron rebalanceos | El periodo puede ser demasiado corto para la ventana; amplía el histórico o reduce la ventana. Verifica también que el método tenga datos requeridos, como volumen para Momentum + liquidez. |
| Una combinación falla parcialmente | Prueba esa combinación por separado y revisa si la muestra ofrece observaciones suficientes para el optimizador seleccionado. |
| Vite muestra errores de sintaxis como “Unexpected token ||=“ | Comprueba Node.js con node --version. La interfaz requiere Node.js 22 o superior; abre una terminal nueva después de actualizarlo. |
| El puerto local no puede abrirse | Cierra procesos que ocupen el puerto o prueba otro puerto local. Si cambias el puerto de la API, define VITE_API_BASE_URL en la terminal del frontend con la dirección base correspondiente antes de iniciar Vite. |

Si el backend no puede escuchar en el puerto 8000, puedes probar el 8001. Inicia el backend con:

    uv run uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8001

En la terminal del frontend, antes de iniciar o reiniciar Vite, define:

    $env:VITE_API_BASE_URL = "http://127.0.0.1:8001/api/v1"

La interfaz debe reiniciarse para que tome la nueva dirección.

## 8. Referencias internas

- [Guía técnica y metodológica](GUIA_TECNICA.md): fundamentos, ecuaciones, supuestos y referencias académicas.
- [README del proyecto](../README.md): arquitectura, requisitos y comandos de instalación.
