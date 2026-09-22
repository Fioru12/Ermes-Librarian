import { useState, useEffect } from 'react'
import { ShieldCheck, ShieldAlert, RefreshCw, FileCheck } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { Card, CardTitle } from '../ui'

interface AuditEntry {
  seq_id?: number
  ts: string
  action: string
  actor: string
  detail: Record<string, unknown>
  prev_hash?: string
  entry_hash?: string
}

interface IntegrityReport {
  valid: boolean
  total_entries: number
  verified_entries: number
  corrupted_count: number
  head_hash: string
  integrity_status: string
}

export default function AuditLogs({ showNotif }: { showNotif: (m: string, t: 'success' | 'error') => void }) {
  const { t } = useTheme()
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [integrity, setIntegrity] = useState<IntegrityReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloadingReport, setDownloadingReport] = useState(false)

  const fetchLogs = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/audit/logs?limit=50', { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        setEntries(data.entries || [])
      }
      const verRes = await fetch('/api/audit/verify', { credentials: 'include' })
      if (verRes.ok) {
        setIntegrity(await verRes.json())
      }
    } catch {
      showNotif('Errore caricamento audit', 'error')
    } finally {
      setLoading(false)
    }
  }

  const downloadComplianceReport = async () => {
    setDownloadingReport(true)
    try {
      const res = await fetch('/api/audit/compliance-report?organization=Ermes%20Knowledge%20Enterprise', {
        credentials: 'include',
      })
      if (!res.ok) throw new Error('Errore durante la generazione del report')
      const data = await res.json()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `compliance_report_soc2_${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      showNotif('Report di conformità SOC 2 / ISO 27001 scaricato con successo', 'success')
    } catch {
      showNotif('Impossibile scaricare il report di conformità', 'error')
    } finally {
      setDownloadingReport(false)
    }
  }

  useEffect(() => {
    fetchLogs()
  }, [])

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <CardTitle>
          <ShieldCheck className="w-5 h-5 text-emerald-400" /> Audit Log Crittografico (SHA-256 Chained)
        </CardTitle>
        <div className="flex items-center gap-2">
          <button
            onClick={downloadComplianceReport}
            disabled={downloadingReport}
            className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-300 transition hover:bg-emerald-500/20 disabled:opacity-50 cursor-pointer"
            title="Scarica Certificato di Conformità SOC 2 / ISO 27001"
          >
            <FileCheck className="h-3.5 w-3.5" />
            <span>{downloadingReport ? 'Generazione...' : 'Scarica Report SOC 2 / GDPR'}</span>
          </button>
          <button
            onClick={fetchLogs}
            title="Verifica e Aggiorna Registro"
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white/5 hover:text-blue-400 cursor-pointer"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {integrity && (
        <div
          className={`mt-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border p-3.5 text-xs ${
            integrity.valid
              ? 'border-emerald-500/30 bg-emerald-500/5 text-emerald-200'
              : 'border-rose-500/30 bg-rose-500/5 text-rose-200'
          }`}
        >
          <div className="flex items-center gap-2.5">
            {integrity.valid ? (
              <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-400" />
            ) : (
              <ShieldAlert className="h-4 w-4 shrink-0 text-rose-400" />
            )}
            <div>
              <p className="font-semibold text-slate-100">
                {integrity.valid
                  ? 'Catena Crittografica Immutabile e Autentica'
                  : `Allerta Integrità: Rilevate ${integrity.corrupted_count} anomalie nella catena!`}
              </p>
              <p className="mt-0.5 text-slate-400">
                {integrity.verified_entries} su {integrity.total_entries} voci verificate matematicamente (SHA-256 + HMAC-SHA256).
              </p>
            </div>
          </div>
          {integrity.head_hash && integrity.head_hash !== '0'.repeat(64) && (
            <div className="rounded bg-black/30 border border-white/5 px-2 py-1 font-mono text-[10px] text-slate-400">
              Head Hash: <span className="text-blue-300">{integrity.head_hash.slice(0, 16)}...</span>
            </div>
          )}
        </div>
      )}

      <div className="mt-4 max-h-96 overflow-y-auto overflow-x-auto rounded-xl border border-white/5">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className={t.tableHeader}>
              <th className="p-2.5 font-semibold">Seq</th>
              <th className="p-2.5 font-semibold">Data e ora</th>
              <th className="p-2.5 font-semibold">Azione</th>
              <th className="p-2.5 font-semibold">Attore</th>
              <th className="p-2.5 font-semibold">Hash Catena</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && !loading && (
              <tr>
                <td colSpan={5} className="p-4 text-center text-slate-500">
                  Nessuna voce di audit ancora registrata.
                </td>
              </tr>
            )}
            {entries.map((entry, index) => (
              <tr key={index} className={`border-t ${t.tableRow}`}>
                <td className="p-2.5 font-mono text-slate-500 font-semibold">#{entry.seq_id ?? index + 1}</td>
                <td className="p-2.5 text-slate-400 whitespace-nowrap">
                  {new Date(entry.ts).toLocaleString('it-IT')}
                </td>
                <td className="p-2.5">
                  <span className="rounded-md bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 font-mono text-[11px] text-blue-300">
                    {entry.action}
                  </span>
                </td>
                <td className={`p-2.5 font-medium ${t.cardTitle}`}>{entry.actor}</td>
                <td className="p-2.5 font-mono text-[10px] text-slate-500">
                  {entry.entry_hash ? (
                    <span className="text-slate-400" title={`SHA256: ${entry.entry_hash}`}>
                      {entry.entry_hash.slice(0, 12)}...
                    </span>
                  ) : (
                    <span className="italic text-slate-600">legacy</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
