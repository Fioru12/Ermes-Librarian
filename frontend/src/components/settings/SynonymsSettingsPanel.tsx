import { useState, useEffect } from 'react'
import { BookOpen, Plus, Trash2, RefreshCw, ChevronDown, ChevronUp, Tag } from 'lucide-react'
import { Card, CardTitle, Button, Input } from '../ui'

interface SynonymsSettingsPanelProps {
  showNotif: (msg: string, type?: 'success' | 'error') => void
  isAdmin?: boolean
}

export default function SynonymsSettingsPanel({ showNotif, isAdmin = false }: SynonymsSettingsPanelProps) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [customSynonyms, setCustomSynonyms] = useState<Record<string, string[]>>({})
  const [allSynonyms, setAllSynonyms] = useState<Record<string, string[]>>({})
  const [showBuiltin, setShowBuiltin] = useState(false)

  // Form stato
  const [newTerm, setNewTerm] = useState('')
  const [newSynonyms, setNewSynonyms] = useState('')
  const [searchTerm, setSearchTerm] = useState('')

  const fetchSynonyms = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/synonyms')
      if (!res.ok) throw new Error('Errore nel caricamento dei sinonimi')
      const data = await res.json()
      setCustomSynonyms(data.custom || {})
      setAllSynonyms(data.all || {})
    } catch (err: any) {
      showNotif(err.message || 'Impossibile caricare il glossario aziendale', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSynonyms()
  }, [])

  const handleAddSynonym = async (e: React.FormEvent) => {
    e.preventDefault()
    const cleanTerm = newTerm.trim().toLowerCase()
    const cleanSyns = newSynonyms
      .split(',')
      .map(s => s.trim().toLowerCase())
      .filter(s => s && s !== cleanTerm)

    if (!cleanTerm) {
      showNotif('Inserisci un termine o acronimo valido', 'error')
      return
    }
    if (cleanSyns.length === 0) {
      showNotif('Inserisci almeno un sinonimo valido separato da virgola', 'error')
      return
    }

    setSaving(true)
    try {
      const res = await fetch('/api/synonyms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ term: cleanTerm, synonyms: cleanSyns }),
      })
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Errore nel salvataggio del sinonimo')
      }
      showNotif(`Termine "${cleanTerm}" aggiunto al glossario!`, 'success')
      setNewTerm('')
      setNewSynonyms('')
      await fetchSynonyms()
    } catch (err: any) {
      showNotif(err.message || 'Errore durante il salvataggio', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteSynonym = async (term: string) => {
    if (!confirm(`Rimuovere il termine "${term}" dai sinonimi personalizzati?`)) return
    try {
      const res = await fetch(`/api/synonyms/${encodeURIComponent(term)}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error('Errore nella cancellazione del termine')
      showNotif(`Termine "${term}" rimosso`, 'success')
      await fetchSynonyms()
    } catch (err: any) {
      showNotif(err.message || 'Errore durante la rimozione', 'error')
    }
  }

  const customEntries = Object.entries(customSynonyms).filter(([term, syns]) => {
    if (!searchTerm) return true
    const q = searchTerm.toLowerCase()
    return term.toLowerCase().includes(q) || syns.some(s => s.toLowerCase().includes(q))
  })

  const builtinEntries = Object.entries(allSynonyms)
    .filter(([term]) => !(term in customSynonyms))
    .filter(([term, syns]) => {
      if (!searchTerm) return true
      const q = searchTerm.toLowerCase()
      return term.toLowerCase().includes(q) || syns.some(s => s.toLowerCase().includes(q))
    })

  return (
    <Card>
      <div className="flex items-center justify-between gap-4 mb-4">
        <CardTitle>
          <BookOpen className="w-5 h-5 text-indigo-400" /> Glossario Aziendale & Sinonimi Dinamici
        </CardTitle>
        <button
          type="button"
          onClick={fetchSynonyms}
          disabled={loading}
          className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-white/5 transition disabled:opacity-50 cursor-pointer"
          title="Aggiorna glossario"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <p className="text-sm text-slate-400 mb-6 leading-relaxed">
        Configura acronimi, abbreviazioni e terminologie aziendali specifiche per la tua organizzazione. 
        Il motore di ricerca espanderà automaticamente le domande degli utenti per massimizzare il recupero dei documenti corretti.
      </p>

      {/* Badges conteggio */}
      <div className="flex flex-wrap gap-3 mb-6">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs font-medium text-indigo-300">
          <Tag className="w-3.5 h-3.5" /> {Object.keys(customSynonyms).length} Termini Personalizzati
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-slate-400">
          {Object.keys(allSynonyms).length} Totale Termini Attivi
        </span>
      </div>

      {/* Form Aggiunta Sinonimo (Admin/Editor) */}
      {isAdmin ? (
        <form onSubmit={handleAddSynonym} className="mb-6 rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Aggiungi nuovo termine o acronimo
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Termine / Acronimo</label>
              <Input
                value={newTerm}
                onChange={e => setNewTerm(e.target.value)}
                placeholder="es. DDT, WFH, CIG..."
                disabled={saving}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1">Sinonimi / Espansioni (separati da virgola)</label>
              <Input
                value={newSynonyms}
                onChange={e => setNewSynonyms(e.target.value)}
                placeholder="es. documento di trasporto, bolla di consegna"
                disabled={saving}
              />
            </div>
          </div>
          <div className="flex justify-end">
            <Button type="submit" disabled={saving || !newTerm.trim() || !newSynonyms.trim()}>
              <Plus className="w-4 h-4 mr-1.5" /> {saving ? 'Salvataggio…' : 'Aggiungi al Glossario'}
            </Button>
          </div>
        </form>
      ) : (
        <div className="mb-6 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-300">
          La modifica del glossario è riservata agli amministratori o editor dell'istanza.
        </div>
      )}

      {/* Barra di ricerca filtri */}
      <div className="mb-4">
        <Input
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          placeholder="Cerca nel glossario per termine o sinonimo…"
        />
      </div>

      {/* Lista Termini Personalizzati */}
      <div className="space-y-3">
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
          Termini Personalizzati ({customEntries.length})
        </div>
        {loading ? (
          <div className="text-center py-6 text-sm text-slate-500">Caricamento glossario…</div>
        ) : customEntries.length === 0 ? (
          <div className="rounded-lg border border-white/5 bg-white/[0.01] p-6 text-center text-sm text-slate-500">
            {searchTerm ? 'Nessun termine personalizzato corrisponde alla ricerca.' : 'Nessun termine personalizzato configurato. Aggiungine uno sopra!'}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {customEntries.map(([term, syns]) => (
              <div
                key={term}
                className="flex items-start justify-between gap-3 rounded-xl border border-indigo-500/20 bg-indigo-500/[0.03] p-3.5 transition hover:border-indigo-500/40"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-indigo-300 uppercase tracking-wide text-xs">{term}</span>
                    <span className="text-[10px] rounded bg-indigo-500/20 px-1.5 py-0.5 text-indigo-300 font-mono">custom</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {syns.map(s => (
                      <span
                        key={s}
                        className="rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-xs text-slate-300"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
                {isAdmin && (
                  <button
                    type="button"
                    onClick={() => handleDeleteSynonym(term)}
                    className="text-slate-500 hover:text-rose-400 p-1 rounded-lg hover:bg-rose-500/10 transition cursor-pointer"
                    title={`Elimina ${term}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sezione Termini di Sistema Built-In */}
      <div className="mt-8 pt-6 border-t border-white/10">
        <button
          type="button"
          onClick={() => setShowBuiltin(!showBuiltin)}
          className="flex items-center justify-between w-full text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-white transition cursor-pointer"
        >
          <span>Termini Standard Predefiniti di Sistema ({builtinEntries.length})</span>
          {showBuiltin ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>

        {showBuiltin && (
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            {builtinEntries.map(([term, syns]) => (
              <div
                key={term}
                className="rounded-xl border border-white/5 bg-white/[0.01] p-3 transition hover:border-white/10"
              >
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-300 uppercase tracking-wide text-xs">{term}</span>
                  <span className="text-[10px] rounded bg-white/5 px-1.5 py-0.5 text-slate-400 font-mono">built-in</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {syns.map(s => (
                    <span
                      key={s}
                      className="rounded-md border border-white/5 bg-white/[0.02] px-2 py-0.5 text-xs text-slate-400"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  )
}
