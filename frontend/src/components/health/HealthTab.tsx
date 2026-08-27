import { useState, useEffect } from 'react'
import { Activity, CheckCircle, XCircle, Server, Database, Cpu, RefreshCw } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { Card, CardTitle, Button, Badge } from '../../components/ui'

interface HealthStatus {
  status: string
  ollama_ok?: boolean
  openrouter_ok?: boolean
  library_db_ok?: boolean
  library_storage_ok?: boolean
  modules_available?: string[]
}

export default function HealthTab() {
  const { t } = useTheme()
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchHealth = async () => {
    setLoading(true)
    try {
      const res = await fetch('/health', { credentials: 'include' })
      if (res.ok) setHealth(await res.json())
    } catch { setHealth(null) }
    setLoading(false)
  }

  useEffect(() => { fetchHealth() }, [])

  const statusIcon = (s: string) => {
    if (!s) return <XCircle className="w-4 h-4 text-rose-500" />
    const status = s.toLowerCase()
    if (status === 'healthy' || status === 'ok') return <CheckCircle className="w-4 h-4 text-emerald-500" />
    if (status === 'degraded') return <CheckCircle className="w-4 h-4 text-amber-500" />
    return <XCircle className="w-4 h-4 text-rose-500" />
  }

  if (loading) return <div className={`flex-1 flex items-center justify-center ${t.chatBg}`}>
    <RefreshCw className="w-8 h-8 text-slate-500 animate-spin" />
  </div>

  if (!health) return <div className={`flex-1 flex items-center justify-center ${t.chatBg}`}>
    <p className="text-slate-500">Impossibile recuperare lo stato del sistema.</p>
  </div>

  return (
    <div className={`flex-1 overflow-y-auto p-6 lg:p-10 ${t.chatBg}`}>
      <CardTitle><Activity className="w-5 h-5 text-emerald-400" />Stato Sistema</CardTitle>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-6">
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Server className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-bold">API Server</span>
            {statusIcon(health.status)}
          </div>
          <p className={`text-xs ${t.cardDesc}`}>Stato: <span className="font-medium text-slate-300 capitalize">{health.status || 'unknown'}</span></p>
        </Card>
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Database className="w-4 h-4 text-purple-400" />
            <span className="text-sm font-bold">Documenti</span>
            {statusIcon(health.library_storage_ok ? 'healthy' : 'error')}
          </div>
          <p className={`text-xs ${t.cardDesc}`}>Stato: <span className="font-medium text-slate-300 capitalize">{health.library_storage_ok ? 'pronto' : 'non disponibile'}</span></p>
        </Card>
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Database className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-bold">Indice locale</span>
            {statusIcon(health.library_db_ok ? 'healthy' : 'error')}
          </div>
          <p className={`text-xs ${t.cardDesc}`}>Stato: <span className="font-medium text-slate-300 capitalize">{health.library_db_ok ? 'metadati SQLite pronti' : 'non disponibile'}</span></p>
        </Card>
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Cpu className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-bold">Provider LLM</span>
            {statusIcon(health.ollama_ok || health.openrouter_ok ? 'healthy' : 'degraded')}
          </div>
          <p className={`text-xs ${t.cardDesc}`}>Stato: <span className="font-medium text-slate-300 capitalize">{health.ollama_ok || health.openrouter_ok ? 'disponibile' : 'opzionale/non configurato'}</span></p>
        </Card>
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-4 h-4 text-rose-400" />
            <span className="text-sm font-bold">Generale</span>
            {statusIcon(health.status)}
          </div>
          <p className={`text-xs ${t.cardDesc}`}>Stato: <span className="font-medium text-slate-300 capitalize">{health.status || 'unknown'}</span></p>
        </Card>
      </div>

      {health.modules_available && health.modules_available.length > 0 && (
        <div className="mt-8">
          <CardTitle className="mb-4"><Database className="w-4 h-4 text-indigo-400" />Moduli RAG</CardTitle>
          <div className="space-y-2">
            {health.modules_available.map((name) => (
              <div key={name} className={`border rounded-xl px-4 py-3 flex items-center justify-between ${t.card}`}>
                <div className="flex items-center gap-2">
                  <Database className="w-3.5 h-3.5 text-blue-400" />
                  <span className="font-medium text-sm">{name}</span>
                </div>
                <div className="flex items-center gap-3">
                  <Badge color="blue">disponibile</Badge>
                  {statusIcon('healthy')}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8 flex justify-center">
        <Button variant="secondary" onClick={fetchHealth}>
          <RefreshCw className="w-3.5 h-3.5" /> Aggiorna
        </Button>
      </div>
    </div>
  )
}
