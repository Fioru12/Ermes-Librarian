import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle, LockKeyhole, ShieldCheck, Sparkles } from 'lucide-react'
import UserManagement from './components/Admin/UserManagement'
import AuditLogs from './components/Admin/AuditLogs'
import Sidebar from './components/layout/Sidebar'
import ChatArea from './components/chat/ChatArea'
import DocumentsTab from './components/documents/DocumentsTab'
import HealthTab from './components/health/HealthTab'
import SettingsTab from './components/settings/SettingsTab'
import { ThemeProvider, useTheme } from './hooks/useTheme'
import type { HealthStatus, Message, TabId } from './types'

type LibrarySummary = { id: string; name: string; document_count?: number }

function AppInner() {
  const { t } = useTheme()
  const [activeTab, setActiveTab] = useState<TabId>('chat')
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [libraries, setLibraries] = useState<LibrarySummary[]>([])
  const [selectedLibraryId, setSelectedLibraryId] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [authState, setAuthState] = useState<'checking' | 'anonymous' | 'authenticated'>('checking')
  const [currentUser, setCurrentUser] = useState<{ username: string; role: string } | null>(null)
  const [loginUsername, setLoginUsername] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginError, setLoginError] = useState('')
  const [notif, setNotif] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const suggestions = [
    { title: 'Trova una procedura', desc: 'Cerca la procedura per richiedere ferie', prompt: 'Qual è la procedura per richiedere ferie?' },
    { title: 'Riassumi un documento', desc: 'Spiega i punti chiave di una policy', prompt: 'Riassumi i punti chiave della policy più recente.' },
    { title: 'Cerca una scadenza', desc: 'Trova le scadenze nei documenti', prompt: 'Quali scadenze importanti sono indicate nei documenti?' },
    { title: 'Confronta fonti', desc: 'Evidenzia differenze tra procedure', prompt: 'Ci sono differenze tra le procedure disponibili su questo argomento?' },
  ]

  const showNotif = (message: string, type: 'success' | 'error' = 'success') => {
    setNotif({ message, type })
    window.setTimeout(() => setNotif(null), 4000)
  }

  const fetchData = async () => {
    try {
      const [librariesResponse, healthResponse] = await Promise.all([
        fetch('/api/libraries', { credentials: 'include' }),
        fetch('/health', { credentials: 'include' }),
      ])
      if (librariesResponse.ok) {
        const data = await librariesResponse.json()
        const items: LibrarySummary[] = data.items ?? []
        setLibraries(items)
        setSelectedLibraryId(current => current && items.some(item => item.id === current) ? current : items[0]?.id ?? '')
      }
      if (healthResponse.ok) setHealth(await healthResponse.json())
    } catch {
      showNotif('Impossibile aggiornare lo stato dell’istanza', 'error')
    }
  }

  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(async response => {
        if (!response.ok) return setAuthState('anonymous')
        setCurrentUser(await response.json())
        setAuthState('authenticated')
      })
      .catch(() => setAuthState('anonymous'))
  }, [])

  useEffect(() => {
    if (authState === 'authenticated') fetchData()
  }, [authState])

  const sendQuestion = async (question: string) => {
    if (isGenerating || !question.trim()) return
    if (!selectedLibraryId) return showNotif('Seleziona una biblioteca prima di fare una domanda', 'error')
    const now = new Date().toLocaleTimeString()
    const answerId = crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)
    setMessages(previous => [
      ...previous,
      { id: crypto.randomUUID?.() ?? Math.random().toString(36).slice(2), role: 'user', content: question, timestamp: now },
      { id: answerId, role: 'assistant', content: '', timestamp: now },
    ])
    setInputMessage('')
    setIsGenerating(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/ask`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }), signal: controller.signal,
        credentials: 'include',
      })
      if (!response.ok) throw new Error('Impossibile interrogare la biblioteca')
      const data = await response.json()
      setMessages(previous => previous.map(message => message.id === answerId
        ? { ...message, content: data.answer, evidence: data.evidence, sources: data.citations ?? [] }
        : message))
    } catch (error) {
      const content = error instanceof DOMException && error.name === 'AbortError'
        ? 'Richiesta annullata.'
        : 'Non riesco a completare la richiesta. Riprova tra poco.'
      setMessages(previous => previous.map(message => message.id === answerId ? { ...message, content } : message))
    } finally {
      setIsGenerating(false)
      abortRef.current = null
    }
  }

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoginError('')
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: loginUsername, password: loginPassword }),
        credentials: 'include',
      })
      if (!response.ok) throw new Error('Credenziali non valide o login non configurato')
      setCurrentUser(await response.json())
      setLoginPassword('')
      setAuthState('authenticated')
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Accesso non riuscito')
    }
  }

  const tabHeaders: Record<TabId, string> = {
    chat: 'Assistente documentale', docs: 'Biblioteche e documenti', kb: 'Knowledge Graph',
    health: 'Stato sistema', providers: 'Provider LLM', settings: 'Impostazioni',
    'admin-users': 'Accessi e chiavi API', 'admin-audit': 'Audit log', 'admin-import': 'Import legacy',
  }

  if (authState !== 'authenticated') {
    return <main className={`ermes-app-shell ermes-grid flex min-h-screen items-center justify-center p-6 ${t.bg}`}>
      <div className="grid w-full max-w-5xl overflow-hidden rounded-3xl border border-white/10 bg-[#121722]/85 shadow-2xl shadow-slate-950/40 ermes-glass lg:grid-cols-[1.05fr_.95fr]">
        <section className="hidden min-h-[34rem] flex-col justify-between border-r border-white/[0.08] bg-gradient-to-br from-blue-600/20 via-slate-950/20 to-indigo-500/10 p-10 lg:flex">
          <div><div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-400 to-indigo-600 text-xl font-bold text-white shadow-lg shadow-blue-500/30">E</div><p className="mt-12 text-xs font-bold uppercase tracking-[0.2em] text-blue-300">ERMES Knowledge</p><h1 className="mt-4 max-w-md text-4xl font-semibold leading-tight tracking-tight text-white">La conoscenza aziendale, finalmente consultabile.</h1><p className="mt-5 max-w-md text-sm leading-6 text-slate-300">Organizza documenti, cerca passaggi e ottieni risposte legate alle fonti originali.</p></div>
          <div className="space-y-3 text-sm text-slate-300"><p className="flex items-center gap-3"><ShieldCheck className="h-4 w-4 text-emerald-400" />Local-first e controllato</p><p className="flex items-center gap-3"><Sparkles className="h-4 w-4 text-blue-300" />Risposte con citazioni verificabili</p></div>
        </section>
        <form onSubmit={handleLogin} className="flex min-h-[34rem] w-full flex-col justify-center p-7 sm:p-10">
          <div className="mb-8"><div className="mb-6 flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 text-blue-300 lg:hidden"><LockKeyhole className="h-5 w-5" /></div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-blue-400">Accesso protetto</p><h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">Accedi al tuo spazio</h2><p className="mt-2 text-sm leading-6 text-slate-400">Usa le credenziali configurate per questa installazione locale.</p></div>
          {authState === 'checking' ? <p className="mt-6 text-sm text-slate-400">Verifica sessione…</p> : <><label className="block text-sm font-medium text-slate-300">Utente<input value={loginUsername} onChange={event => setLoginUsername(event.target.value)} placeholder="nome utente" className={`mt-2 w-full rounded-xl border px-3.5 py-3 outline-none ${t.sidebarInput}`} autoComplete="username" /></label><label className="mt-5 block text-sm font-medium text-slate-300">Password<input type="password" value={loginPassword} onChange={event => setLoginPassword(event.target.value)} className={`mt-2 w-full rounded-xl border px-3.5 py-3 outline-none ${t.sidebarInput}`} autoComplete="current-password" /></label>{loginError && <p className="mt-4 rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{loginError}</p>}<button className="mt-7 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-3 font-semibold text-white shadow-lg shadow-blue-900/30 transition hover:from-blue-500 hover:to-indigo-500">Accedi <LockKeyhole className="h-4 w-4" /></button></>}
          <p className="mt-7 text-center text-xs leading-5 text-slate-500">Le tue sessioni restano protette su questa istanza Ermes.</p>
        </form>
      </div>
    </main>
  }

  return <div className={`ermes-app-shell flex h-screen overflow-hidden font-sans antialiased ${t.bg}`}>
    <Sidebar activeTab={activeTab} onTabChange={setActiveTab} healthStatus={health ? { status: health.status } : undefined} onRefresh={fetchData} isAdmin={currentUser?.role === 'admin'} username={currentUser?.username} />
    <main className="relative flex flex-1 flex-col overflow-hidden">
      {notif && <div className={`absolute right-4 top-4 z-50 flex items-center gap-2.5 rounded-xl border px-4 py-3 shadow-lg ${notif.type === 'error' ? 'border-rose-800 bg-rose-950/90 text-rose-200' : 'border-emerald-800 bg-emerald-950/90 text-emerald-200'}`}>{notif.type === 'error' ? <AlertTriangle className="h-4 w-4" /> : <CheckCircle className="h-4 w-4" />}<span className="text-sm font-medium">{notif.message}</span></div>}
      <header className={`z-10 flex h-[4.5rem] items-center justify-between border-b px-7 ${t.header}`}><div className="flex items-center gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Spazio di lavoro</p><h2 className={`mt-0.5 text-sm font-semibold ${t.cardTitle}`}>{tabHeaders[activeTab]}</h2></div><span className="hidden rounded-full border border-blue-500/20 bg-blue-500/10 px-2.5 py-1 text-[10px] font-semibold text-blue-400 sm:inline">Biblioteca locale</span></div><p className={`text-xs ${t.cardDesc}`}>Policy AI per singola biblioteca</p></header>
      <div className="flex-1 overflow-hidden">
        {activeTab === 'chat' && <ChatArea messages={messages} inputMessage={inputMessage} onInputChange={setInputMessage} onSend={sendQuestion} onStop={() => abortRef.current?.abort()} isGenerating={isGenerating} suggestions={suggestions} libraries={libraries} selectedLibraryId={selectedLibraryId} onLibraryChange={setSelectedLibraryId} selectedLibraryDocumentCount={libraries.find(library => library.id === selectedLibraryId)?.document_count ?? 0} onOpenLibraries={() => setActiveTab('docs')} />}
        {activeTab === 'docs' && <DocumentsTab showNotif={showNotif} />}
        {activeTab === 'health' && <HealthTab />}
        {activeTab === 'settings' && <SettingsTab showNotif={showNotif} isAdmin={currentUser?.role === 'admin'} />}
        {activeTab === 'admin-users' && currentUser?.role === 'admin' && <div className="h-full overflow-y-auto p-8"><UserManagement showNotif={showNotif} /></div>}
        {activeTab === 'admin-audit' && currentUser?.role === 'admin' && <div className="h-full overflow-y-auto p-8"><AuditLogs showNotif={showNotif} /></div>}
      </div>
    </main>
  </div>
}

export default function App() {
  return <ThemeProvider><AppInner /></ThemeProvider>
}
