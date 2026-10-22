import { useRef, useEffect, useState } from 'react'
import { Send, Square, ShieldCheck, Download, X, ThumbsUp, ThumbsDown, Copy, Check, RotateCcw, FileDown, History, Plus, Table, Trash2, AlertTriangle, Maximize2, PanelRightOpen, FileText, Printer, ExternalLink } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { useDialog } from '../../hooks/useDialog'
import { InlineMarkdown } from './InlineMarkdown'
import { TabularExplorerModal } from '../documents/TabularExplorerModal'
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
        return <CitationChip key={index} marker={marker} source={source} onCitation={onCitation} />
      })}
    </span>
  )
}

/** Il numero cliccabile che porta dal testo al passaggio da cui viene. */
function CitationChip({ marker, source, onCitation }: { marker: number; source: Source; onCitation: (source: Source, marker: number) => void }) {
  return (
    <button
      type="button"
      onClick={() => onCitation(source, marker)}
      title={`${source.filename} · ${source.locator}`}
      aria-label={`Fonte ${marker}: ${source.filename}`}
      className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full border border-blue-400/40 bg-blue-500/15 px-1 align-super text-[10px] font-semibold text-blue-300 transition hover:bg-blue-500/30 hover:text-blue-200"
    >
      {marker}
    </button>
  )
}

/**
 * Il corpo di una risposta con due voci distinte.
 *
 * Quello che dice il documento (i passaggi recuperati, la frase in evidenza) e' composto
 * in carattere con grazie e con un filetto a sinistra: e' una citazione, non un'opinione
 * del sistema. Quello che dice il sistema resta in sans. Cosi' si vede a colpo d'occhio
 * che cosa e' stato scritto da chi, che e' il punto di tutto il prodotto.
 */
function AnswerBody({ text, sources, onCitation }: {
  text: string
  sources: Source[]
  onCitation: (source: Source, marker: number) => void
}) {
  const blocks = text.split(/\n{2,}/)
  return (
    <div className="space-y-3">
      {blocks.map((block, index) => {
        const passage = block.match(/^\[(\d+)\]\s+([\s\S]+)$/)
        if (passage) {
          const marker = Number(passage[1])
          const source = sources.find(candidate => (candidate.marker ?? 0) === marker)
          return (
            <blockquote key={index} className="doc-voice border-l-2 border-blue-400/50 pl-4 text-[15px]">
              {source && <CitationChip marker={marker} source={source} onCitation={onCitation} />}
              <InlineMarkdown text={passage[2]} />
            </blockquote>
          )
        }
        const brief = block.match(/^In breve:\s*([\s\S]+)$/)
        if (brief) {
          return (
            <div key={index}>
              <p className="text-xs font-medium text-slate-400">In breve</p>
              <p className="doc-voice mt-1 text-xl leading-snug"><CitationText text={brief[1]} sources={sources} onCitation={onCitation} /></p>
            </div>
          )
        }
        return <p key={index} className="text-slate-400"><CitationText text={block} sources={sources} onCitation={onCitation} /></p>
      })}
    </div>
  )
}

interface ChatAreaProps {
  messages: Message[]
  inputMessage: string
  onInputChange: (v: string) => void
  onSend: (text: string) => void
  onStop: () => void
  onClearChat?: () => void
  isGenerating: boolean
  suggestions: { title: string; desc: string; prompt: string }[]
  libraries?: Array<{ id: string; name: string }>
  selectedLibraryId?: string
  selectedLibraryDocumentCount?: number
  onLibraryChange?: (id: string) => void
  onOpenLibraries?: () => void
  conversations?: Array<{ id: string; title: string; updated_at: number }>
  activeConversationId?: string | null
  onSelectConversation?: (id: string) => void
  onNewConversation?: () => void
  onDeleteConversation?: (id: string) => void
}

