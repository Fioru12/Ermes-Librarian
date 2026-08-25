import { useRef, useEffect, useState } from 'react'
import { Send, Square, HelpCircle, ArrowRight, BookOpen, Files, ShieldCheck, Download, X } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { InlineMarkdown } from './InlineMarkdown'
import type { Message } from '../../types'

type Source = NonNullable<Message['sources']>[number]

/** Renderizza il testo della risposta trasformando i marcatori [1], [2]... in
 *  citazioni cliccabili che aprono la fonte corrispondente. */
function CitationText({ text, sources, onCitation }: {
  text: string
  sources: Source[]
  onCitation: (source: Source, marker: number) => void
}) {
  const parts = text.split(/(\[\d+\])/g)
  return (
    <span className="whitespace-pre-wrap">
      {parts.map((part, index) => {
        const match = part.match(/^\[(\d+)\]$/)
        if (!match) return <InlineMarkdown key={index} text={part} />
        const marker = Number(match[1])
        const source = sources.find(candidate => (candidate.marker ?? index) === marker)
        if (!source) return <span key={index}>{part}</span>
        return (
          <button
            key={index}
            type="button"
            onClick={() => onCitation(source, marker)}
            title={`${source.filename} · ${source.locator}`}
            className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full border border-blue-400/40 bg-blue-500/15 px-1 align-super text-[10px] font-semibold text-blue-300 transition hover:bg-blue-500/30 hover:text-blue-200"
          >
            {marker}
          </button>
        )
      })}
    </span>
  )
}

interface ChatAreaProps {
  messages: Message[]
  inputMessage: string
  onInputChange: (v: string) => void
  onSend: (text: string) => void
  onStop: () => void
  isGenerating: boolean
  suggestions: { title: string; desc: string; prompt: string }[]
  libraries?: Array<{ id: string; name: string }>
  selectedLibraryId?: string
  selectedLibraryDocumentCount?: number
  onLibraryChange?: (id: string) => void
  onOpenLibraries?: () => void
}

