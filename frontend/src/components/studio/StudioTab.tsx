import { useEffect, useState } from 'react'
import { BookOpen, HelpCircle, ListChecks, MessageCircleQuestion, RefreshCw, Sparkles } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { Button, CardTitle } from '../ui'

export type StudioKind = 'briefing' | 'faq' | 'study_guide' | 'questions'

interface StudioItem {
  text: string
  question?: string
  section?: string
  citations: number[]
}

interface StudioSource {
  marker: number
  filename: string
  version: number
  locator: string
  excerpt: string
}

export interface StudioResult {
  kind: StudioKind
  status: 'answered' | 'abstained' | 'unavailable'
  reason: string
  items: StudioItem[]
  sources: StudioSource[]
  discarded: number
}

const KINDS: { kind: StudioKind; label: string; icon: typeof BookOpen; hint: string }[] = [
  { kind: 'briefing', label: 'Briefing', icon: BookOpen, hint: 'Cosa contiene la biblioteca, in cinque minuti' },
  { kind: 'faq', label: 'FAQ', icon: HelpCircle, hint: 'Le domande che farebbe un collega, con risposta' },
  { kind: 'study_guide', label: 'Guida di studio', icon: ListChecks, hint: 'I concetti chiave, per argomento' },
  { kind: 'questions', label: 'Domande suggerite', icon: MessageCircleQuestion, hint: 'Da cui partire, tutte con risposta nei documenti' },
]

interface Props {
  libraries: { id: string; name: string }[]
  selectedLibraryId: string
  onSelectLibrary: (id: string) => void
  onAsk: (question: string) => void
}

