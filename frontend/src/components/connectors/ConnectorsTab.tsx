import { useEffect, useState } from 'react'
import {
  FolderCheck,
  Globe,
  HardDrive,
  Bot,
  Zap,
  CheckCircle2,
  AlertCircle,
  Copy,
  RefreshCw,
  Cloud,
  Layers,
} from 'lucide-react'

interface Library {
  id: string
  name: string
}

interface ConnectorsTabProps {
  showNotif: (msg: string, type?: 'success' | 'error') => void
}

export default function ConnectorsTab({ showNotif }: ConnectorsTabProps) {
  const [libraries, setLibraries] = useState<Library[]>([])
  const [selectedLibrary, setSelectedLibrary] = useState<string>('')
  
  // Local folder state
  const [folderPath, setFolderPath] = useState<string>('')
  const [isFolderTesting, setIsFolderTesting] = useState<boolean>(false)
  const [isFolderSyncing, setIsFolderSyncing] = useState<boolean>(false)
  const [folderStatus, setFolderStatus] = useState<{ ok?: boolean; message?: string } | null>(null)

  // Web scraper state
  const [webUrl, setWebUrl] = useState<string>('')
  const [isWebTesting, setIsWebTesting] = useState<boolean>(false)
  const [isWebSyncing, setIsWebSyncing] = useState<boolean>(false)
  const [webStatus, setWebStatus] = useState<{ ok?: boolean; message?: string } | null>(null)

  // Microsoft Graph (SharePoint / OneDrive) state
  const [msTenantId, setMsTenantId] = useState<string>('')
  const [msClientId, setMsClientId] = useState<string>('')
  const [msClientSecret, setMsClientSecret] = useState<string>('')
  const [msDriveId, setMsDriveId] = useState<string>('')
  const [msFolderPath, setMsFolderPath] = useState<string>('/')
  const [isMsTesting, setIsMsTesting] = useState<boolean>(false)
  const [isMsSyncing, setIsMsSyncing] = useState<boolean>(false)
  const [msStatus, setMsStatus] = useState<{ ok?: boolean; message?: string } | null>(null)

  // Folder Watcher state
  const [watcherStatus, setWatcherStatus] = useState<{ active?: boolean; monitored_sources_count?: number } | null>(null)
  const [isWatcherSyncing, setIsWatcherSyncing] = useState<boolean>(false)

  useEffect(() => {
    fetchLibraries()
    fetchWatcherStatus()
  }, [])

  const fetchLibraries = async () => {
    try {
      const res = await fetch('/api/libraries', { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        const libs = data.items || data.libraries || []
        setLibraries(libs)
        if (libs.length > 0) {
          setSelectedLibrary(libs[0].id)
        }
      }
    } catch {
      // ignore
    }
  }

  const fetchWatcherStatus = async () => {
    try {
      const res = await fetch('/api/connectors/watcher/status', { credentials: 'include' })
      if (res.ok) {
        setWatcherStatus(await res.json())
      }
    } catch {
      // ignore
    }
  }

  const handleTestFolder = async () => {
    if (!folderPath.trim()) {
      showNotif('Inserisci un percorso cartella valido', 'error')
      return
    }
    setIsFolderTesting(true)
    setFolderStatus(null)
    try {
      const res = await fetch('/api/connectors/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          type: 'local_folder',
          config: { folder_path: folderPath },
        }),
      })
      const data = await res.json()
      if (res.ok && data.ok) {
        setFolderStatus({ ok: true, message: data.message })
        showNotif('Connessione cartella verificata con successo!', 'success')
      } else {
        setFolderStatus({ ok: false, message: data.message || data.detail || 'Errore durante la verifica' })
        showNotif(data.message || data.detail || 'Verifica cartella fallita', 'error')
      }
    } catch (err: any) {
      setFolderStatus({ ok: false, message: err.message || 'Errore di rete' })
      showNotif('Impossibile verificare la cartella', 'error')
    } finally {
      setIsFolderTesting(false)
    }
  }

  const handleSyncFolder = async () => {
    if (!selectedLibrary) {
      showNotif('Seleziona una biblioteca di destinazione', 'error')
      return
    }
    if (!folderPath.trim()) {
      showNotif('Inserisci un percorso cartella valido', 'error')
      return
    }
    setIsFolderSyncing(true)
    try {
      const res = await fetch('/api/connectors/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          type: 'local_folder',
          target_library_id: selectedLibrary,
          config: { folder_path: folderPath },
        }),
      })
      const data = await res.json()
      if (res.ok) {
        showNotif(`Sincronizzati ${data.synced_count} documenti con successo!`, 'success')
      } else {
        showNotif(data.detail || 'Errore durante la sincronizzazione', 'error')
      }
    } catch (err: any) {
      showNotif('Impossibile completare la sincronizzazione', 'error')
    } finally {
      setIsFolderSyncing(false)
    }
  }

  const handleTestWeb = async () => {
    if (!webUrl.trim()) {
      showNotif('Inserisci un URL valido', 'error')
      return
    }
    setIsWebTesting(true)
    setWebStatus(null)
    try {
      const res = await fetch('/api/connectors/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          type: 'web_scraper',
          config: { base_url: webUrl },
        }),
      })
      const data = await res.json()
      if (res.ok && data.ok) {
        setWebStatus({ ok: true, message: data.message })
        showNotif('Sito web raggiungibile!', 'success')
      } else {
        setWebStatus({ ok: false, message: data.message || data.detail || 'Impossibile raggiungere il sito' })
        showNotif(data.message || data.detail || 'Verifica web fallita', 'error')
      }
    } catch (err: any) {
      setWebStatus({ ok: false, message: err.message || 'Errore di rete' })
      showNotif('Errore durante la connessione web', 'error')
    } finally {
      setIsWebTesting(false)
    }
  }

  const handleSyncWeb = async () => {
    if (!selectedLibrary) {
      showNotif('Seleziona una biblioteca di destinazione', 'error')
      return
    }
    if (!webUrl.trim()) {
      showNotif('Inserisci un URL valido', 'error')
      return
    }
    setIsWebSyncing(true)
    try {
      const res = await fetch('/api/connectors/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          type: 'web_scraper',
          target_library_id: selectedLibrary,
          config: { base_url: webUrl, max_pages: 5 },
        }),
      })
      const data = await res.json()
      if (res.ok) {
        showNotif(`Scraping completato! Importate ${data.imported_count ?? data.synced_count ?? 0} pagine web.`, 'success')
      } else {
        showNotif(data.detail || 'Errore durante lo scraping', 'error')
      }
    } catch (err: any) {
      showNotif('Impossibile completare lo scraping', 'error')
    } finally {
      setIsWebSyncing(false)
    }
  }

  const getMsConfig = () => ({
    tenant_id: msTenantId,
    client_id: msClientId,
    client_secret: msClientSecret,
    drive_id: msDriveId,
    folder_path: msFolderPath || '/',
  })

  const handleTestMs = async () => {
    if (!msTenantId.trim() || !msClientId.trim() || !msClientSecret.trim()) {
      showNotif('Inserisci Tenant ID, Client ID e Client Secret Microsoft', 'error')
      return
    }
    setIsMsTesting(true)
    setMsStatus(null)
    try {
      const res = await fetch('/api/connectors/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ type: 'microsoft_graph', config: getMsConfig() }),
      })
      const data = await res.json()
      if (res.ok && data.ok) {
        setMsStatus({ ok: true, message: data.message })
        showNotif('Connessione Microsoft Graph verificata!', 'success')
      } else {
        setMsStatus({ ok: false, message: data.message || data.detail || 'Errore durante la verifica' })
        showNotif(data.message || data.detail || 'Verifica Microsoft Graph fallita', 'error')
      }
    } catch (err: any) {
      setMsStatus({ ok: false, message: err.message || 'Errore di rete' })
      showNotif('Impossibile verificare Microsoft Graph', 'error')
    } finally {
      setIsMsTesting(false)
    }
  }

  const handleSyncMs = async () => {
    if (!selectedLibrary) {
      showNotif('Seleziona una biblioteca di destinazione', 'error')
      return
    }
    if (!msTenantId.trim() || !msClientId.trim() || !msClientSecret.trim()) {
      showNotif('Inserisci le credenziali Microsoft Graph', 'error')
      return
    }
    setIsMsSyncing(true)
    try {
      const res = await fetch('/api/connectors/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          type: 'microsoft_graph',
          target_library_id: selectedLibrary,
          config: getMsConfig(),
        }),
      })
      const data = await res.json()
      if (res.ok) {
        showNotif(`Sincronizzati ${data.imported_count} documenti Microsoft 365!`, 'success')
      } else {
        showNotif(data.detail || 'Errore durante la sincronizzazione', 'error')
      }
    } catch (err: any) {
      showNotif('Impossibile completare la sincronizzazione Microsoft', 'error')
    } finally {
      setIsMsSyncing(false)
    }
  }

  const handleWatcherSync = async () => {
    setIsWatcherSyncing(true)
    try {
      const res = await fetch('/api/connectors/watcher/sync', {
        method: 'POST',
        credentials: 'include',
      })
      const data = await res.json()
      if (res.ok) {
        showNotif('Sincronizzazione forzata completata!', 'success')
        fetchWatcherStatus()
      } else {
        showNotif(data.detail || 'Errore durante la sincronizzazione', 'error')
      }
    } catch (err: any) {
      showNotif('Impossibile forzare la sincronizzazione', 'error')
    } finally {
      setIsWatcherSyncing(false)
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    showNotif('Copiato negli appunti!', 'success')
  }

  const mcpConfigJson = JSON.stringify(
    {
      mcpServers: {
        "ermes-knowledge": {
          url: "http://127.0.0.1:8502/api/mcp/rpc",
          headers: {
            "X-API-Key": "<TUA_API_KEY>"
          }
        }
      }
    },
    null,
    2
  )

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-3">
          <HardDrive className="w-7 h-7 text-blue-400" /> Connettori & Integrazioni Enterprise
        </h2>
        <p className="text-sm text-slate-400 mt-1">
          Sincronizza documenti da cartelle di rete local-first, siti web ed esponi Ermes ad agenti AI (MCP) e workflow di automazione (n8n/Zapier).
        </p>
      </div>

      {/* Target Library Selector */}
      <div className="rounded-xl border border-white/10 bg-slate-900/60 p-4 flex flex-col md:flex-row md:items-center gap-4 justify-between shadow-lg">
        <div>
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 block mb-1">
            Biblioteca di destinazione per le sincronizzazioni
          </label>
          <p className="text-xs text-slate-400">
            I documenti importati verranno associati ed indicizzati direttamente in questa biblioteca.
          </p>
        </div>
        <select
          value={selectedLibrary}
          onChange={(e) => setSelectedLibrary(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {libraries.map((lib) => (
            <option key={lib.id} value={lib.id}>
              {lib.name} ({lib.id})
            </option>
          ))}
        </select>
      </div>

      {/* Folder Watcher Status */}
      <div className="rounded-xl border border-white/10 bg-slate-900/60 p-4 flex flex-col md:flex-row md:items-center gap-4 justify-between shadow-lg">
        <div className="flex items-center gap-3">
          <Layers className="w-6 h-6 text-indigo-400" />
          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-slate-300 block mb-1">
              Folder Watcher — Monitoraggio automatico cartelle registrate
            </label>
            <p className="text-xs text-slate-400">
              {watcherStatus
                ? `${watcherStatus.active ? 'Attivo' : 'Inattivo'} — ${watcherStatus.monitored_sources_count ?? 0} sorgenti monitorate`
                : 'Stato non disponibile'}
            </p>
          </div>
        </div>
        <button
          onClick={handleWatcherSync}
          disabled={isWatcherSyncing}
          className="px-4 py-2 text-xs font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center gap-2 shadow-lg shadow-indigo-600/20"
        >
          {isWatcherSyncing && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
          Sincronizza ora tutte le cartelle
        </button>
      </div>

      {/* Grid Connectors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* NAS / Local Folder Connector */}
        <div className="rounded-xl border border-white/10 bg-slate-900/50 p-6 flex flex-col justify-between space-y-5 hover:border-blue-500/30 transition-all shadow-md">
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-blue-400 font-semibold text-lg">
              <FolderCheck className="w-6 h-6" /> NAS & Cartella Locale
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Scansiona ed indicizza cartelle di rete aziendali (SMB/NFS) o directory locali (.pdf, .docx, .txt, .md).
            </p>
            <div className="space-y-2 pt-2">
              <label className="text-xs font-medium text-slate-300">Percorso Cartella (locale o UNC)</label>
              <input
                type="text"
                placeholder="es. C:\Documenti\Procedure oppure \\nas\share\docs"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            {folderStatus && (
              <div
                className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
                  folderStatus.ok
                    ? 'bg-emerald-950/40 border border-emerald-500/30 text-emerald-300'
                    : 'bg-rose-950/40 border border-rose-500/30 text-rose-300'
                }`}
              >
                {folderStatus.ok ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                {folderStatus.message}
              </div>
            )}
          </div>
          <div className="flex gap-3 pt-2">
            <button
              onClick={handleTestFolder}
              disabled={isFolderTesting}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition border border-slate-700 flex items-center gap-2"
            >
              {isFolderTesting && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
              Testa percorso
            </button>
            <button
              onClick={handleSyncFolder}
              disabled={isFolderSyncing}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition flex items-center gap-2 shadow-lg shadow-blue-600/20"
            >
              {isFolderSyncing && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
              Sincronizza ora
            </button>
          </div>
        </div>

        {/* Web Scraper / Intranet Connector */}
        <div className="rounded-xl border border-white/10 bg-slate-900/50 p-6 flex flex-col justify-between space-y-5 hover:border-purple-500/30 transition-all shadow-md">
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-purple-400 font-semibold text-lg">
              <Globe className="w-6 h-6" /> Web Scraper / Intranet Wiki
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Estrae e converte in Markdown le pagine di wiki aziendali o portali web pubblici/intranet.
            </p>
            <div className="space-y-2 pt-2">
              <label className="text-xs font-medium text-slate-300">URL Base Portale Web</label>
              <input
                type="text"
                placeholder="es. https://intranet.azienda.local/wiki"
                value={webUrl}
                onChange={(e) => setWebUrl(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            {webStatus && (
              <div
                className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
                  webStatus.ok
                    ? 'bg-emerald-950/40 border border-emerald-500/30 text-emerald-300'
                    : 'bg-rose-950/40 border border-rose-500/30 text-rose-300'
                }`}
              >
                {webStatus.ok ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                {webStatus.message}
              </div>
            )}
          </div>
          <div className="flex gap-3 pt-2">
            <button
              onClick={handleTestWeb}
              disabled={isWebTesting}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition border border-slate-700 flex items-center gap-2"
            >
              {isWebTesting && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
              Testa URL
            </button>
            <button
              onClick={handleSyncWeb}
              disabled={isWebSyncing}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-purple-600 hover:bg-purple-500 text-white transition flex items-center gap-2 shadow-lg shadow-purple-600/20"
            >
              {isWebSyncing && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
              Avvia Scraping
            </button>
          </div>
        </div>

        {/* M365 / SharePoint / OneDrive Connector */}
        <div className="rounded-xl border border-white/10 bg-slate-900/50 p-6 flex flex-col justify-between space-y-5 hover:border-sky-500/30 transition-all shadow-md">
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-sky-400 font-semibold text-lg">
              <Cloud className="w-6 h-6" /> Microsoft 365 (SharePoint / OneDrive)
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Collegati a Microsoft Graph (OAuth2 client credentials) per indicizzare documenti da SharePoint e OneDrive for Business.
            </p>
            <div className="space-y-2 pt-2">
              <label className="text-xs font-medium text-slate-300">Tenant ID</label>
              <input
                type="text"
                placeholder="es. 12345678-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                value={msTenantId}
                onChange={(e) => setMsTenantId(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
              <label className="text-xs font-medium text-slate-300">Client ID</label>
              <input
                type="text"
                placeholder="Azure Application (Client) ID"
                value={msClientId}
                onChange={(e) => setMsClientId(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
              <label className="text-xs font-medium text-slate-300">Client Secret</label>
              <input
                type="password"
                placeholder="Azure Application Secret"
                value={msClientSecret}
                onChange={(e) => setMsClientSecret(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
              <label className="text-xs font-medium text-slate-300">Drive ID (opzionale)</label>
              <input
                type="text"
                placeholder="es. 0B7g34... (lascia vuoto per OneDrive personale)"
                value={msDriveId}
                onChange={(e) => setMsDriveId(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
              <label className="text-xs font-medium text-slate-300">Percorso cartella remota</label>
              <input
                type="text"
                placeholder="es. /Documenti Condivisi"
                value={msFolderPath}
                onChange={(e) => setMsFolderPath(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>
            {msStatus && (
              <div
                className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
                  msStatus.ok
                    ? 'bg-emerald-950/40 border border-emerald-500/30 text-emerald-300'
                    : 'bg-rose-950/40 border border-rose-500/30 text-rose-300'
                }`}
              >
                {msStatus.ok ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                {msStatus.message}
              </div>
            )}
          </div>
          <div className="flex gap-3 pt-2">
            <button
              onClick={handleTestMs}
              disabled={isMsTesting}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition border border-slate-700 flex items-center gap-2"
            >
              {isMsTesting && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
              Testa connessione
            </button>
            <button
              onClick={handleSyncMs}
              disabled={isMsSyncing}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-sky-600 hover:bg-sky-500 text-white transition flex items-center gap-2 shadow-lg shadow-sky-600/20"
            >
              {isMsSyncing && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
              Sincronizza ora
            </button>
          </div>
        </div>
      </div>

      {/* Advanced Integrations Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4">
        {/* MCP Server Integration */}
        <div className="rounded-xl border border-white/10 bg-slate-900/60 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-emerald-400 font-semibold text-lg">
              <Bot className="w-6 h-6" /> Server MCP (Model Context Protocol)
            </div>
            <span className="text-[10px] font-mono uppercase bg-emerald-950 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/30">
              JSON-RPC 2.0
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Collega Ermes a client AI come <strong>Claude Desktop, Cursor, Antigravity o LangChain</strong> per risposte con fonti tracciate.
          </p>
          <div className="relative bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-[11px] text-slate-300 overflow-x-auto">
            <button
              onClick={() => copyToClipboard(mcpConfigJson)}
              className="absolute top-2 right-2 p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
              title="Copia configurazione JSON"
            >
              <Copy className="w-3.5 h-3.5" />
            </button>
            <pre>{mcpConfigJson}</pre>
          </div>
          <p className="text-[11px] text-slate-500">
            Endpoint attivo su: <code className="text-emerald-400">/api/mcp/rpc</code>
          </p>
        </div>

        {/* Automation Webhook Gateway */}
        <div className="rounded-xl border border-white/10 bg-slate-900/60 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-amber-400 font-semibold text-lg">
              <Zap className="w-6 h-6" /> Webhook Automazioni (n8n / Zapier)
            </div>
            <span className="text-[10px] font-mono uppercase bg-amber-950 text-amber-400 px-2 py-0.5 rounded border border-amber-500/30">
              REST Webhooks
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Interroga biblioteche o carica documenti da workflow automatici tramite API Key.
          </p>
          <div className="space-y-2 bg-slate-950 p-3 rounded-lg border border-slate-800 text-[11px] font-mono text-slate-300">
            <p className="text-amber-400 font-semibold">POST /api/integrations/automation/ask</p>
            <p className="text-slate-500">Body: &#123; "library_id": "...", "question": "..." &#125;</p>
            <hr className="border-slate-800 my-2" />
            <p className="text-amber-400 font-semibold">POST /api/integrations/automation/ingest</p>
            <p className="text-slate-500">Body: &#123; "library_id": "...", "filename": "...", "content": "..." &#125;</p>
          </div>
          <p className="text-[11px] text-slate-500">
            Autenticazione via header: <code className="text-amber-400">X-API-Key: &lt;TUA_API_KEY&gt;</code>
          </p>
        </div>
      </div>
    </div>
  )
}
