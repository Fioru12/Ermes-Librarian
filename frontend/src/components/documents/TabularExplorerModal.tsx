import { useEffect, useState } from 'react'
import { AlertCircle, Check, Copy, Database, Download, Play, Table, X } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { errorMessage } from '../../lib/errors'

interface ColumnInfo {
  name: string
  type: string
}

interface TabularSchemaResponse {
  document_id: string
  filename: string
  table_name: string
  columns: ColumnInfo[]
  row_count: number
  sample_rows: Record<string, unknown>[]
}

interface TabularQueryResponse {
  document_id: string
  columns: string[]
  rows: (string | number | null)[][]
  row_count: number
  execution_ms: number
  markdown_table: string
}

interface TabularExplorerModalProps {
  libraryId: string
  documentId: string
  filename: string
  onClose: () => void
}

export function TabularExplorerModal({
  libraryId,
  documentId,
  filename,
  onClose,
}: TabularExplorerModalProps) {
  const { t } = useTheme()
  const [activeTab, setActiveTab] = useState<'schema' | 'query'>('schema')
  const [loadingSchema, setLoadingSchema] = useState(true)
  const [schema, setSchema] = useState<TabularSchemaResponse | null>(null)
  const [schemaError, setSchemaError] = useState<string | null>(null)

  const [sqlQuery, setSqlQuery] = useState<string>('SELECT * FROM data LIMIT 25')
  const [executingQuery, setExecutingQuery] = useState(false)
  const [queryResult, setQueryResult] = useState<TabularQueryResponse | null>(null)
  const [queryError, setQueryError] = useState<string | null>(null)
  const [copiedMd, setCopiedMd] = useState(false)

  useEffect(() => {
    async function fetchSchema() {
      setLoadingSchema(true)
      setSchemaError(null)
      try {
        const resp = await fetch(`/api/libraries/${libraryId}/documents/${documentId}/schema`, {
          credentials: 'include',
        })
        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}))
          throw new Error(errData.detail || 'Impossibile recuperare lo schema del documento')
        }
        const data: TabularSchemaResponse = await resp.json()
        setSchema(data)
        setSqlQuery('SELECT * FROM data LIMIT 25')
      } catch (err) {
        setSchemaError(errorMessage(err))
      } finally {
        setLoadingSchema(false)
      }
    }
    fetchSchema()
  }, [libraryId, documentId])

  const handleExecuteQuery = async (queryToRun?: string) => {
    const q = queryToRun || sqlQuery
    if (!q.trim()) return

    setExecutingQuery(true)
    setQueryError(null)
    try {
      const resp = await fetch(`/api/libraries/${libraryId}/documents/${documentId}/query-table`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ query: q.trim() }),
      })
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}))
        throw new Error(errData.detail || 'Errore durante l\'esecuzione della query SQL')
      }
      const result: TabularQueryResponse = await resp.json()
      setQueryResult(result)
      setActiveTab('query')
    } catch (err) {
      setQueryError(errorMessage(err))
    } finally {
      setExecutingQuery(false)
    }
  }

  const handleExportCsv = () => {
    if (!queryResult || !queryResult.columns.length) return
    const csvLines = [
      queryResult.columns.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','),
      ...queryResult.rows.map(row =>
        row.map(cell => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(',')
      ),
    ]
    const blob = new Blob([csvLines.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `query_result_${filename.replace(/\.[^/.]+$/, '')}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  const handleCopyMarkdown = () => {
    if (!queryResult?.markdown_table) return
    navigator.clipboard.writeText(queryResult.markdown_table)
    setCopiedMd(true)
    setTimeout(() => setCopiedMd(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className={`relative flex flex-col w-full max-w-5xl h-[85vh] rounded-2xl border shadow-2xl overflow-hidden ${t.card}`}>
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4 bg-slate-950/20">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
              <Table className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-white truncate max-w-md">{filename}</h2>
                <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-xs font-medium text-blue-400 border border-blue-500/20">
                  SQL Sandboxed
                </span>
                {schema && (
                  <span className="text-xs text-slate-400">
                    {schema.row_count} righe · {schema.columns.length} colonne
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Esplora lo schema ed esegui query analitiche in sola lettura (SELECT, SUM, AVG, COUNT, GROUP BY).
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-white/10 hover:text-white transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center justify-between border-b px-6 py-2 bg-slate-950/10">
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab('schema')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition ${
                activeTab === 'schema'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <Database className="h-3.5 w-3.5" />
              <span>Schema & Campione</span>
            </button>
            <button
              onClick={() => setActiveTab('query')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition ${
                activeTab === 'query'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <Play className="h-3.5 w-3.5" />
              <span>Console SQL {queryResult ? `(${queryResult.row_count} righe)` : ''}</span>
            </button>
          </div>

          {activeTab === 'query' && queryResult && (
            <div className="flex items-center gap-2">
              <button
                onClick={handleCopyMarkdown}
                className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300 hover:bg-white/10 transition"
                title="Copia tabella Markdown"
              >
                {copiedMd ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                <span>{copiedMd ? 'Copiato!' : 'Copia MD'}</span>
              </button>
              <button
                onClick={handleExportCsv}
                className="flex items-center gap-1 rounded-lg border border-blue-500/30 bg-blue-500/10 px-2.5 py-1 text-xs font-medium text-blue-300 hover:bg-blue-500/20 transition"
              >
                <Download className="h-3.5 w-3.5" />
                <span>Esporta CSV</span>
              </button>
            </div>
          )}
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-hidden p-6 flex flex-col">
          {schemaError && (
            <div className="mb-4 flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{schemaError}</span>
            </div>
          )}

          {activeTab === 'schema' && (
            <div className="flex-1 overflow-y-auto space-y-6">
              {loadingSchema ? (
                <div className="flex flex-col items-center justify-center py-20 text-slate-400">
                  <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent mb-3" />
                  <p className="text-xs">Ispezione schema in corso...</p>
                </div>
              ) : schema ? (
                <>
                  {/* Columns Grid */}
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
                      Struttura Colonne ({schema.columns.length})
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5">
                      {schema.columns.map(col => (
                        <div
                          key={col.name}
                          className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] p-2.5"
                        >
                          <span className="text-xs font-medium text-slate-200 truncate" title={col.name}>
                            {col.name}
                          </span>
                          <span
                            className={`text-[10px] font-semibold px-2 py-0.5 rounded-md ${
                              col.type === 'INTEGER'
                                ? 'bg-purple-500/15 text-purple-300 border border-purple-500/20'
                                : col.type === 'REAL'
                                ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20'
                                : 'bg-blue-500/15 text-blue-300 border border-blue-500/20'
                            }`}
                          >
                            {col.type}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Sample Rows Table */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                        Anteprima Dati (Prime {schema.sample_rows.length} righe)
                      </h3>
                      <button
                        onClick={() => {
                          setSqlQuery('SELECT * FROM data LIMIT 50')
                          handleExecuteQuery('SELECT * FROM data LIMIT 50')
                        }}
                        className="text-xs text-blue-400 hover:text-blue-300 transition underline"
                      >
                        Interroga tabella completa →
                      </button>
                    </div>

                    <div className="overflow-x-auto rounded-xl border border-white/10 bg-slate-950/30">
                      <table className="w-full text-left text-xs text-slate-300 border-collapse">
                        <thead>
                          <tr className="border-b border-white/10 bg-white/5 font-semibold text-slate-200">
                            {schema.columns.map(c => (
                              <th key={c.name} className="px-3 py-2 whitespace-nowrap">
                                {c.name}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                          {schema.sample_rows.map((row, idx) => (
                            <tr key={idx} className="hover:bg-white/[0.02] transition">
                              {schema.columns.map(c => (
                                <td key={c.name} className="px-3 py-2 whitespace-nowrap truncate max-w-xs">
                                  {String(row[c.name] ?? '')}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          )}

          {activeTab === 'query' && (
            <div className="flex-1 flex flex-col gap-4 overflow-hidden">
              {/* SQL Editor */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-400">Query SQL (Nome tabella: `data`)</span>
                  <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
                    <span className="text-slate-500">Preset:</span>
                    <button
                      onClick={() => setSqlQuery('SELECT * FROM data LIMIT 50')}
                      className="px-2 py-0.5 rounded border border-white/10 hover:bg-white/5 text-blue-300"
                    >
                      Top 50
                    </button>
                    {schema?.columns && schema.columns.length > 0 && (
                      <button
                        onClick={() =>
                          setSqlQuery(
                            `SELECT ${schema.columns[0].name}, COUNT(*) as conteggio FROM data GROUP BY ${schema.columns[0].name} ORDER BY conteggio DESC`
                          )
                        }
                        className="px-2 py-0.5 rounded border border-white/10 hover:bg-white/5 text-purple-300"
                      >
                        Group By
                      </button>
                    )}
                  </div>
                </div>

                <div className="flex gap-2">
                  <textarea
                    value={sqlQuery}
                    onChange={e => setSqlQuery(e.target.value)}
                    placeholder="SELECT * FROM data WHERE ..."
                    rows={3}
                    className="flex-1 rounded-xl border border-white/10 bg-slate-950/60 p-3 font-mono text-xs text-white outline-none focus:border-blue-500 transition resize-none"
                  />
                  <button
                    onClick={() => handleExecuteQuery()}
                    disabled={executingQuery || !sqlQuery.trim()}
                    className="flex flex-col items-center justify-center gap-1 rounded-xl bg-blue-600 px-5 text-white font-medium text-xs hover:bg-blue-500 transition disabled:opacity-50 disabled:cursor-not-allowed shadow-md"
                  >
                    <Play className={`h-4 w-4 ${executingQuery ? 'animate-spin' : ''}`} />
                    <span>{executingQuery ? 'Esecuzione...' : 'Esegui'}</span>
                  </button>
                </div>
              </div>

              {queryError && (
                <div className="flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span>{queryError}</span>
                </div>
              )}

              {/* Query Results Table */}
              <div className="flex-1 overflow-hidden flex flex-col rounded-xl border border-white/10 bg-slate-950/30">
                {executingQuery ? (
                  <div className="flex flex-1 items-center justify-center text-slate-400 text-xs">
                    <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent mr-2" />
                    Elaborazione query nel sandbox SQLite...
                  </div>
                ) : queryResult ? (
                  <>
                    <div className="flex items-center justify-between border-b border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-400">
                      <span>{queryResult.row_count} record trovati</span>
                      <span className="font-mono text-[11px] text-emerald-400">
                        ⚡ {queryResult.execution_ms} ms
                      </span>
                    </div>
                    <div className="flex-1 overflow-auto">
                      <table className="w-full text-left text-xs text-slate-300 border-collapse">
                        <thead className="sticky top-0 bg-slate-900 border-b border-white/10">
                          <tr className="font-semibold text-slate-200">
                            {queryResult.columns.map(col => (
                              <th key={col} className="px-3 py-2 whitespace-nowrap">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                          {queryResult.rows.map((row, rIdx) => (
                            <tr key={rIdx} className="hover:bg-white/[0.02] transition">
                              {row.map((cell, cIdx) => (
                                <td key={cIdx} className="px-3 py-2 whitespace-nowrap truncate max-w-xs font-mono">
                                  {cell !== null ? String(cell) : <span className="text-slate-600 italic">null</span>}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-1 items-center justify-center text-slate-500 text-xs">
                    Esegui una query SQL per visualizzare i risultati.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