export default function ChatArea({
  messages, inputMessage, onInputChange, onSend, onStop, onClearChat,
  isGenerating, suggestions, libraries = [], selectedLibraryId = '', selectedLibraryDocumentCount = 0, onLibraryChange, onOpenLibraries,
  conversations = [], activeConversationId = null, onSelectConversation, onNewConversation, onDeleteConversation,
}: ChatAreaProps) {
  const { t, isDark } = useTheme()
  const chatEndRef = useRef<HTMLDivElement>(null)
  const [activeCitation, setActiveCitation] = useState<{ source: Source; marker: number } | null>(null)
  const [citationViewMode, setCitationViewMode] = useState<'text' | 'pdf'>('text')
  const [isCitationDocked, setIsCitationDocked] = useState<boolean>(false)
  const [tabularSource, setTabularSource] = useState<{ documentId: string; filename: string } | null>(null)
  const [showHistoryMenu, setShowHistoryMenu] = useState(false)
  const [historyFilter, setHistoryFilter] = useState('')
  const [feedbackState, setFeedbackState] = useState<Record<string, number>>({})
  const [negativeFeedbackOpen, setNegativeFeedbackOpen] = useState<string | null>(null)
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null)
  const [copiedCitation, setCopiedCitation] = useState(false)

  const feedbackReasons = [
    'Informazione mancante',
    'Fonte non pertinente',
    'Risposta poco chiara',
    'Altro',
  ]

  const getFileBadge = (filename: string) => {
    const ext = filename.split('.').pop()?.toUpperCase() || 'DOC'
    if (ext === 'PDF') return { color: 'bg-rose-500/15 text-rose-300 border-rose-500/30', label: 'PDF' }
    if (ext === 'DOCX' || ext === 'DOC') return { color: 'bg-blue-500/15 text-blue-300 border-blue-500/30', label: 'DOCX' }
    if (ext === 'XLSX' || ext === 'CSV') return { color: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30', label: 'EXCEL' }
    if (ext === 'PPTX') return { color: 'bg-amber-500/15 text-amber-300 border-amber-500/30', label: 'SLIDES' }
    return { color: 'bg-purple-500/15 text-purple-300 border-purple-500/30', label: ext }
  }

  const handleCopy = (messageId: string, text: string) => {
    if (!navigator.clipboard) return
    navigator.clipboard.writeText(text).then(() => {
      setCopiedMessageId(messageId)
      setTimeout(() => setCopiedMessageId(prev => (prev === messageId ? null : prev)), 2000)
    }).catch(() => {})
  }

  const handleCopyCitation = () => {
    if (!navigator.clipboard || !activeCitation?.source?.excerpt) return
    navigator.clipboard.writeText(activeCitation.source.excerpt).then(() => {
      setCopiedCitation(true)
      setTimeout(() => setCopiedCitation(false), 2000)
    }).catch(() => {})
  }

  const citationDialogRef = useDialog<HTMLDivElement>(!!activeCitation && !isCitationDocked, () => setActiveCitation(null))

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (activeCitation) setActiveCitation(null)
        if (negativeFeedbackOpen) setNegativeFeedbackOpen(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeCitation, negativeFeedbackOpen])

  useEffect(() => {
    if (typeof chatEndRef.current?.scrollIntoView === 'function') {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isGenerating])

  const handleFeedback = async (messageId: string, rating: 1 | -1, comment: string = '') => {
    const previous = feedbackState[messageId]
    setFeedbackState(prev => ({ ...prev, [messageId]: rating }))
    setNegativeFeedbackOpen(null)
    try {
      const ratingStr = rating === 1 ? 'positive' : 'negative'
      if (activeConversationId) {
        fetch(`/api/conversations/${activeConversationId}/messages/${messageId}/feedback`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rating: ratingStr, reason: comment, comment }),
          credentials: 'include',
        }).catch(() => {})
      }
      const response = await fetch('/api/analytics/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: messageId, rating, comment }),
        credentials: 'include',
      })
      if (!response.ok) throw new Error(String(response.status))
    } catch {
      // Optimistic update rolled back: a thumb that stays lit after a failed
      // save tells the user something that did not happen.
      setFeedbackState(prev => {
        const next = { ...prev }
        if (previous === undefined) delete next[messageId]
        else next[messageId] = previous
        return next
      })
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!inputMessage.trim() || isGenerating) return
    onSend(inputMessage)
  }

  const exportChatMarkdown = () => {
    if (messages.length === 0) return
    let md = `# Conversazione Ermes Knowledge\n\n`
    md += `**Biblioteca:** ${selectedLibraryName}\n`
    md += `**Data esportazione:** ${new Date().toLocaleString('it-IT')}\n\n`
    md += `---\n\n`

    messages.forEach(msg => {
      if (msg.role === 'user') {
        md += `### 👤 Domanda (${msg.timestamp})\n\n${msg.content}\n\n`
      } else {
        md += `### 🤖 Risposta Ermes (${msg.timestamp})\n\n${msg.content}\n\n`
        if (msg.sources && msg.sources.length > 0) {
          md += `#### 📚 Fonti ed Evidenze:\n`
          msg.sources.forEach(src => {
            md += `- **[${src.marker ?? '•'}] ${src.filename}** (v${src.version} · ${src.locator})\n`
            md += `  > ${src.excerpt.replace(/\n/g, '\n  > ')}\n\n`
          })
        }
        md += `---\n\n`
      }
    })

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ermes_conversazione_${new Date().toISOString().slice(0, 10)}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const needsLibrary = Boolean(onOpenLibraries) && (!selectedLibraryId || libraries.length === 0)
  const needsDocuments = Boolean(onOpenLibraries) && !needsLibrary && selectedLibraryDocumentCount === 0
  const selectedLibraryName = libraries.find(library => library.id === selectedLibraryId)?.name || 'Nessuna biblioteca selezionata'
  const onboardingTitle = needsLibrary ? 'Crea la prima biblioteca' : 'Aggiungi il primo documento'
  const onboardingDescription = needsLibrary
    ? 'Una biblioteca separa procedure, manuali e policy del tuo team. Poi potrai chiedere risposte con fonti verificabili.'
    : 'La biblioteca è pronta. Carica un PDF, DOCX, TXT o Markdown per iniziare a cercare e fare domande.'

  const exportCertifiedReport = () => {
    if (messages.length === 0) return
    const allSources: Source[] = []
    const seenKeys = new Set<string>()
    messages.forEach(msg => {
      msg.sources?.forEach(s => {
        const key = `${s.document_id}-${s.locator}`
        if (!seenKeys.has(key)) {
          seenKeys.add(key)
          allSources.push(s)
        }
      })
    })

    const printWindow = window.open('', '_blank')
    if (!printWindow) return

    const escapeHtml = (str: string) =>
      str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

    const html = `<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>Ermes Knowledge - Report di consultazione</title>
  <style>
    @page { size: A4; margin: 18mm 15mm; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #0f172a; line-height: 1.5; padding: 0; margin: 0; font-size: 13px; }
    .header { border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: flex-start; }
    .title { font-size: 20px; font-weight: 700; color: #0f172a; margin: 0; }
    .subtitle { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-top: 4px; }
    .badge { display: inline-block; padding: 4px 10px; background: #ecfdf5; border: 1px solid #10b981; color: #065f46; font-size: 11px; font-weight: 600; border-radius: 9999px; }
    .meta-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; margin-bottom: 24px; font-size: 12px; display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
    .meta-item strong { color: #475569; }
    .exchange { margin-bottom: 20px; page-break-inside: avoid; }
    .user-q { background: #f1f5f9; border-left: 4px solid #3b82f6; padding: 10px 14px; border-radius: 0 6px 6px 0; margin-bottom: 8px; font-weight: 600; color: #1e3a8a; }
    .bot-a { padding: 12px 14px; border-left: 4px solid #10b981; background: #fafafa; border-radius: 0 6px 6px 0; line-height: 1.6; }
    .sources-list { margin-top: 8px; font-size: 11px; color: #475569; border-top: 1px dashed #cbd5e1; padding-top: 6px; }
    .sources-table { width: 100%; border-collapse: collapse; margin-top: 24px; font-size: 11px; page-break-inside: avoid; }
    .sources-table th, .sources-table td { border: 1px solid #cbd5e1; padding: 8px 10px; text-align: left; }
    .sources-table th { background: #f1f5f9; color: #334155; font-weight: 600; }
    .footer { margin-top: 36px; border-top: 1px solid #e2e8f0; padding-top: 12px; font-size: 10px; color: #94a3b8; display: flex; justify-content: space-between; }
    @media print {
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1 class="title">Ermes Knowledge Hub</h1>
      <div class="subtitle">Report Ufficiale di Consultazione Documentale &amp; Evidenze</div>
    </div>
    <div>
      <span class="badge">Fonti citate nella risposta</span>
    </div>
  </div>

  <div class="meta-box">
    <div class="meta-item"><strong>Biblioteca Consultata:</strong> ${escapeHtml(selectedLibraryName)}</div>
    <div class="meta-item"><strong>Data e Ora Esportazione:</strong> ${new Date().toLocaleString('it-IT')}</div>
    <div class="meta-item"><strong>Protocollo Sicurezza:</strong> Evidence-First &amp; Quarantine Guard</div>
    <div class="meta-item"><strong>Natura del documento:</strong> esportazione non firmata, senza valore di certificazione</div>
  </div>

  <h3 style="margin-top: 0; color: #0f172a; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px;">Q&amp;A ed Evidenze Estratte</h3>
  ${messages.map(msg => {
    if (msg.role === 'user') {
      return `<div class="exchange"><div class="user-q">&#128100; Domanda (${msg.timestamp}): ${escapeHtml(msg.content)}</div>`
    }
    const sourcesHtml = msg.sources && msg.sources.length > 0
      ? `<div class="sources-list"><strong>Fonti Citata:</strong> ${msg.sources.map(s => `[${s.marker ?? '•'}] ${escapeHtml(s.filename)} (${escapeHtml(s.locator)})`).join(' · ')}</div>`
      : ''
    return `<div class="bot-a"><strong>&#129302; Risposta Ermes:</strong><br/>${escapeHtml(msg.content).replace(/\n/g, '<br/>')}${sourcesHtml}</div></div>`
  }).join('')}

  ${allSources.length > 0 ? `
  <h3 style="color: #0f172a; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; margin-top: 28px;">Fonti citate e loro provenienza</h3>
  <table class="sources-table">
    <thead>
      <tr>
        <th style="width: 25px;">#</th>
        <th>Documento</th>
        <th>Versione</th>
        <th>Posizione / Pagina</th>
        <th>Identificativo / Hash</th>
        <th>Stato</th>
      </tr>
    </thead>
    <tbody>
      ${allSources.map(s => `
        <tr>
          <td>[${s.marker ?? '•'}]</td>
          <td><strong>${escapeHtml(s.filename)}</strong></td>
          <td>v${s.version}</td>
          <td>${escapeHtml(s.locator)}</td>
          <td style="font-family: monospace; font-size: 10px;">${escapeHtml(s.content_hash || s.chunk_id || 'n/d')}</td>
          <td>Citata</td>
        </tr>
      `).join('')}
    </tbody>
  </table>
  ` : ''}

  <div class="footer">
    <span>Ermes Knowledge Hub v2.4.1 &mdash; Documentazione riservata a uso aziendale interno</span>
    <span>Generato il ${new Date().toISOString()}</span>
  </div>

  <script>
    window.onload = function() {
      setTimeout(function() {
        window.print();
      }, 300);
    };
  </script>
