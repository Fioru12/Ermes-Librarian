import { useState, useEffect } from 'react'
import { ShieldCheck, ShieldAlert, RefreshCw } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { Card, CardTitle } from '../ui'

interface AuditEntry {
  ts: string
  action: string
  actor: string
  detail: Record<string, unknown>
}

export default function AuditLogs({ showNotif }: { showNotif: (m: string, t: 'success' | 'error') => void }) {
  const { t } = useTheme()
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [integrity, setIntegrity] = useState<{ tampered: number; integrity_ok: boolean } | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchLogs = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/audit/logs?limit=50')
      if (res.ok) {
        const data = await res.json()
        setEntries(data.entries || [])
      }
      const verRes = await fetch('/api/audit/verify')
      if (verRes.ok) setIntegrity(await verRes.json())
    } catch {
      showNotif('Errore caricamento audit', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchLogs() }, [])

  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle><ShieldCheck className="w-4 h-4 text-emerald-400" /> Audit log amministrativo</CardTitle>
        <button onClick={fetchLogs} title="Aggiorna" className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white/5 hover:text-blue-400">
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {integrity && (
        <div className={`mt-4 flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${integrity.integrity_ok ? 'border-emerald-800 bg-emerald-950/40 text-emerald-300' : 'border-rose-800 bg-rose-950/40 text-rose-300'}`}>
          {integrity.integrity_ok ? <ShieldCheck className="h-4 w-4 shrink-0" /> : <ShieldAlert className="h-4 w-4 shrink-0" />}
          {integrity.integrity_ok ? 'Integrità del log verificata (firma HMAC valida su ogni voce).' : `Attenzione: ${integrity.tampered} voci con firma non valida.`}
        </div>
      )}

      <div className="mt-4 max-h-96 overflow-y-auto overflow-x-auto rounded-xl border border-white/5">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className={t.tableHeader}>
              <th className="p-2.5 font-semibold">Data e ora</th>
              <th className="p-2.5 font-semibold">Azione</th>
              <th className="p-2.5 font-semibold">Attore</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && !loading && (
              <tr><td colSpan={3} className="p-4 text-center text-slate-500">Nessuna voce di audit ancora registrata.</td></tr>
            )}
            {entries.map((entry, index) => (
              <tr key={index} className={`border-t ${t.tableRow}`}>
                <td className="p-2.5 text-slate-400">{new Date(entry.ts).toLocaleString('it-IT')}</td>
                <td className="p-2.5"><span className="rounded-md bg-blue-500/10 px-2 py-0.5 font-mono text-xs text-blue-300">{entry.action}</span></td>
                <td className={`p-2.5 ${t.cardTitle}`}>{entry.actor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
