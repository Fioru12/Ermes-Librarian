import { Settings, ShieldCheck } from 'lucide-react'
import { Card, CardTitle } from '../ui'
import ProvidersTab from '../providers/ProvidersTab'

interface SettingsTabProps {
  showNotif: (msg: string, type?: 'success' | 'error') => void
  isAdmin?: boolean
}

export default function SettingsTab({ showNotif, isAdmin = false }: SettingsTabProps) {

  return (
    <div className="p-8 h-full overflow-y-auto space-y-8">
      <div className="flex items-center gap-3 mb-6">
        <Settings className="w-6 h-6 text-blue-400" />
        <h1 className="text-xl font-bold">Impostazioni Sistema</h1>
      </div>

      {/* Informazioni affidabili, non impostazioni non persistenti. */}
      <Card>
        <CardTitle><ShieldCheck className="w-4 h-4 text-emerald-400" /> Configurazione dell'istanza</CardTitle>
        <div className="mt-4 grid gap-3 text-sm text-slate-400 sm:grid-cols-2">
          <p className="rounded-lg border border-white/5 bg-white/[0.02] p-3"><span className="block text-xs font-semibold uppercase tracking-wide text-slate-500">Dati</span><span className="mt-1 block text-slate-300">Biblioteche e file restano nell'istanza locale.</span></p>
          <p className="rounded-lg border border-white/5 bg-white/[0.02] p-3"><span className="block text-xs font-semibold uppercase tracking-wide text-slate-500">AI cloud</span><span className="mt-1 block text-slate-300">Disponibile solo quando autorizzata per una biblioteca.</span></p>
        </div>
      </Card>

      {isAdmin ? <ProvidersTab showNotif={showNotif} /> : <Card><CardTitle>Provider LLM</CardTitle><p className="mt-3 text-sm leading-6 text-slate-400">La configurazione dei provider è riservata agli amministratori dell'istanza.</p></Card>}
    </div>
  )
}