export default function StudioTab({ libraries, selectedLibraryId, onSelectLibrary, onAsk }: Props) {
  const { t } = useTheme()
  const [kind, setKind] = useState<StudioKind>('briefing')
  const [results, setResults] = useState<Partial<Record<StudioKind, StudioResult>>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [openSource, setOpenSource] = useState<StudioSource | null>(null)

  // Cambiare biblioteca invalida quanto generato: appartiene all'altra.
  useEffect(() => { setResults({}); setOpenSource(null); setError('') }, [selectedLibraryId])

  const generate = async (target: StudioKind) => {
    if (!selectedLibraryId) return
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/studio/${target}`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!response.ok) throw new Error(response.status === 429 ? 'Troppe richieste: riprova fra poco.' : 'Generazione non riuscita.')
      const data: StudioResult = await response.json()
      setResults(current => ({ ...current, [target]: data }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generazione non riuscita.')
    } finally {
      setLoading(false)
    }
  }

  const result = results[kind]
  const sourceFor = (marker: number) => result?.sources.find(s => s.marker === marker)
  const active = KINDS.find(k => k.kind === kind)!

  const citationChips = (item: StudioItem) => item.citations.map(marker => {
    const source = sourceFor(marker)
    return (
      <button
        key={marker}
        type="button"
        onClick={() => source && setOpenSource(source)}
        title={source ? `${source.filename} — ${source.locator}` : undefined}
        className="ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-md bg-blue-500/15 px-1 align-middle text-[10px] font-bold text-blue-300 hover:bg-blue-500/30"
      >
        {marker}
      </button>
    )
  })

  const body = () => {
    if (!result) return (
      <div className={`rounded-2xl border border-dashed p-10 text-center ${t.card}`}>
        <active.icon className="mx-auto h-8 w-8 text-blue-400" />
        <p className="mt-3 text-sm font-semibold">{active.label}</p>
        <p className={`mt-1 text-xs ${t.cardDesc}`}>{active.hint}</p>
        <Button className="mx-auto mt-5" onClick={() => generate(kind)} disabled={loading || !selectedLibraryId}>
          {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Genera
        </Button>
      </div>
    )
    if (result.status !== 'answered') return (
      <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-5 text-sm text-amber-200" role="status">
        {result.status === 'unavailable' ? 'Non disponibile: ' : 'Nessun contenuto affidabile: '}{result.reason}
      </div>
    )
    if (kind === 'questions') return (
      <ul className="space-y-2">
        {result.items.map(item => (
          <li key={item.text}>
            <button type="button" onClick={() => onAsk(item.text)} className={`w-full rounded-xl border px-4 py-3 text-left text-sm transition hover:border-blue-500/40 ${t.card}`}>
              {item.text}
            </button>
          </li>
        ))}
      </ul>
    )
    if (kind === 'faq') return (
      <dl className="space-y-4">
        {result.items.map(item => (
          <div key={`${item.question}-${item.text}`} className={`rounded-xl border p-4 ${t.card}`}>
            <dt className="text-sm font-semibold">{item.question}</dt>
            <dd className={`mt-1.5 text-sm leading-6 ${t.cardDesc}`}>{item.text}{citationChips(item)}</dd>
          </div>
        ))}
      </dl>
    )
    if (kind === 'study_guide') {
      const sections = [...new Set(result.items.map(item => item.section || ''))]
      return (
        <div className="space-y-5">
          {sections.map(section => (
            <section key={section}>
              {section && <h3 className="mb-2 text-sm font-semibold">{section}</h3>}
              <ul className="list-disc space-y-1.5 pl-5">
                {result.items.filter(item => (item.section || '') === section).map(item => (
                  <li key={item.text} className={`text-sm leading-6 ${t.cardDesc}`}>{item.text}{citationChips(item)}</li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )
    }
    return (
      <div className="space-y-4">
        {result.items.map(item => (
          <p key={item.text} className={`text-sm leading-7 ${t.cardDesc}`}>{item.text}{citationChips(item)}</p>
        ))}
      </div>
    )
  }

  return (
    <div className={`h-full overflow-y-auto p-6 lg:p-10 ${t.chatBg}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <CardTitle><Sparkles className="h-5 w-5 text-blue-400" />Studio della biblioteca</CardTitle>
        <select
          aria-label="Biblioteca"
          value={selectedLibraryId}
          onChange={event => onSelectLibrary(event.target.value)}
          className={`rounded-xl border px-3 py-2 text-sm ${t.sidebarInput}`}
        >
          {libraries.map(library => <option key={library.id} value={library.id}>{library.name}</option>)}
        </select>
      </div>
      <p className={`mt-2 max-w-2xl text-xs leading-5 ${t.cardDesc}`}>
        Generato solo dai documenti che puoi vedere. Ogni punto porta il numero della fonte: cliccalo per leggere il
        passaggio originale. I punti che il modello non ha saputo collegare a una fonte vengono scartati, non mostrati.
      </p>

      <div role="tablist" className="mt-6 flex flex-wrap gap-2">
        {KINDS.map(item => (
          <button
            key={item.kind}
            role="tab"
            aria-selected={kind === item.kind}
            onClick={() => { setKind(item.kind); setOpenSource(null) }}
            className={`flex items-center gap-2 rounded-xl border px-3.5 py-2 text-sm transition ${kind === item.kind ? 'border-blue-500/40 bg-blue-500/15 text-blue-200' : 'border-white/10 text-slate-400 hover:bg-white/5'}`}
          >
            <item.icon className="h-4 w-4" />{item.label}
          </button>
        ))}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div>
          {error && <p className="mb-4 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-300" role="alert">{error}</p>}
          {body()}
          {result && (
            <div className="mt-5 flex items-center gap-3">
              <Button variant="secondary" onClick={() => generate(kind)} disabled={loading}>
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Rigenera
              </Button>
              {result.discarded > 0 && (
                <span className={`text-xs ${t.cardDesc}`}>{result.discarded} punti scartati perché senza fonte valida</span>
              )}
            </div>
          )}
        </div>
        <aside className={`h-fit rounded-2xl border p-4 ${t.card}`} aria-label="Fonte">
          {openSource ? (
            <>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-300">Fonte {openSource.marker}</p>
              <p className="mt-1 text-sm font-semibold">{openSource.filename} <span className={`font-normal ${t.cardDesc}`}>v{openSource.version}</span></p>
              <p className={`text-xs ${t.cardDesc}`}>{openSource.locator}</p>
              <blockquote className={`mt-3 border-l-2 border-blue-500/40 pl-3 text-sm leading-6 ${t.cardDesc}`}>{openSource.excerpt}</blockquote>
            </>
          ) : (
            <p className={`text-xs leading-5 ${t.cardDesc}`}>Clicca un numero accanto a un punto per vedere il passaggio da cui viene.</p>
          )}
        </aside>
      </div>
    </div>
  )
}