</body>
</html>`

    printWindow.document.write(html)
    printWindow.document.close()
  }

  return (
    <div className={`flex h-full w-full overflow-hidden ${t.chatBg}`}>
      {/* Colonna Principale Chat */}
      <div className="flex flex-col flex-1 h-full min-w-0 overflow-hidden relative">
      {/* Messages / Welcome */}
      {messages.length === 0 && (needsLibrary || needsDocuments) ? (
        <div className="flex-1 overflow-y-auto px-8 py-8 flex flex-col items-center justify-center max-w-2xl mx-auto space-y-6 w-full text-center">
          <div className="rounded-2xl border border-blue-500/20 bg-blue-500/5 p-7">
            <p className="text-xs font-bold text-blue-400">Primo avvio</p>
            <h2 className={`mt-3 text-2xl font-bold tracking-tight ${t.welcomeTitle}`}>{onboardingTitle}</h2>
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
          <p className="text-xs text-slate-500">Di norma Ermes lavora solo su questo server: nessun documento viene inviato su internet.</p>
        </div>
      ) : messages.length === 0 ? (
        <div className="flex-1 overflow-y-auto px-6 py-10 md:px-12">
          <div className="mx-auto w-full max-w-2xl pt-4 md:pt-16">
            <h2 className={`text-4xl font-semibold leading-[1.1] tracking-tight ${t.welcomeTitle}`}>Cosa vuoi trovare nei tuoi documenti?</h2>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-500 dark:text-slate-400">
              Ogni risposta indica il documento da cui arriva. Se i documenti non bastano, Ermes te lo dice invece di inventare.
            </p>
            <p className="mt-6 text-sm text-slate-500 dark:text-slate-400">
              Stai consultando <span className="font-medium text-slate-800 dark:text-slate-200">{selectedLibraryName}</span>, con {selectedLibraryDocumentCount} {selectedLibraryDocumentCount === 1 ? 'documento' : 'documenti'}.
            </p>
            <ul className="mt-8 divide-y divide-slate-200 border-y border-slate-200 dark:divide-white/10 dark:border-white/10">
              {suggestions.map((s, idx) => (
                <li key={idx}>
                  <button type="button" onClick={() => onSend(s.prompt)} className="group w-full py-4 text-left">
                    <span className={`block font-medium group-hover:underline group-hover:underline-offset-4 ${t.cardTitle}`}>{s.title}</span>
                    <span className={`mt-0.5 block text-sm ${t.cardDesc}`}>{s.desc}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-8 py-6 space-y-6">
          {messages.map(m => (
            <div key={m.id} className={`flex flex-col max-w-[85%] ${m.role === 'user' ? 'ml-auto items-end' : 'mr-auto items-start'}`}>
              <div className="text-[10px] text-slate-500 font-medium mb-1 px-1 flex items-center gap-1.5">
                <span className="font-bold ">{m.role === 'user' ? 'Tu' : 'Ermes AI'}</span>
                <span>•</span>
                <span>{m.timestamp}</span>
              </div>
              <div className={`px-4 py-3 rounded-xl text-sm leading-relaxed border ${m.role === 'user' ? t.chatBubbleUser : t.chatBubbleAssistant}`}>
                {m.role === 'assistant' && m.searchedAs && (
                  <p className="mb-2 text-[11px] text-slate-400" title="La domanda e' stata riscritta con la conversazione prima della ricerca">
                    Ho cercato: <span className="italic text-slate-300">{m.searchedAs}</span>
                  </p>
                )}
                {m.role === 'assistant' && m.evidence && (
                  <div className={`mb-3 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold shadow-xs ${
                    m.evidence.coverage === 'supported'
                      ? 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300'
                      : 'border-amber-500/30 bg-amber-500/15 text-amber-300'
                  }`}>
                    {m.evidence.coverage === 'supported' ? (
                      <>
                        <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                        <span>Basata su {m.sources?.length ?? 0} {(m.sources?.length ?? 0) === 1 ? 'fonte' : 'fonti'}</span>
                      </>
                    ) : (
                      <>
                        <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
                        <span>Nessuna fonte sufficiente nei documenti</span>
                      </>
                    )}
                    {m.evidence.reason ? <span className="text-slate-400 font-normal"> - {m.evidence.reason}</span> : ''}
                  </div>
                )}
                <div className="whitespace-pre-wrap">{m.role === 'assistant' && m.sources && m.sources.length > 0
                  ? <AnswerBody text={m.content} sources={m.sources} onCitation={(source, marker) => setActiveCitation({ source, marker })} />
                  : <InlineMarkdown text={m.content} />}</div>
                {m.role === 'assistant' && m.sources && m.sources.length > 0 && <div className="mt-4 border-t border-white/10 pt-3"><p className="text-xs font-semibold text-slate-400">Fonti</p><div className="mt-2 space-y-2">{m.sources.map((source, index) => {
                    const isTabular = ['csv', 'tsv', 'xlsx'].includes(source.filename.split('.').pop()?.toLowerCase() || '')
                    return (
                      <div key={`${source.document_id}-${source.locator}-${index}`} className="rounded-md bg-white/5 p-2 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <button
                            type="button"
                            onClick={() => setActiveCitation({ source, marker: source.marker ?? (index + 1) })}
                            className="font-medium text-blue-300 hover:underline text-left"
                            title="Visualizza estratto completo"
                          >
                            <span className="data-voice text-[11px]">{source.filename}</span><span className="data-voice text-[11px] font-normal text-slate-400"> · v{source.version} · {source.locator}</span>
                            {source.library_name && <span className="ml-2 rounded-sm border border-indigo-500/30 bg-indigo-500/15 px-1.5 py-0.5 text-[10px] font-medium text-indigo-300" title={`Biblioteca: ${source.library_name}`}>{source.library_name}</span>}
                            {source.injection_suspected && <span className="ml-2 rounded-sm border border-amber-400/40 bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300" title="Il passaggio contiene istruzioni rivolte al modello: la fonte e' mostrata, il suo testo non e' stato usato per rispondere">non usata</span>}
                          </button>
                          <div className="flex items-center gap-1.5 shrink-0">
                            {isTabular && (
                              <button
                                type="button"
                                onClick={() => setTabularSource({ documentId: source.document_id, filename: source.filename })}
                                className="flex items-center gap-1 rounded-md border border-purple-500/30 bg-purple-500/10 px-2 py-1 text-[10px] font-semibold text-purple-300 transition hover:border-purple-400/50 hover:bg-purple-500/20"
                                title="Esplora dati e query SQL"
                              >
                                <Table className="h-3 w-3" /> Dati SQL
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => window.open(`/api/libraries/${selectedLibraryId}/documents/${source.document_id}/download`, '_blank', 'noopener,noreferrer')}
                              className="flex items-center gap-1 rounded-md border border-blue-500/20 bg-blue-500/10 px-2 py-1 text-[10px] font-semibold text-blue-300 transition hover:border-blue-400/40 hover:bg-blue-500/20"
                              title="Apri il documento originale"
                            >
                              <Download className="h-3 w-3" /> Apri
                            </button>
                          </div>
                        </div>
                        {!m.content.includes(source.excerpt) && <p className="doc-voice mt-1 text-[13px] text-slate-400"><InlineMarkdown text={source.excerpt} /></p>}
                      </div>
                    )
                  })}</div></div>}
                {m.role === 'assistant' && m.content !== '' && (
                  <div className="mt-3 flex items-center justify-end gap-2 border-t border-white/5 pt-2 text-xs text-slate-400">
                    <button
                      type="button"
                      onClick={() => handleCopy(m.id, m.content)}
                      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border transition text-[11px] font-medium ${
                        copiedMessageId === m.id
                          ? 'border-emerald-500/40 bg-emerald-500/20 text-emerald-300'
                          : 'border-white/5 hover:border-white/20 text-slate-400 hover:text-white'
                      }`}
                      title="Copia risposta negli appunti"
                    >
                      {copiedMessageId === m.id ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                          <span>Copiato!</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          <span>Copia</span>
                        </>
                      )}
                    </button>
                    <span className="h-3 w-px bg-white/10 mx-1" />
                    <span className="text-[11px] text-slate-500">Risposta utile?</span>
                    <button
                      type="button"
                      onClick={() => handleFeedback(m.id, 1)}
                      className={`p-1.5 rounded-lg border transition ${
                        feedbackState[m.id] === 1
                          ? 'border-emerald-500/40 bg-emerald-500/20 text-emerald-300'
                          : 'border-white/5 hover:border-white/20 text-slate-400 hover:text-white'
                      }`}
                      title="Utile"
                    >
                      <ThumbsUp className="w-3.5 h-3.5" />
                    </button>
                    <div className="relative inline-flex items-center">
                      <button
                        type="button"
                        onClick={() => {
                          if (negativeFeedbackOpen === m.id) {
                            setNegativeFeedbackOpen(null)
                          } else {
                            setNegativeFeedbackOpen(m.id)
                          }
                        }}
                        className={`p-1.5 rounded-lg border transition ${
                          feedbackState[m.id] === -1
                            ? 'border-rose-500/40 bg-rose-500/20 text-rose-300'
                            : 'border-white/5 hover:border-white/20 text-slate-400 hover:text-white'
                        }`}
                        title="Non utile (clicca per specificare motivo)"
                      >
                        <ThumbsDown className="w-3.5 h-3.5" />
                      </button>
                      {negativeFeedbackOpen === m.id && (
                        <div className="absolute right-0 bottom-full mb-2 z-20 flex flex-col gap-1.5 p-2.5 rounded-xl border border-white/10 bg-[#141b2d] shadow-2xl min-w-[210px] text-xs animate-fadeIn backdrop-blur-md">
                          <p className="text-[11px] font-semibold text-slate-400 px-1 border-b border-white/5 pb-1">Segnala motivo gap:</p>
                          {feedbackReasons.map((reason) => (
                            <button
                              key={reason}
                              type="button"
                              onClick={() => handleFeedback(m.id, -1, reason)}
                              className="text-left px-2.5 py-1.5 rounded-lg hover:bg-rose-500/15 text-slate-300 hover:text-rose-200 text-xs transition font-medium border border-transparent hover:border-rose-500/30"
                            >
                              • {reason}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {m.role === 'assistant' && m.content === '' && (
                  <div className="flex flex-col gap-2 py-1">
                    <div className="flex items-center gap-3">
                      <span className="w-2 h-2 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-2 h-2 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-2 h-2 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '300ms' }} />
                      {m.statusStep && <span className="text-xs text-blue-400 font-medium animate-pulse">{m.statusStep}</span>}
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
        <div className="mb-3 flex max-w-5xl items-center justify-between gap-2 mx-auto">
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-blue-500/15 bg-blue-500/5 px-2.5 py-1 text-[11px] font-medium text-blue-300">Stai consultando</span>
            <select aria-label="Biblioteca da consultare" value={selectedLibraryId} onChange={event => onLibraryChange?.(event.target.value)} className={`min-w-0 rounded-lg border px-3 py-1.5 text-xs outline-hidden ${t.sidebarInput}`}>
              <option value="">Seleziona una biblioteca</option>
              {libraries.map(library => <option key={library.id} value={library.id}>{library.name}</option>)}
            </select>
            {onNewConversation && (
              <button
                type="button"
                onClick={onNewConversation}
                className="inline-flex items-center gap-1 rounded-lg border border-blue-500/30 bg-blue-500/10 px-2.5 py-1.5 text-xs font-semibold text-blue-300 transition hover:bg-blue-500/20 cursor-pointer"
                title="Avvia una nuova sessione di chat"
              >
                <Plus className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Nuova chat</span>
              </button>
            )}
            {conversations.length > 0 && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowHistoryMenu(prev => !prev)}
                  className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition cursor-pointer ${
                    showHistoryMenu || activeConversationId
                      ? 'border-indigo-500/40 bg-indigo-500/15 text-indigo-200'
                      : 'border-white/10 hover:border-white/20 text-slate-300'
                  }`}
                  title="Mostra storico conversazioni"
                >
                  <History className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Storico ({conversations.length})</span>
                </button>
                {showHistoryMenu && (
                  <div className="absolute left-0 bottom-full mb-2 z-30 flex flex-col gap-1.5 p-2.5 rounded-xl border border-white/10 bg-[#121722]/95 shadow-2xl min-w-[280px] max-h-[320px] overflow-y-auto text-xs backdrop-blur-md">
                    <div className="flex items-center justify-between gap-1 pb-1 border-b border-white/5 px-1">
                      <p className="text-[11px] font-semibold text-slate-400">Conversazioni ({conversations.length}):</p>
                      {historyFilter && (
                        <button
                          type="button"
                          onClick={() => setHistoryFilter('')}
                          className="text-[10px] text-slate-500 hover:text-slate-300"
                        >
                          Cancella
                        </button>
                      )}
                    </div>
                    <input
                      type="text"
                      value={historyFilter}
                      onChange={e => setHistoryFilter(e.target.value)}
                      placeholder="Cerca conversazioni…" aria-label="Cerca nelle conversazioni"
                      className="w-full rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-200 placeholder-slate-500 outline-hidden focus:border-blue-500/50"
                      onClick={e => e.stopPropagation()}
                    />
                    <div className="flex flex-col gap-1 max-h-[220px] overflow-y-auto mt-1">
                      {conversations
                        .filter(c => !historyFilter.trim() || c.title.toLowerCase().includes(historyFilter.toLowerCase().trim()))
                        .map(c => (
                          <div
                            key={c.id}
                            className={`flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg transition ${
                              activeConversationId === c.id
                                ? 'bg-blue-600/25 border border-blue-500/40 text-blue-200'
                                : 'hover:bg-white/5 text-slate-300'
                            }`}
                          >
                            <button
                              type="button"
                              onClick={() => {
                                onSelectConversation?.(c.id)
                                setShowHistoryMenu(false)
                              }}
                              className="flex-1 text-left truncate font-medium hover:text-white"
                              title={c.title}
                            >
                              {c.title}
                            </button>
                            {onDeleteConversation && (
                              <button
                                type="button"
                                onClick={e => {
                                  e.stopPropagation()
                                  onDeleteConversation(c.id)
                                }}
                                className="text-slate-500 hover:text-rose-400 p-1 rounded-sm transition"
                                title="Elimina conversazione"
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        ))}
                      {conversations.filter(c => !historyFilter.trim() || c.title.toLowerCase().includes(historyFilter.toLowerCase().trim())).length === 0 && (
                        <p className="py-3 text-center text-[11px] text-slate-500">Nessuna conversazione trovata</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
          {messages.length > 0 && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={exportChatMarkdown}
                className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1 text-xs text-slate-300 transition hover:border-white/20 hover:bg-white/5 hover:text-white cursor-pointer"
                title="Esporta conversazione in Markdown"
              >
                <FileDown className="w-3.5 h-3.5 text-blue-400" />
                <span>Markdown</span>
              </button>
              <button
                type="button"
                onClick={exportCertifiedReport}
                className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300 transition hover:bg-emerald-500/20 hover:text-emerald-200 cursor-pointer shadow-xs"
                title="Esporta report formattato ufficiale per stampa o salvataggio PDF"
              >
                <Printer className="w-3.5 h-3.5 text-emerald-400" />
                <span>Report PDF</span>
              </button>
              {onClearChat && (
                <button
                  type="button"
                  onClick={onClearChat}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1 text-xs text-slate-400 transition hover:border-rose-500/30 hover:bg-rose-500/10 hover:text-rose-300 cursor-pointer"
                  title="Pulisci la conversazione attuale"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Pulisci</span>
                </button>
              )}
            </div>
          )}
        </div>
        <form onSubmit={handleSubmit} className="flex gap-3 max-w-5xl mx-auto">
          <input type="text" aria-label="La tua domanda sui documenti" value={inputMessage}
            onChange={e => onInputChange(e.target.value)}
            disabled={isGenerating || needsLibrary || needsDocuments}
            placeholder={isGenerating ? 'Sto preparando la risposta…' : 'Fai una domanda sui tuoi documenti…'}
            className={`flex-1 border rounded-xl px-4 py-3 text-sm outline-hidden transition disabled:opacity-50 ${t.chatInput}`} />
          {isGenerating ? (
            <button type="button" onClick={onStop}
              className="bg-red-600 hover:bg-red-500 text-white rounded-lg px-5 py-3 flex items-center justify-center gap-2 font-medium text-sm transition shadow-xs cursor-pointer">
              <Square className="w-4 h-4" /> Stop
            </button>
          ) : (
            <button type="submit" disabled={!inputMessage.trim() || isGenerating || needsLibrary || needsDocuments}
              className="bg-linear-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white rounded-xl px-5 py-3 flex items-center justify-center gap-2 font-medium text-sm transition shadow-lg shadow-blue-950/30 cursor-pointer">
              <Send className="w-4 h-4" /> Invia
            </button>
          )}
        </form>
      </div>
      </div>

      {/* NotebookLM-Style Split-Screen Source Inspector Panel */}
      {activeCitation && isCitationDocked && (
        <aside
          className={`hidden lg:flex flex-col w-[420px] xl:w-[460px] h-full border-l backdrop-blur-xl p-5 shrink-0 overflow-y-auto terminal-scroll shadow-2xl animate-fadeIn z-20 ${isDark ? 'border-white/10 bg-slate-950/90' : 'border-slate-200 bg-white/95'}`}
          aria-label="Ispezione Fonte NotebookLM"
        >
          <div className={`flex items-start justify-between gap-3 pb-3 border-b ${isDark ? 'border-white/10' : 'border-slate-200'}`}>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`font-bold text-sm ${isDark ? 'text-white' : 'text-slate-900'}`}>Fonte [{activeCitation.marker}]</span>
                <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                  Evidenza Verificata
                </span>
                {(() => {
                  const badge = getFileBadge(activeCitation.source.filename)
                  return (
                    <span className={`rounded-full border px-2 py-0.5 text-[9px] font-bold ${badge.color}`}>
                      {badge.label}
                    </span>
                  )
                })()}
              </div>
              <div className="flex items-center gap-1.5 text-xs text-slate-400 mt-1 truncate max-w-[340px]">
                <span className={`font-medium truncate ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>{activeCitation.source.filename}</span>
                <span>•</span>
                <span className="rounded-sm bg-blue-500/10 border border-blue-500/20 px-1 py-0.5 text-blue-300 font-mono text-[10px]">
                  {activeCitation.source.locator}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setIsCitationDocked(false)}
                className={`p-1 rounded-lg transition cursor-pointer ${isDark ? 'text-slate-400 hover:text-white hover:bg-white/10' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'}`}
                title="Espandi in modale"
              >
                <Maximize2 className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setActiveCitation(null)}
                className={`p-1 rounded-lg transition cursor-pointer ${isDark ? 'text-slate-400 hover:text-white hover:bg-white/10' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'}`}
                title="Chiudi ispezione"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Contenuto fonte: Toggle Estratto / PDF per i file PDF */}
          {(() => {
            const isPdf = activeCitation.source.filename.toLowerCase().endsWith('.pdf')
            const pageMatch = activeCitation.source.locator.match(/Pagina\s+(\d+)/i)
            const pageNum = pageMatch ? pageMatch[1] : '1'
            const pdfUrl = `/api/libraries/${selectedLibraryId}/documents/${activeCitation.source.document_id}/download?inline=true#page=${pageNum}&view=FitH`

            return (
              <div className="mt-4 flex-1 flex flex-col">
                {isPdf && (
                  <div className="flex items-center gap-1.5 p-0.5 rounded-lg bg-black/20 border border-white/10 w-fit mb-2.5">
                    <button
                      type="button"
                      onClick={() => setCitationViewMode('text')}
                      className={`px-2 py-0.5 text-[11px] rounded-md font-medium transition cursor-pointer ${
                        citationViewMode === 'text'
                          ? 'bg-blue-600 text-white shadow-xs'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Estratto Testo
                    </button>
                    <button
                      type="button"
                      onClick={() => setCitationViewMode('pdf')}
                      className={`px-2 py-0.5 text-[11px] rounded-md font-medium transition cursor-pointer flex items-center gap-1 ${
                        citationViewMode === 'pdf'
                          ? 'bg-rose-600 text-white shadow-xs'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <FileText className="w-3 h-3" />
                      <span>PDF Pag. {pageNum}</span>
                    </button>
                  </div>
                )}

                {isPdf && citationViewMode === 'pdf' ? (
                  <div className="flex flex-col h-[52vh] rounded-xl border border-white/10 bg-slate-950 overflow-hidden shadow-inner">
                    <div className="flex items-center justify-between px-2.5 py-1.5 bg-slate-900 border-b border-white/10 text-xs">
                      <span className="text-slate-300 font-medium text-[11px] flex items-center gap-1">
                        <FileText className="w-3.5 h-3.5 text-rose-400" />
                        <span>Pagina {pageNum}</span>
                      </span>
                      <button
                        type="button"
                        onClick={() => window.open(pdfUrl, '_blank', 'noopener,noreferrer')}
                        className="text-blue-400 hover:text-blue-300 flex items-center gap-1 text-[11px] font-medium transition cursor-pointer"
                        title="Apri a tutto schermo"
                      >
                        <ExternalLink className="h-3 w-3" /> Schermo intero
                      </button>
                    </div>
                    <iframe
                      src={pdfUrl}
                      className="w-full flex-1 border-0 bg-slate-900"
                      title={`Anteprima PDF ${activeCitation.source.filename} a pagina ${pageNum}`}
                    />
                  </div>
                ) : (
                  <div>
                    <p className="text-xs font-medium text-slate-400 mb-1.5">Passaggio nel documento</p>
                    <blockquote className={`rounded-xl border border-amber-500/25 bg-amber-500/4 doc-voice p-3.5 text-[13px] leading-relaxed ${isDark ? 'text-slate-200' : 'text-slate-800'} border-l-4 border-l-amber-400/80 shadow-inner`}>
                      <InlineMarkdown text={activeCitation.source.excerpt} />
                    </blockquote>
                  </div>
                )}
              </div>
            )
          })()}

          <div className={`mt-4 pt-3 border-t ${isDark ? 'border-white/10' : 'border-slate-200'} flex items-center justify-between gap-2`}>
            <button
              type="button"
              onClick={handleCopyCitation}
              className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-white/5 hover:text-white cursor-pointer"
            >
              {copiedCitation ? (
                <>
                  <Check className="h-3.5 w-3.5 text-emerald-400" />
                  <span className="text-emerald-300 font-medium">Copiato!</span>
                </>
              ) : (
                <>
                  <Copy className="h-3.5 w-3.5 text-slate-400" />
                  <span>Copia testo</span>
                </>
              )}
            </button>
            <button
              type="button"
              onClick={() =>
                window.open(
                  `/api/libraries/${selectedLibraryId}/documents/${activeCitation.source.document_id}/download`,
                  '_blank',
                  'noopener,noreferrer'
                )
              }
              className="flex items-center gap-1.5 rounded-lg border border-blue-500/30 bg-blue-500/15 hover:bg-blue-500/25 px-3 py-1.5 text-xs font-semibold text-blue-200 transition cursor-pointer"
            >
              <Download className="h-3.5 w-3.5 text-blue-400" /> Scarica file
            </button>
          </div>
        </aside>
      )}

      {/* Modal dettaglio citazione */}
      {activeCitation && !isCitationDocked && (
        <div
          ref={citationDialogRef}
          tabIndex={-1}
          aria-modal="true"
          className="absolute inset-0 z-30 flex items-center justify-center bg-slate-950/80 p-4 sm:p-6 backdrop-blur-xs animate-fadeIn outline-hidden"
          role="dialog"
          aria-label="Dettaglio citazione"
          onClick={e => {
            if (e.target === e.currentTarget) setActiveCitation(null)
          }}
        >
          <section className={`w-full ${citationViewMode === 'pdf' && activeCitation.source.filename.toLowerCase().endsWith('.pdf') ? 'max-w-4xl' : 'max-w-2xl'} rounded-2xl border p-6 shadow-2xl transition-all duration-200 ${t.card}`}>
            <div className="flex items-start justify-between gap-4 pb-4 border-b border-white/10">
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="font-semibold text-base text-slate-900 dark:text-white">Citazione [{activeCitation.marker}]</h2>
                  <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-300">
                    Evidenza verificata
                  </span>
                  {(() => {
                    const badge = getFileBadge(activeCitation.source.filename)
                    return (
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${badge.color}`}>
                        {badge.label}
                      </span>
                    )
                  })()}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <span className="font-medium text-slate-200">{activeCitation.source.filename}</span>
                  <span>·</span>
                  <span>v{activeCitation.source.version}</span>
                  <span>·</span>
                  <span className="rounded-sm bg-blue-500/10 border border-blue-500/20 px-1.5 py-0.5 text-blue-300 font-mono text-[11px]">
                    {activeCitation.source.locator}
                  </span>
                  {activeCitation.source.library_name && (
                    <>
                      <span>·</span>
                      <span className="rounded-sm bg-indigo-500/10 border border-indigo-500/20 px-1.5 py-0.5 text-indigo-300 text-[11px] font-medium">
                        {activeCitation.source.library_name}
                      </span>
                    </>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setIsCitationDocked(true)}
                  className="hidden lg:flex items-center gap-1 text-[11px] font-semibold text-blue-300 hover:text-blue-200 px-2 py-1 rounded-lg border border-blue-500/20 bg-blue-500/10 hover:bg-blue-500/20 transition cursor-pointer"
                  title="Ancora il pannello a destra stile NotebookLM"
                >
                  <PanelRightOpen className="h-3.5 w-3.5" /> Ancora a lato
                </button>
                <button
                  onClick={() => setActiveCitation(null)}
                  className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-white/10 transition cursor-pointer"
                  aria-label="Chiudi citazione"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            {/* Contenuto citazione: Toggle Estratto / PDF per i file PDF */}
            {(() => {
              const isPdf = activeCitation.source.filename.toLowerCase().endsWith('.pdf')
              const pageMatch = activeCitation.source.locator.match(/Pagina\s+(\d+)/i)
              const pageNum = pageMatch ? pageMatch[1] : '1'
              const pdfUrl = `/api/libraries/${selectedLibraryId}/documents/${activeCitation.source.document_id}/download?inline=true#page=${pageNum}&view=FitH`

              return (
                <div className="mt-4">
                  {isPdf && (
                    <div className="flex items-center gap-1.5 p-0.5 rounded-lg bg-black/20 border border-white/10 w-fit mb-3">
                      <button
                        type="button"
                        onClick={() => setCitationViewMode('text')}
                        className={`px-3 py-1 text-xs rounded-md font-medium transition cursor-pointer ${
                          citationViewMode === 'text'
                            ? 'bg-blue-600 text-white shadow-xs'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        Estratto Testuale
                      </button>
                      <button
                        type="button"
                        onClick={() => setCitationViewMode('pdf')}
                        className={`px-3 py-1 text-xs rounded-md font-medium transition cursor-pointer flex items-center gap-1.5 ${
                          citationViewMode === 'pdf'
                            ? 'bg-rose-600 text-white shadow-xs'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        <FileText className="w-3.5 h-3.5" />
                        <span>Visualizza PDF (Pag. {pageNum})</span>
                      </button>
                    </div>
                  )}

                  {isPdf && citationViewMode === 'pdf' ? (
                    <div className="flex flex-col h-[52vh] rounded-xl border border-white/10 bg-slate-950 overflow-hidden shadow-inner">
                      <div className="flex items-center justify-between px-3 py-1.5 bg-slate-900 border-b border-white/10 text-xs">
                        <span className="text-slate-300 font-medium flex items-center gap-1.5">
                          <FileText className="w-3.5 h-3.5 text-rose-400" />
                          <span>{activeCitation.source.filename}</span>
                          <span className="text-slate-500">·</span>
                          <span className="text-rose-300 font-mono">Pagina {pageNum}</span>
                        </span>
                        <button
                          type="button"
                          onClick={() => window.open(pdfUrl, '_blank', 'noopener,noreferrer')}
                          className="text-blue-400 hover:text-blue-300 flex items-center gap-1 text-[11px] font-medium transition cursor-pointer"
                          title="Apri a tutto schermo in una nuova scheda"
                        >
                          <ExternalLink className="h-3 w-3" /> Schermo intero
                        </button>
                      </div>
                      <iframe
                        src={pdfUrl}
                        className="w-full flex-1 border-0 bg-slate-900"
                        title={`Anteprima PDF ${activeCitation.source.filename} a pagina ${pageNum}`}
                      />
                    </div>
                  ) : (
                    <div>
                      <p className="text-xs font-medium text-slate-400 mb-2">Passaggio nel documento</p>
                      <blockquote className="max-h-[50vh] overflow-y-auto doc-voice rounded-xl border border-amber-500/20 bg-amber-500/3 p-4 text-[15px] leading-relaxed text-slate-200 border-l-4 border-l-amber-400/70 shadow-inner">
                        <InlineMarkdown text={activeCitation.source.excerpt} />
                      </blockquote>
                    </div>
                  )}
                </div>
              )
            })()}
            <div className="mt-5 flex items-center justify-between gap-3 pt-3 border-t border-white/10">
              <button
                type="button"
                onClick={handleCopyCitation}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/5 hover:text-white cursor-pointer"
                title="Copia il testo della citazione"
              >
                {copiedCitation ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-emerald-400" />
                    <span className="text-emerald-300 font-medium">Copiato negli appunti!</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5 text-slate-400" />
                    <span>Copia estratto</span>
                  </>
                )}
              </button>
              <div className="flex items-center gap-2">
                {['csv', 'tsv', 'xlsx'].includes(activeCitation.source.filename.split('.').pop()?.toLowerCase() || '') && (
                  <button
                    type="button"
                    onClick={() => {
                      setTabularSource({
                        documentId: activeCitation.source.document_id,
                        filename: activeCitation.source.filename,
                      })
                    }}
                    className="flex items-center gap-1.5 rounded-lg border border-purple-500/30 bg-purple-500/15 hover:bg-purple-500/25 px-3.5 py-2 text-xs font-semibold text-purple-200 transition shadow-xs cursor-pointer"
                  >
                    <Table className="h-3.5 w-3.5 text-purple-400" /> Esplora Dati SQL
                  </button>
                )}
                <button
                  type="button"
                  onClick={() =>
                    window.open(
                      `/api/libraries/${selectedLibraryId}/documents/${activeCitation.source.document_id}/download`,
                      '_blank',
                      'noopener,noreferrer'
                    )
                  }
                  className="flex items-center gap-1.5 rounded-lg border border-blue-500/30 bg-blue-500/15 hover:bg-blue-500/25 px-4 py-2 text-xs font-semibold text-blue-200 transition shadow-xs cursor-pointer"
                >
                  <Download className="h-3.5 w-3.5 text-blue-400" /> Scarica originale
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
      {tabularSource && selectedLibraryId && (
        <TabularExplorerModal
          libraryId={selectedLibraryId}
          documentId={tabularSource.documentId}
          filename={tabularSource.filename}
          onClose={() => setTabularSource(null)}
        />
      )}
    </div>
  )
}