export default function ChatArea({
  messages, inputMessage, onInputChange, onSend, onStop,
  isGenerating, suggestions, libraries = [], selectedLibraryId = '', selectedLibraryDocumentCount = 0, onLibraryChange, onOpenLibraries,
}: ChatAreaProps) {
  const { t } = useTheme()
  const chatEndRef = useRef<HTMLDivElement>(null)
  const [activeCitation, setActiveCitation] = useState<{ source: Source; marker: number } | null>(null)

  useEffect(() => {
    if (typeof chatEndRef.current?.scrollIntoView === 'function') {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isGenerating])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!inputMessage.trim() || isGenerating) return
    onSend(inputMessage)
  }

  const needsLibrary = Boolean(onOpenLibraries) && (!selectedLibraryId || libraries.length === 0)
  const needsDocuments = Boolean(onOpenLibraries) && !needsLibrary && selectedLibraryDocumentCount === 0
  const selectedLibraryName = libraries.find(library => library.id === selectedLibraryId)?.name || 'Nessuna biblioteca selezionata'
  const onboardingTitle = needsLibrary ? 'Crea la prima biblioteca' : 'Aggiungi il primo documento'
  const onboardingDescription = needsLibrary
    ? 'Una biblioteca separa procedure, manuali e policy del tuo team. Poi potrai chiedere risposte con fonti verificabili.'
    : 'La biblioteca è pronta. Carica un PDF, DOCX, TXT o Markdown per iniziare a cercare e fare domande.'

  return (
    <div className={`flex flex-col h-full ${t.chatBg}`}>
      {/* Messages / Welcome */}
      {messages.length === 0 && (needsLibrary || needsDocuments) ? (
        <div className="flex-1 overflow-y-auto px-8 py-8 flex flex-col items-center justify-center max-w-2xl mx-auto space-y-6 w-full text-center">
          <div className="rounded-2xl border border-blue-500/20 bg-blue-500/5 p-7">
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-blue-400">Primo avvio</p>
            <h1 className={`mt-3 text-2xl font-bold tracking-tight ${t.welcomeTitle}`}>{onboardingTitle}</h1>
            <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-slate-400">{onboardingDescription}</p>
            <ol className="mx-auto mt-6 max-w-md space-y-3 text-left text-sm text-slate-300">
              <li className="flex gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-500/20 text-xs font-bold text-blue-300">1</span><span>Crea o seleziona una biblioteca.</span></li>
              <li className="flex gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-500/20 text-xs font-bold text-blue-300">2</span><span>Carica documenti che possono essere consultati dal team.</span></li>
              <li className="flex gap-3"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-500/20 text-xs font-bold text-blue-300">3</span><span>Fai una domanda e verifica sempre le fonti.</span></li>
            </ol>
            <button onClick={onOpenLibraries} className="mt-7 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-500">
              {needsLibrary ? 'Crea biblioteca' : 'Carica documento'}
            </button>
          </div>
          <p className="text-xs text-slate-500">Di default Ermes usa solo evidenze locali: nessun file viene inviato a un provider cloud.</p>
        </div>
      ) : messages.length === 0 ? (
        <div className="flex-1 overflow-y-auto px-6 py-8 flex flex-col items-center justify-center max-w-5xl mx-auto w-full">
          <div className="w-full rounded-[2rem] border border-white/[0.09] bg-slate-950/42 px-6 py-7 shadow-2xl shadow-slate-950/30 ermes-glass sm:px-9 sm:py-8">
          <div className="text-center space-y-3">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-blue-400/20 bg-blue-500/10 text-lg font-bold text-blue-300 shadow-lg shadow-blue-500/10">E</div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-400">Assistente documentale</p>
            <h1 className={`text-3xl font-semibold tracking-tight ${t.welcomeTitle}`}>Cosa vuoi trovare?</h1>
            <p className="text-sm text-slate-400 max-w-md mx-auto leading-relaxed">Chiedi informazioni sui documenti presenti nelle tue biblioteche.</p>
          </div>
          <div className="mt-7 grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-white/[0.07] bg-white/[0.035] p-3 text-left"><BookOpen className="h-4 w-4 text-blue-400" /><p className="mt-2 truncate text-xs font-semibold text-slate-200">{selectedLibraryName}</p><p className="mt-1 text-[11px] text-slate-500">Biblioteca selezionata</p></div>
            <div className="rounded-xl border border-white/[0.07] bg-white/[0.035] p-3 text-left"><Files className="h-4 w-4 text-violet-400" /><p className="mt-2 text-xs font-semibold text-slate-200">{selectedLibraryDocumentCount} documenti</p><p className="mt-1 text-[11px] text-slate-500">Disponibili per la ricerca</p></div>
            <div className="rounded-xl border border-emerald-400/10 bg-emerald-400/[0.035] p-3 text-left"><ShieldCheck className="h-4 w-4 text-emerald-400" /><p className="mt-2 text-xs font-semibold text-slate-200">Fonti verificate</p><p className="mt-1 text-[11px] text-slate-500">Risposte ancorate ai documenti</p></div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full mt-7">
            {suggestions.map((s, idx) => (
              <button key={idx} onClick={() => onSend(s.prompt)}
                className={`min-h-32 p-5 rounded-2xl border text-left flex flex-col justify-between transition-all group ${t.card}`}>
                <div className="space-y-1">
                  <h4 className={`text-sm font-bold flex items-center gap-1.5 ${t.cardTitle}`}>
                    <HelpCircle className="w-3.5 h-3.5 text-blue-500" /> {s.title}
                  </h4>
                  <p className={`text-xs leading-normal ${t.cardDesc}`}>{s.desc}</p>
                </div>
                <div className="mt-3 flex items-center gap-1 text-[11px] font-semibold text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity">
                  Invia suggerimento <ArrowRight className="w-3 h-3" />
                </div>
              </button>
            ))}
          </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-8 py-6 space-y-6">
          {messages.map(m => (
            <div key={m.id} className={`flex flex-col max-w-[85%] ${m.role === 'user' ? 'ml-auto items-end' : 'mr-auto items-start'}`}>
              <div className="text-[10px] text-slate-500 font-medium mb-1 px-1 flex items-center gap-1.5">
                <span className="font-bold uppercase tracking-wider">{m.role === 'user' ? 'Tu' : 'Ermes AI'}</span>
                <span>•</span>
                <span>{m.timestamp}</span>
              </div>
              <div className={`px-4 py-3 rounded-xl text-sm leading-relaxed border ${m.role === 'user' ? t.chatBubbleUser : t.chatBubbleAssistant}`}>
                {m.role === 'assistant' && m.evidence && (
                  <p className={`mb-2 text-xs font-medium ${m.evidence.coverage === 'supported' ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {m.evidence.coverage === 'supported' ? `Basata su ${m.sources?.length ?? 0} fonti` : 'Evidenza insufficiente'}
                    {m.evidence.reason ? ` - ${m.evidence.reason}` : ''}
                  </p>
                )}
                <div className="whitespace-pre-wrap">{m.role === 'assistant' && m.sources && m.sources.length > 0
                  ? <CitationText text={m.content} sources={m.sources} onCitation={(source, marker) => setActiveCitation({ source, marker })} />
                  : <InlineMarkdown text={m.content} />}</div>
                {m.role === 'assistant' && m.sources && m.sources.length > 0 && <div className="mt-4 border-t border-white/10 pt-3"><p className="text-xs font-semibold text-slate-400">Fonti</p><div className="mt-2 space-y-2">{m.sources.map((source, index) => <div key={`${source.document_id}-${source.locator}-${index}`} className="rounded-md bg-white/5 p-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-blue-300">{source.filename}<span className="font-normal text-slate-400"> · v{source.version} · {source.locator}</span></span>
                      <button type="button" onClick={() => window.open(`/api/libraries/${selectedLibraryId}/documents/${source.document_id}/download`, '_blank', 'noopener,noreferrer')} className="flex shrink-0 items-center gap-1 rounded-md border border-blue-500/20 bg-blue-500/10 px-2 py-1 text-[10px] font-semibold text-blue-300 transition hover:border-blue-400/40 hover:bg-blue-500/20" title="Apri il documento originale">
                        <Download className="h-3 w-3" /> Apri originale
                      </button>
                    </div>
                    <p className="mt-1 text-slate-400"><InlineMarkdown text={source.excerpt} /></p>
                  </div>)}</div></div>}
                {m.role === 'assistant' && m.content === '' && (
                  <div className="flex flex-col gap-2 py-1">
                    <div className="flex items-center gap-3">
                      <span className="w-2 h-2 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-2 h-2 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-2 h-2 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>
      )}

      {/* Input Form */}
      <div className={`p-5 sm:p-6 border-t ${t.chatFormBg}`}>
        <div className="mb-3 flex max-w-5xl items-center gap-2 mx-auto"><span className="rounded-full border border-blue-500/15 bg-blue-500/5 px-2.5 py-1 text-[11px] font-medium text-blue-300">Stai consultando</span><select value={selectedLibraryId} onChange={event => onLibraryChange?.(event.target.value)} className={`min-w-0 rounded-lg border px-3 py-1.5 text-xs outline-none ${t.sidebarInput}`}><option value="">Seleziona una biblioteca</option>{libraries.map(library => <option key={library.id} value={library.id}>{library.name}</option>)}</select></div>
        <form onSubmit={handleSubmit} className="flex gap-3 max-w-5xl mx-auto rounded-2xl border border-white/[0.08] bg-white/[0.025] p-2 shadow-lg shadow-slate-950/10">
          <input type="text" value={inputMessage}
            onChange={e => onInputChange(e.target.value)}
            disabled={isGenerating || needsLibrary || needsDocuments}
            placeholder={isGenerating ? 'Sto preparando la risposta…' : 'Fai una domanda sui tuoi documenti…'}
            className={`flex-1 border rounded-xl px-4 py-3 text-sm outline-none transition disabled:opacity-50 ${t.chatInput}`} />
          {isGenerating ? (
            <button type="button" onClick={onStop}
              className="bg-red-600 hover:bg-red-500 text-white rounded-lg px-5 py-3 flex items-center justify-center gap-2 font-medium text-sm transition shadow-sm cursor-pointer">
              <Square className="w-4 h-4" /> Stop
            </button>
          ) : (
            <button type="submit" disabled={!inputMessage.trim() || isGenerating || needsLibrary || needsDocuments}
              className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white rounded-xl px-5 py-3 flex items-center justify-center gap-2 font-medium text-sm transition shadow-lg shadow-blue-950/30 cursor-pointer">
              <Send className="w-4 h-4" /> Invia
            </button>
          )}
        </form>
      </div>
      {activeCitation && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-slate-950/70 p-6" role="dialog" aria-label="Dettaglio citazione">
          <section className={`w-full max-w-lg rounded-2xl border p-6 shadow-2xl ${t.card}`}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="font-semibold">Citazione [{activeCitation.marker}]</h2>
                <p className="mt-1 text-sm text-slate-400">{activeCitation.source.filename} · v{activeCitation.source.version} · {activeCitation.source.locator}</p>
              </div>
              <button onClick={() => setActiveCitation(null)} className="text-slate-400 hover:text-white" aria-label="Chiudi citazione"><X className="h-4 w-4" /></button>
            </div>
            <blockquote className="mt-4 rounded-lg border border-white/10 bg-white/[0.02] p-4 text-sm leading-6">
              <InlineMarkdown text={activeCitation.source.excerpt} />
            </blockquote>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={() => window.open(`/api/libraries/${selectedLibraryId}/documents/${activeCitation.source.document_id}/download`, '_blank', 'noopener,noreferrer')}
                className="flex items-center gap-1.5 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-1.5 text-xs font-semibold text-blue-300 transition hover:bg-blue-500/20"
              >
                <Download className="h-3.5 w-3.5" /> Apri originale
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
