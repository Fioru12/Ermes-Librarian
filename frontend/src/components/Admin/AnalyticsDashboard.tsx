import { useEffect, useState } from 'react'
import {
  Activity,
  AlertCircle,
  Clock,
  Download,
  HelpCircle,
  RefreshCw,
  Search,
  ThumbsUp,
} from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'

interface AnalyticsSummary {
  period_days: number
  total_queries: number
  avg_latency_ms: number
  knowledge_gaps_count: number
  positive_feedback_rate: number
  total_feedback: number
  by_coverage: Record<string, number>
  top_libraries: Array<{ library_id: string; count: number }>
}

interface KnowledgeGap {
  query: string
  count: number
  library_id: string
  last_seen: string
  reason: string
  negative_feedback: number
}

interface AnalyticsDashboardProps {
  showNotif: (msg: string, type?: 'success' | 'error') => void
}

export default function AnalyticsDashboard({ showNotif }: AnalyticsDashboardProps) {
  const { t } = useTheme()
  const [days, setDays] = useState<number>(30)
  const [loading, setLoading] = useState<boolean>(true)
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [gaps, setGaps] = useState<KnowledgeGap[]>([])
  const [searchTerm, setSearchTerm] = useState('')

  const loadData = async () => {
    setLoading(true)
    try {
      const [summaryRes, gapsRes] = await Promise.all([
        fetch(`/api/analytics/overview?days=${days}`, { credentials: 'include' }),
        fetch(`/api/analytics/knowledge-gaps?days=${days}&limit=50`, { credentials: 'include' }),
      ])
      if (summaryRes.ok) {
        setSummary(await summaryRes.json())
      }
      if (gapsRes.ok) {
        const data = await gapsRes.json()
        setGaps(data.gaps || [])
      }
    } catch {
      showNotif('Impossibile caricare i dati di analytics', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [days])

  const filteredGaps = gaps.filter(
    (g) =>
      g.query.toLowerCase().includes(searchTerm.toLowerCase()) ||
      g.reason.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className={`text-2xl font-bold tracking-tight ${t.cardTitle}`}>
            Analytics & Knowledge Gaps
          </h2>
          <p className={`text-sm mt-1 ${t.cardDesc}`}>
            Monitora le query, la latenza e individua proattivamente le informazioni mancanti nei documenti.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className={`text-xs rounded-xl px-3 py-2 border outline-none font-medium ${t.sidebarInput}`}
          >
            <option value={7}>Ultimi 7 giorni</option>
            <option value={30}>Ultimi 30 giorni</option>
            <option value={90}>Ultimi 90 giorni</option>
          </select>
          <button
            onClick={() => window.open(`/api/analytics/export?days=${days}`, '_blank')}
            className={`flex items-center gap-1.5 text-xs font-semibold rounded-xl px-3 py-2 border hover:opacity-80 transition ${t.sidebarInput} text-blue-400`}
            title="Scarica report in formato CSV"
          >
            <Download className="w-4 h-4" /> Esporta CSV
          </button>
          <button
            onClick={loadData}
            disabled={loading}
            className={`p-2 rounded-xl border hover:opacity-80 transition ${t.sidebarInput}`}
            title="Ricarica metriche"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-blue-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Queries */}
        <div className={`p-5 rounded-2xl border ${t.card} relative overflow-hidden shadow-sm`}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Query Totali
            </span>
            <Activity className="w-5 h-5 text-blue-400" />
          </div>
          <p className="text-3xl font-bold mt-3 text-white">
            {summary ? summary.total_queries.toLocaleString() : '—'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">In {days} giorni</span>
        </div>

        {/* Avg Latency */}
        <div className={`p-5 rounded-2xl border ${t.card} relative overflow-hidden shadow-sm`}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Latenza Media
            </span>
            <Clock className="w-5 h-5 text-amber-400" />
          </div>
          <p className="text-3xl font-bold mt-3 text-white">
            {summary ? `${summary.avg_latency_ms} ms` : '—'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">Tempo ricerca + sintesi</span>
        </div>

        {/* Satisfaction Rate */}
        <div className={`p-5 rounded-2xl border ${t.card} relative overflow-hidden shadow-sm`}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Feedback Positivi
            </span>
            <ThumbsUp className="w-5 h-5 text-emerald-400" />
          </div>
          <p className="text-3xl font-bold mt-3 text-white">
            {summary ? `${summary.positive_feedback_rate}%` : '—'}
          </p>
          <span className="text-xs text-slate-400 mt-1 block">
            {summary ? `${summary.total_feedback} feedback registrati` : '0 valutazioni'}
          </span>
        </div>

        {/* Knowledge Gaps */}
        <div className={`p-5 rounded-2xl border ${t.card} relative overflow-hidden shadow-sm`}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-rose-400">
              Knowledge Gaps
            </span>
            <AlertCircle className="w-5 h-5 text-rose-400" />
          </div>
          <p className="text-3xl font-bold mt-3 text-white">
            {summary ? summary.knowledge_gaps_count : '—'}
          </p>
          <span className="text-xs text-rose-300/80 mt-1 block">Domande senza evidenza</span>
        </div>
      </div>

      {/* Knowledge Gaps Section */}
      <div className={`p-6 rounded-2xl border ${t.card} shadow-sm space-y-4`}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-purple-400" />
            <h3 className="text-base font-semibold text-white">
              Buchi di Conoscenza Rilevati ({filteredGaps.length})
            </h3>
          </div>
          <div className="relative w-full sm:w-64">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Filtra domande..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className={`w-full text-xs rounded-xl pl-9 pr-3 py-2 border outline-none ${t.sidebarInput}`}
            />
          </div>
        </div>

        <p className="text-xs text-slate-400">
          Queste sono le domande poste dagli utenti a cui Ermes non ha trovato evidenza nei documenti caricati. Caricare documenti su questi argomenti aumenterà la copertura del RAG.
        </p>

        {filteredGaps.length === 0 ? (
          <div className="text-center py-10 text-slate-400 text-sm">
            Nessun knowledge gap rilevato nel periodo selezionato.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className={`border-b ${t.tableHeader}`}>
                <tr>
                  <th className="py-3 px-4 font-semibold text-slate-300">Domanda Frequente</th>
                  <th className="py-3 px-4 font-semibold text-slate-300">Frequenza</th>
                  <th className="py-3 px-4 font-semibold text-slate-300">Motivo Esito</th>
                  <th className="py-3 px-4 font-semibold text-slate-300">Feedback Negativi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {filteredGaps.map((gap, idx) => (
                  <tr key={idx} className="hover:bg-white/[0.02] transition">
                    <td className="py-3 px-4 font-medium text-white max-w-md truncate" title={gap.query}>
                      {gap.query}
                    </td>
                    <td className="py-3 px-4">
                      <span className="inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        {gap.count} {gap.count === 1 ? 'volta' : 'volte'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-300 max-w-xs truncate" title={gap.reason}>
                      {gap.reason || 'Evidenza insufficiente'}
                    </td>
                    <td className="py-3 px-4">
                      {gap.negative_feedback > 0 ? (
                        <span className="inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                          👎 {gap.negative_feedback}
                        </span>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
