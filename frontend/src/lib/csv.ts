import Papa from 'papaparse'
import type { PricePanel } from './types'

type Row = Record<string, string>

function parseRows(file: File): Promise<Row[]> {
  return new Promise((resolve, reject) => {
    Papa.parse<Row>(file, {
      header: true,
      dynamicTyping: false,
      skipEmptyLines: 'greedy',
      complete: ({ data, errors, meta }) => {
        if (errors.length) return reject(new Error(errors[0]?.message ?? 'Error al leer el CSV.'))
        if (!meta.fields?.length || !data.length) return reject(new Error('El CSV está vacío o no tiene encabezados.'))
        resolve(data)
      },
      error: (error) => reject(error),
    })
  })
}

function dateColumn(headers: string[]) {
  return headers.find((name) => ['date', 'fecha', 'datetime', 'timestamp'].includes(name.trim().toLowerCase()))
}

function numeric(value: string | undefined, field: string, row: number): number {
  if (value === undefined || value.trim() === '') throw new Error(`Dato vacío en ${field}, fila ${row}.`)
  const parsed = Number(value.trim())
  if (!Number.isFinite(parsed)) throw new Error(`Dato no numérico en ${field}, fila ${row}.`)
  return parsed
}

function parseDate(value: string | undefined, row: number): string {
  const raw = value?.trim() ?? ''
  const isoDate = raw.match(/^(\d{4}-\d{2}-\d{2})(?:$|[T ])/)?.[1]
  if (!isoDate || Number.isNaN(Date.parse(`${isoDate}T00:00:00Z`))) {
    throw new Error(`Fecha inválida en fila ${row}; utiliza AAAA-MM-DD.`)
  }
  return isoDate
}

export async function parsePriceCsv(file: File, volumeFile?: File): Promise<PricePanel> {
  const rows = await parseRows(file)
  const headers = Object.keys(rows[0] ?? {})
  const dateKey = dateColumn(headers)
  if (!dateKey) throw new Error('El CSV de precios debe incluir una columna Date o Fecha.')
  const assets = headers.filter((header) => header !== dateKey && header.trim())
  if (assets.length < 2) throw new Error('Incluye por lo menos dos columnas de activos además de la fecha.')
  const dates = rows.map((row, index) => parseDate(row[dateKey], index + 2))
  if (dates.some((date, index) => index > 0 && date <= dates[index - 1]!)) throw new Error('Las fechas deben estar ordenadas y no repetirse.')
  const prices = Object.fromEntries(assets.map((asset) => [asset.trim(), rows.map((row, index) => numeric(row[asset], asset, index + 2))]))
  let volumes: Record<string, number[]> | undefined
  if (volumeFile) {
    const volumeRows = await parseRows(volumeFile)
    const volumeHeaders = Object.keys(volumeRows[0] ?? {})
    const volumeDateKey = dateColumn(volumeHeaders)
    if (!volumeDateKey || volumeRows.length !== rows.length) throw new Error('El CSV de volúmenes debe tener las mismas filas y fechas que precios.')
    const volumeDates = volumeRows.map((row, index) => parseDate(row[volumeDateKey], index + 2))
    if (volumeDates.some((date, index) => date !== dates[index])) throw new Error('Las fechas de volúmenes no coinciden con las de precios.')
    volumes = Object.fromEntries(assets.map((asset) => {
      if (!volumeHeaders.includes(asset)) throw new Error(`Falta la columna de volumen para ${asset}.`)
      return [asset.trim(), volumeRows.map((row, index) => numeric(row[asset], asset, index + 2))]
    }))
  }
  return { dates, prices, volumes }
}

export async function parseFundamentalsCsv(file: File) {
  const rows = await parseRows(file)
  const headers = Object.keys(rows[0] ?? {})
  const assetKey = headers.find((name) => ['asset', 'ticker', 'symbol', 'activo', 'emisora'].includes(name.trim().toLowerCase()))
  if (!assetKey) throw new Error('El CSV fundamental debe tener una columna Asset, Ticker, Symbol o Activo.')
  const fundamentals: Record<string, Record<string, string | number | null>> = {}
  rows.forEach((row, index) => {
    const asset = row[assetKey]?.trim()
    if (!asset) throw new Error(`Falta el identificador del activo en la fila ${index + 2}.`)
    if (fundamentals[asset]) throw new Error(`El activo ${asset} está repetido.`)
    const fields: Record<string, string | number | null> = {}
    for (const key of headers.filter((header) => header !== assetKey)) {
      const value = row[key]?.trim() ?? ''
      if (!value) { fields[key] = null; continue }
      const number = Number(value)
      fields[key] = Number.isFinite(number) ? number : value
    }
    fundamentals[asset] = fields
  })
  return fundamentals
}
