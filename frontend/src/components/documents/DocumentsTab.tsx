import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Clock3, Download, FileText, FolderCog, FolderPlus, Library, RefreshCw, Search, ShieldCheck, Trash2, Upload, UserPlus, Users, XCircle } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { CardTitle } from '../../components/ui'

interface LibraryItem {
  id: string
  name: string
  description: string
  visibility: 'private' | 'shared'
  assistant_mode: 'evidence_only' | 'local_ollama' | 'approved_openrouter' | 'approved_provider'
  assistant_provider?: string
  document_count: number
  access_role?: 'admin' | 'owner' | 'editor' | 'viewer'
}

interface LibraryDocument {
  id: string
  filename: string
  media_type: string
  size_bytes: number
  version: number
  status: string
}

interface SearchResult {
  document_id: string
  filename: string
  excerpt: string
  citation: { version: number; locator: string }
}

interface RetrievalProfile {
  mode: 'keyword' | 'hybrid_local'
  semantic_indexed_chunks: number
  semantic_used: boolean
}

interface DocumentVersion {
  version: number
  size_bytes: number
  created_at: string
}

interface LibraryMember {
  username: string
  role: 'owner' | 'viewer' | 'editor'
  created_at: string
}

interface ApprovedProvider {
  name: string
  type: string
  default_model: string
}

interface DocumentAclEntry {
  username: string
  created_at: string
}

interface ImportSource {
  id: string
  path: string
  created_by: string
  last_scan_at: string | null
  created_at: string
}

interface ScanResult {
  imported: { filename: string }[]
  skipped_duplicates: string[]
  skipped_unsupported: string[]
  failed: { file: string; error: string }[]
}

interface DocumentsTabProps {
  showNotif: (msg: string, type?: 'success' | 'error') => void
}

const formatSize = (size: number) => size < 1024 * 1024
  ? `${Math.max(1, Math.round(size / 1024))} KB`
  : `${(size / (1024 * 1024)).toFixed(1)} MB`

const documentStatus = (status: string) => {
  if (status === 'ready') return { label: 'Pronto', className: 'bg-emerald-500/10 text-emerald-400', Icon: CheckCircle2 }
  if (status === 'failed') return { label: 'Errore import', className: 'bg-rose-500/10 text-rose-400', Icon: XCircle }
  if (status === 'processing') return { label: 'Indicizzazione', className: 'bg-blue-500/10 text-blue-400', Icon: RefreshCw }
  return { label: 'In attesa', className: 'bg-amber-500/10 text-amber-400', Icon: Clock3 }
}

export default function DocumentsTab({ showNotif }: DocumentsTabProps) {
  const { t } = useTheme()
  const [libraries, setLibraries] = useState<LibraryItem[]>([])
  const [documents, setDocuments] = useState<LibraryDocument[]>([])
  const [selectedLibraryId, setSelectedLibraryId] = useState<string | null>(null)
  const [newLibraryName, setNewLibraryName] = useState('')
  const [loadingLibraries, setLoadingLibraries] = useState(true)
  const [loadingDocuments, setLoadingDocuments] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null)
  const [retrievalProfile, setRetrievalProfile] = useState<RetrievalProfile | null>(null)
  const [searching, setSearching] = useState(false)
  const [searchScopeDoc, setSearchScopeDoc] = useState<LibraryDocument | null>(null)
  const [versionHistory, setVersionHistory] = useState<{ document: LibraryDocument; items: DocumentVersion[] } | null>(null)
  const [members, setMembers] = useState<LibraryMember[]>([])
  const [canManageMembers, setCanManageMembers] = useState(false)
  const [showMembers, setShowMembers] = useState(false)
  const [memberUsername, setMemberUsername] = useState('')
  const [memberRole, setMemberRole] = useState<'viewer' | 'editor'>('viewer')
  const [savingMember, setSavingMember] = useState(false)
  const [approvedProviders, setApprovedProviders] = useState<ApprovedProvider[]>([])
  const [aclPanel, setAclPanel] = useState<{ document: LibraryDocument; usernames: string[] } | null>(null)
  const [aclUsername, setAclUsername] = useState('')
  const [savingAcl, setSavingAcl] = useState(false)
  const [summaryPanel, setSummaryPanel] = useState<{ document: LibraryDocument; status: string; summary: string; mode: string; reason: string } | null>(null)
  const [summarizing, setSummarizing] = useState(false)
  const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(null)
  const [deletingLibrary, setDeletingLibrary] = useState(false)
  const [sources, setSources] = useState<ImportSource[]>([])
  const [showSources, setShowSources] = useState(false)
  const [newSourcePath, setNewSourcePath] = useState('')
  const [addingSource, setAddingSource] = useState(false)
  const [scanningSourceId, setScanningSourceId] = useState<string | null>(null)

  const selectedLibrary = libraries.find(library => library.id === selectedLibraryId) ?? null
  const canEditLibrary = selectedLibrary?.access_role === 'admin' || selectedLibrary?.access_role === 'owner' || selectedLibrary?.access_role === 'editor'
  // Sorgenti cartella e cancellazione biblioteca concedono al server accesso
  // in lettura a un percorso scelto dall'attore, o distruggono l'intera
  // biblioteca: stessa soglia usata lato backend (owner o admin globale),
  // non un editor collaboratore qualsiasi.
  const canManageLibrary = selectedLibrary?.access_role === 'admin' || selectedLibrary?.access_role === 'owner'

  const fetchLibraries = async () => {
    setLoadingLibraries(true)
    try {
      const response = await fetch('/api/libraries', { credentials: 'include' })
      if (!response.ok) throw new Error('libraries unavailable')
      const data = await response.json()
      const items = data.items ?? []
      setLibraries(items)
      setSelectedLibraryId(current => current && items.some((item: LibraryItem) => item.id === current) ? current : items[0]?.id ?? null)
    } catch {
      setLibraries([])
      showNotif('Impossibile caricare le biblioteche', 'error')
    } finally {
      setLoadingLibraries(false)
    }
  }

  const fetchDocuments = async (libraryId: string) => {
    setLoadingDocuments(true)
    try {
      const response = await fetch(`/api/libraries/${libraryId}/documents`, { credentials: 'include' })
      if (!response.ok) throw new Error('documents unavailable')
      const data = await response.json()
      setDocuments(data.items ?? [])
    } catch {
      setDocuments([])
      showNotif('Impossibile caricare i documenti', 'error')
    } finally {
      setLoadingDocuments(false)
    }
  }

  const fetchMembers = async (libraryId: string) => {
    try {
      const response = await fetch(`/api/libraries/${libraryId}/members`, { credentials: 'include' })
      if (!response.ok) {
        setCanManageMembers(false)
        setMembers([])
        setShowMembers(false)
        return
      }
      const data = await response.json()
      setMembers(data.items ?? [])
      setCanManageMembers(true)
    } catch {
      setCanManageMembers(false)
      setMembers([])
    }
  }

  const fetchSources = async (libraryId: string) => {
    try {
      const response = await fetch(`/api/libraries/${libraryId}/sources`, { credentials: 'include' })
      if (!response.ok) { setSources([]); return }
      const data = await response.json()
      setSources(data.items ?? [])
    } catch {
      setSources([])
    }
  }

  const fetchApprovedProviders = async (libraryId: string) => {
    try {
      const response = await fetch(`/api/libraries/${libraryId}/assistant-options`, { credentials: 'include' })
      if (!response.ok) {
        setApprovedProviders([])
        return
      }
      const data = await response.json()
      setApprovedProviders(data.items ?? [])
    } catch {
      setApprovedProviders([])
    }
  }

  useEffect(() => { fetchLibraries() }, [])
  useEffect(() => {
    if (selectedLibraryId) fetchDocuments(selectedLibraryId)
    else setDocuments([])
    setSearchQuery('')
    setSearchResults(null)
    setRetrievalProfile(null)
    setSearchScopeDoc(null)
  }, [selectedLibraryId])

  useEffect(() => {
    if (selectedLibraryId) fetchMembers(selectedLibraryId)
    else {
      setMembers([])
      setCanManageMembers(false)
      setShowMembers(false)
    }
  }, [selectedLibraryId])

  useEffect(() => {
    if (selectedLibraryId && canEditLibrary) fetchApprovedProviders(selectedLibraryId)
    else setApprovedProviders([])
  }, [selectedLibraryId, canEditLibrary])

  useEffect(() => {
    if (selectedLibraryId && canManageLibrary) fetchSources(selectedLibraryId)
    else { setSources([]); setShowSources(false) }
  }, [selectedLibraryId, canManageLibrary])

  useEffect(() => {
    if (!selectedLibraryId || !documents.some(document => document.status === 'queued' || document.status === 'processing')) return
    const timer = window.setTimeout(() => fetchDocuments(selectedLibraryId), 2500)
    return () => window.clearTimeout(timer)
  }, [documents, selectedLibraryId])

  const searchDocuments = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!selectedLibraryId || searchQuery.trim().length < 2) return
    setSearching(true)
    try {
      const endpoint = searchScopeDoc
        ? `/api/libraries/${selectedLibraryId}/documents/${searchScopeDoc.id}/search?q=${encodeURIComponent(searchQuery.trim())}`
        : `/api/libraries/${selectedLibraryId}/search?q=${encodeURIComponent(searchQuery.trim())}`
      const response = await fetch(endpoint)
      if (!response.ok) throw new Error('search failed')
      const data = await response.json()
      setSearchResults(data.items ?? [])
      setRetrievalProfile(data.retrieval_profile ?? null)
    } catch {
      showNotif('Impossibile cercare nei documenti', 'error')
    } finally {
      setSearching(false)
    }
  }

  const createLibrary = async (event: React.FormEvent) => {
    event.preventDefault()
    const name = newLibraryName.trim()
    if (!name) return
    try {
      const response = await fetch('/api/libraries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, visibility: 'private' }),
      })
      if (!response.ok) throw new Error('create failed')
      const library = await response.json()
      setNewLibraryName('')
      await fetchLibraries()
      setSelectedLibraryId(library.id)
      showNotif(`Biblioteca “${library.name}” creata`)
    } catch {
      showNotif('Impossibile creare la biblioteca', 'error')
    }
  }

  const changeAssistantMode = async (mode: LibraryItem['assistant_mode'], providerName = '') => {
    if (!selectedLibrary) return
    const providerLabel = mode === 'approved_provider' ? providerName : 'OpenRouter'
    if ((mode === 'approved_openrouter' || mode === 'approved_provider') && !window.confirm(`I passaggi recuperati da questa biblioteca potranno essere inviati a ${providerLabel} per generare le risposte. Vuoi continuare?`)) return
    try {
      const response = await fetch(`/api/libraries/${selectedLibrary.id}/assistant-policy`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode, provider_name: providerName }),
      })
      if (!response.ok) throw new Error('policy update failed')
      const updated = await response.json()
      setLibraries(current => current.map(item => item.id === selectedLibrary.id ? { ...item, assistant_mode: updated.assistant_mode, assistant_provider: updated.assistant_provider } : item))
      showNotif(mode === 'approved_provider' ? `${providerName} attivato per questa biblioteca` : mode === 'approved_openrouter' ? 'OpenRouter attivato per questa biblioteca' : 'Policy assistente aggiornata')
    } catch {
      showNotif('Impossibile aggiornare la policy dell’assistente', 'error')
    }
  }

  const uploadDocument = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file || !selectedLibraryId) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/documents`, {  method: 'POST', body: formData, credentials: 'include' })
      if (!response.ok) throw new Error('upload failed')
      showNotif(`Documento “${file.name}” aggiunto alla biblioteca`)
      await fetchDocuments(selectedLibraryId)
      await fetchLibraries()
    } catch {
      showNotif('Impossibile caricare il documento', 'error')
    } finally {
      event.target.value = ''
    }
  }

  const reindexDocument = async (document: LibraryDocument) => {
    if (!selectedLibraryId) return
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/documents/${document.id}/reindex`, {  method: 'POST', credentials: 'include' })
      if (!response.ok) throw new Error('reindex failed')
      await fetchDocuments(selectedLibraryId)
      showNotif(`Indice aggiornato: ${document.filename}`)
    } catch {
      showNotif('Impossibile reindicizzare il documento', 'error')
    }
  }

  const downloadDocument = (document: LibraryDocument) => {
    if (!selectedLibraryId) return
    window.open(`/api/libraries/${selectedLibraryId}/documents/${document.id}/download`, '_blank', 'noopener,noreferrer')
  }

  const showSummary = async (document: LibraryDocument) => {
    if (!selectedLibraryId) return
    setSummarizing(true)
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/documents/${document.id}/summary`, { credentials: 'include' })
      if (!response.ok) throw new Error('summary unavailable')
      const data = await response.json()
      setSummaryPanel({
        document,
        status: data.status ?? 'abstained',
        summary: data.summary ?? '',
        mode: data.mode ?? '',
        reason: data.reason ?? '',
      })
    } catch {
      showNotif('Impossibile generare il riassunto', 'error')
    } finally {
      setSummarizing(false)
    }
  }

  const saveDocumentAcl = async (documentId: string, usernames: string[]) => {
    if (!selectedLibraryId) return false
    setSavingAcl(true)
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/documents/${documentId}/acl`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ usernames }),
      })
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail ?? 'acl update failed')
      }
      setAclPanel(current => current && current.document.id === documentId ? { ...current, usernames } : current)
      showNotif(usernames.length ? `Accesso limitato a: ${usernames.join(', ')}` : 'Restrizioni rimosse: documento visibile alla biblioteca')
      return true
    } catch (error) {
      showNotif(error instanceof Error && error.message.includes('Utenti sconosciuti') ? error.message : 'Impossibile aggiornare le restrizioni del documento', 'error')
      return false
    } finally {
      setSavingAcl(false)
    }
  }

  const openAclPanel = async (document: LibraryDocument) => {
    if (!selectedLibraryId || !canManageMembers) return
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/documents/${document.id}/acl`, { credentials: 'include' })
      if (!response.ok) throw new Error('acl unavailable')
      const data = await response.json()
      setAclPanel({ document, usernames: (data.items as DocumentAclEntry[]).map(item => item.username) })
      setAclUsername('')
    } catch {
      showNotif('Impossibile leggere le restrizioni del documento', 'error')
    }
  }

  const addAclUser = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!aclPanel) return
    const username = aclUsername.trim()
    if (!username || aclPanel.usernames.includes(username)) return
    if (await saveDocumentAcl(aclPanel.document.id, [...aclPanel.usernames, username])) setAclUsername('')
  }

  const removeAclUser = async (username: string) => {
    if (!aclPanel) return
    await saveDocumentAcl(aclPanel.document.id, aclPanel.usernames.filter(item => item !== username))
  }

  const showVersions = async (document: LibraryDocument) => {
    if (!selectedLibraryId) return
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/documents/${document.id}/versions`, { credentials: 'include' })
      if (!response.ok) throw new Error('versions unavailable')
      const data = await response.json()
      setVersionHistory({ document, items: data.items ?? [] })
    } catch {
      showNotif('Impossibile caricare lo storico versioni', 'error')
    }
  }

  const restoreVersion = async (version: number) => {
    if (!selectedLibraryId || !versionHistory) return
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/documents/${versionHistory.document.id}/versions/${version}/restore`, {  method: 'POST', credentials: 'include' })
      if (!response.ok) throw new Error('restore failed')
      await fetchDocuments(selectedLibraryId)
      setVersionHistory(null)
      showNotif(`Ripristinata la versione ${version}: creata una nuova versione corrente`)
    } catch {
      showNotif('Impossibile ripristinare questa versione', 'error')
    }
  }

  const saveMember = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!selectedLibraryId || !memberUsername.trim()) return
    setSavingMember(true)
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/members`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: memberUsername.trim(), role: memberRole }),
      })
      if (!response.ok) throw new Error('member update failed')
      setMemberUsername('')
      await fetchMembers(selectedLibraryId)
      showNotif('Collaboratore aggiornato')
    } catch {
      showNotif('Impossibile aggiornare il collaboratore', 'error')
    } finally {
      setSavingMember(false)
    }
  }

  const deleteDocument = async (document: LibraryDocument) => {
    if (!selectedLibraryId) return
    if (!window.confirm(`Eliminare “${document.filename}” e tutte le sue versioni? L'operazione non è reversibile.`)) return
    setDeletingDocumentId(document.id)
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/documents/${document.id}`, { method: 'DELETE', credentials: 'include' })
      if (!response.ok) throw new Error('delete failed')
      if (searchScopeDoc?.id === document.id) setSearchScopeDoc(null)
      await fetchDocuments(selectedLibraryId)
      await fetchLibraries()
      showNotif(`Documento “${document.filename}” eliminato`)
    } catch {
      showNotif('Impossibile eliminare il documento', 'error')
    } finally {
      setDeletingDocumentId(null)
    }
  }

  const deleteLibrary = async () => {
    if (!selectedLibrary) return
    if (!window.confirm(`Eliminare la biblioteca “${selectedLibrary.name}” con tutti i suoi ${selectedLibrary.document_count} documenti? L'operazione non è reversibile.`)) return
    setDeletingLibrary(true)
    try {
      const response = await fetch(`/api/libraries/${selectedLibrary.id}`, { method: 'DELETE', credentials: 'include' })
      if (!response.ok) throw new Error('delete failed')
      const deletedName = selectedLibrary.name
      setSelectedLibraryId(null)
      await fetchLibraries()
      showNotif(`Biblioteca “${deletedName}” eliminata`)
    } catch {
      showNotif('Impossibile eliminare la biblioteca', 'error')
    } finally {
      setDeletingLibrary(false)
    }
  }

  const addSource = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!selectedLibraryId || !newSourcePath.trim()) return
    setAddingSource(true)
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/sources`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: newSourcePath.trim() }),
      })
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail ?? 'add source failed')
      }
      setNewSourcePath('')
      await fetchSources(selectedLibraryId)
      showNotif('Sorgente cartella registrata')
    } catch (error) {
      showNotif(error instanceof Error ? error.message : 'Impossibile registrare la sorgente', 'error')
    } finally {
      setAddingSource(false)
    }
  }

  const removeSource = async (source: ImportSource) => {
    if (!selectedLibraryId) return
    if (!window.confirm(`Rimuovere la sorgente “${source.path}”? I documenti già importati non vengono eliminati.`)) return
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/sources/${source.id}`, { method: 'DELETE', credentials: 'include' })
      if (!response.ok) throw new Error('remove source failed')
      await fetchSources(selectedLibraryId)
      showNotif('Sorgente rimossa')
    } catch {
      showNotif('Impossibile rimuovere la sorgente', 'error')
    }
  }

  const scanSource = async (source: ImportSource) => {
    if (!selectedLibraryId) return
    setScanningSourceId(source.id)
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/sources/${source.id}/scan`, { method: 'POST', credentials: 'include' })
      if (!response.ok) throw new Error('scan failed')
      const result: ScanResult = await response.json()
      await fetchSources(selectedLibraryId)
      await fetchDocuments(selectedLibraryId)
      await fetchLibraries()
      const parts = [`${result.imported.length} importati`]
      if (result.skipped_duplicates.length) parts.push(`${result.skipped_duplicates.length} duplicati saltati`)
      if (result.failed.length) parts.push(`${result.failed.length} falliti`)
      showNotif(parts.join(', '), result.failed.length ? 'error' : 'success')
    } catch {
      showNotif('Impossibile scansionare la sorgente', 'error')
    } finally {
      setScanningSourceId(null)
    }
  }

  const removeMember = async (username: string) => {
    if (!selectedLibraryId) return
    try {
      const response = await fetch(`/api/libraries/${selectedLibraryId}/members/${encodeURIComponent(username)}`, {  method: 'DELETE', credentials: 'include' })
      if (!response.ok) throw new Error('member removal failed')
      await fetchMembers(selectedLibraryId)
      showNotif('Collaboratore rimosso')
    } catch {
      showNotif('Impossibile rimuovere il collaboratore', 'error')
    }
  }

  return (
    <div className="flex h-full">
      <aside className={`w-80 border-r p-6 flex flex-col gap-4 bg-slate-950/20 ermes-glass ${t.documentsBg}`}>
        <div className="flex items-center justify-between gap-3">
          <CardTitle><Library className="w-4 h-4 text-blue-400" />Biblioteche</CardTitle>
          <button onClick={fetchLibraries} aria-label="Aggiorna biblioteche" className="text-slate-400 hover:text-blue-400 transition">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={createLibrary} className="flex gap-2">
          <input
            id="new-library-name"
            value={newLibraryName}
            onChange={event => setNewLibraryName(event.target.value)}
            placeholder="Nuova biblioteca"
            className={`min-w-0 flex-1 border rounded-lg px-3 py-2 text-sm outline-none ${t.sidebarInput}`}
          />
          <button type="submit" aria-label="Crea biblioteca" className="rounded-lg bg-blue-600 px-3 text-white hover:bg-blue-500 transition">
            <FolderPlus className="w-4 h-4" />
          </button>
        </form>

        {loadingLibraries ? (
          <div className="space-y-3">{[1, 2, 3].map(item => <div key={item} className={`h-16 rounded-xl ${t.skeleton}`} />)}</div>
        ) : libraries.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500">Crea la prima biblioteca per iniziare.</p>
        ) : (
          <div className="flex-1 space-y-2 overflow-y-auto">
            {libraries.map(library => (
              <button
                key={library.id}
                onClick={() => setSelectedLibraryId(library.id)}
                className={`w-full rounded-xl border p-3 text-left text-sm transition ${selectedLibraryId === library.id ? t.docSelected : t.card}`}
              >
                <span className="block truncate font-medium">{library.name}</span>
                <span className="mt-1 block text-xs text-slate-400">{library.document_count} documenti · {library.visibility === 'shared' ? 'Condivisa' : 'Privata'}</span>
              </button>
            ))}
          </div>
        )}
      </aside>

      <section className="flex flex-1 flex-col overflow-hidden">
        {selectedLibrary ? (
          <>
            <header className={`flex items-center justify-between gap-4 border-b bg-slate-950/15 px-7 py-5 ermes-glass ${t.documentsBg}`}>
              <div>
                <CardTitle><Library className="w-4 h-4 text-blue-400" />{selectedLibrary.name}</CardTitle>
                {selectedLibrary.description && <p className="mt-1 text-xs text-slate-400">{selectedLibrary.description}</p>}
              </div>
              <div className="flex items-center gap-3">
                {selectedLibrary.access_role && <span className={`rounded-full px-2 py-1 text-[11px] font-medium ${canEditLibrary ? 'bg-emerald-500/10 text-emerald-300' : 'bg-slate-500/10 text-slate-400'}`}>
                  {selectedLibrary.access_role === 'owner' ? 'Proprietario' : selectedLibrary.access_role === 'admin' ? 'Admin' : selectedLibrary.access_role === 'editor' ? 'Editor' : 'Sola lettura'}
                </span>}
                {canManageMembers && <button onClick={() => setShowMembers(current => !current)} className={`rounded-xl border px-3 py-2 text-xs font-medium transition ${showMembers ? 'border-blue-500/60 bg-blue-500/10 text-blue-300' : 'border-white/10 text-slate-300 hover:bg-white/5'}`}>
                  <span className="flex items-center gap-1.5"><Users className="h-3.5 w-3.5" />Collaboratori{members.length > 1 ? ` (${members.length - 1})` : ''}</span>
                </button>}
                {canManageLibrary && <button onClick={() => setShowSources(current => !current)} className={`rounded-xl border px-3 py-2 text-xs font-medium transition ${showSources ? 'border-blue-500/60 bg-blue-500/10 text-blue-300' : 'border-white/10 text-slate-300 hover:bg-white/5'}`}>
                  <span className="flex items-center gap-1.5"><FolderCog className="h-3.5 w-3.5" />Sorgenti{sources.length > 0 ? ` (${sources.length})` : ''}</span>
                </button>}
                {canManageLibrary && <button onClick={deleteLibrary} disabled={deletingLibrary} aria-label="Elimina biblioteca" title="Elimina biblioteca" className="rounded-xl border border-rose-500/30 px-3 py-2 text-xs font-medium text-rose-300 transition hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-40">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>}
                {canEditLibrary && <div className="flex items-center gap-2">
                  <select value={selectedLibrary.assistant_mode ?? 'evidence_only'} onChange={event => {
                    const mode = event.target.value as LibraryItem['assistant_mode']
                    changeAssistantMode(mode, mode === 'approved_provider' ? approvedProviders[0]?.name ?? '' : '')
                  }} className={`rounded-xl border px-3 py-2 text-xs outline-none ${t.sidebarInput}`} aria-label="Modalità assistente biblioteca">
                    <option value="evidence_only">Solo evidenze locali</option>
                    <option value="local_ollama">Ollama locale</option>
                    <option value="approved_openrouter">OpenRouter (cloud)</option>
                    <option value="approved_provider" disabled={!approvedProviders.length}>Provider approvato (cloud)</option>
                  </select>
                  {selectedLibrary.assistant_mode === 'approved_provider' && <select value={selectedLibrary.assistant_provider ?? ''} onChange={event => changeAssistantMode('approved_provider', event.target.value)} className={`max-w-44 rounded-xl border px-3 py-2 text-xs outline-none ${t.sidebarInput}`} aria-label="Provider cloud biblioteca">
                    {approvedProviders.map(provider => <option key={provider.name} value={provider.name}>{provider.name} · {provider.default_model}</option>)}
                  </select>}
                </div>}
                {canEditLibrary && <label className="cursor-pointer rounded-xl border border-white/10 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:bg-white/5">
                  <span className="flex items-center gap-1.5"><Upload className="w-3.5 h-3.5" />Carica documento</span>
                  <input type="file" className="hidden" accept=".pdf,.docx,.xlsx,.txt,.md" onChange={uploadDocument} />
                </label>}
              </div>
            </header>
            {showMembers && canManageMembers && (
              <section className={`border-b px-6 py-5 ${t.documentsBg}`} aria-label="Gestione collaboratori">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-200">Accesso alla biblioteca</h2>
                    <p className="mt-1 text-xs text-slate-400">I viewer consultano fonti e risposte; gli editor possono anche caricare e reindicizzare documenti.</p>
                  </div>
                  <form onSubmit={saveMember} className="flex flex-wrap items-center gap-2">
                    <input value={memberUsername} onChange={event => setMemberUsername(event.target.value)} placeholder="Nome utente" aria-label="Nome utente collaboratore" className={`w-36 rounded-lg border px-3 py-2 text-xs outline-none ${t.sidebarInput}`} />
                    <select value={memberRole} onChange={event => setMemberRole(event.target.value as 'viewer' | 'editor')} aria-label="Ruolo collaboratore" className={`rounded-lg border px-3 py-2 text-xs outline-none ${t.sidebarInput}`}>
                      <option value="viewer">Viewer</option>
                      <option value="editor">Editor</option>
                    </select>
                    <button type="submit" disabled={!memberUsername.trim() || savingMember} className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-blue-500 disabled:opacity-50"><span className="flex items-center gap-1"><UserPlus className="h-3.5 w-3.5" />{savingMember ? 'Salvataggio...' : 'Aggiungi'}</span></button>
                  </form>
                </div>
                <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                  {members.map(member => (
                    <article key={member.username} className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-2 ${t.card}`}>
                      <div className="min-w-0"><p className="truncate text-sm font-medium">{member.username}</p><p className="text-xs text-slate-400">{member.role === 'owner' ? 'Proprietario' : member.role === 'editor' ? 'Editor' : 'Viewer'}</p></div>
                      {member.role !== 'owner' && <button onClick={() => removeMember(member.username)} aria-label={`Rimuovi ${member.username}`} className="rounded-md p-1.5 text-slate-400 transition hover:bg-rose-500/10 hover:text-rose-300"><Trash2 className="h-3.5 w-3.5" /></button>}
                    </article>
                  ))}
                </div>
              </section>
            )}
            {showSources && canManageLibrary && (
              <section className={`border-b px-6 py-5 ${t.documentsBg}`} aria-label="Sorgenti cartella">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-200">Sorgenti cartella</h2>
                    <p className="mt-1 flex max-w-md items-start gap-1.5 text-xs text-slate-400">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
                      <span>Registra un percorso locale o di rete (UNC): i diritti sulla cartella sono quelli dell'account con cui gira Ermes, nessuna credenziale viene salvata. Solo il proprietario o un amministratore possono registrarne; il percorso non può trovarsi dentro la cartella dell'applicazione. Scansionare importa i file .txt/.pdf/.docx nuovi, saltando i duplicati per contenuto.</span>
                    </p>
                  </div>
                  <form onSubmit={addSource} className="flex flex-wrap items-center gap-2">
                    <input value={newSourcePath} onChange={event => setNewSourcePath(event.target.value)} placeholder={'\\\\server\\condivisa oppure C:\\percorso'} aria-label="Percorso della cartella" className={`w-56 rounded-lg border px-3 py-2 text-xs outline-none ${t.sidebarInput}`} />
                    <button type="submit" disabled={!newSourcePath.trim() || addingSource} className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-blue-500 disabled:opacity-50"><span className="flex items-center gap-1"><FolderPlus className="h-3.5 w-3.5" />{addingSource ? 'Registro...' : 'Registra'}</span></button>
                  </form>
                </div>
                {sources.length === 0 ? (
                  <p className="mt-4 text-xs text-slate-500">Nessuna sorgente registrata.</p>
                ) : (
                  <div className="mt-4 space-y-2">
                    {sources.map(source => (
                      <article key={source.id} className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-2 ${t.card}`}>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{source.path}</p>
                          <p className="text-xs text-slate-400">{source.last_scan_at ? `Ultima scansione: ${new Date(source.last_scan_at).toLocaleString()}` : 'Mai scansionata'}</p>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <button onClick={() => scanSource(source)} disabled={scanningSourceId === source.id} className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-xs text-slate-300 transition hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40">
                            <RefreshCw className={`h-3.5 w-3.5 ${scanningSourceId === source.id ? 'animate-spin' : ''}`} />{scanningSourceId === source.id ? 'Scansiono...' : 'Scansiona'}
                          </button>
                          <button onClick={() => removeSource(source)} aria-label={`Rimuovi sorgente ${source.path}`} className="rounded-md p-1.5 text-slate-400 transition hover:bg-rose-500/10 hover:text-rose-300"><Trash2 className="h-3.5 w-3.5" /></button>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            )}
            <div className="flex-1 overflow-y-auto p-7">
              <form onSubmit={searchDocuments} className="mb-6 flex max-w-2xl gap-2">
                <input
                  value={searchQuery}
                  onChange={event => {
                    setSearchQuery(event.target.value)
                    if (!event.target.value) {
                      setSearchResults(null)
                      setRetrievalProfile(null)
                    }
                  }}
                  placeholder="Cerca nei documenti della biblioteca"
                  className={`min-w-0 flex-1 border rounded-lg px-3 py-2 text-sm outline-none ${t.sidebarInput}`}
                />
                <button type="submit" disabled={searchQuery.trim().length < 2 || searching} className="rounded-lg bg-blue-600 px-4 text-sm text-white transition hover:bg-blue-500 disabled:opacity-50">
                  <span className="flex items-center gap-1.5"><Search className="h-3.5 w-3.5" />{searching ? 'Ricerca...' : 'Cerca'}</span>
                </button>
              </form>
              {searchScopeDoc && (
                <div className="mb-4 flex max-w-2xl items-center justify-between gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-xs text-blue-200">
                  <span>Ricerca limitata a: <strong>{searchScopeDoc.filename}</strong></span>
                  <button type="button" onClick={() => { setSearchScopeDoc(null); setSearchResults(null); setRetrievalProfile(null) }} className="rounded-md border border-blue-400/40 px-2 py-0.5 font-semibold transition hover:bg-blue-500/20" aria-label="Torna alla ricerca sull'intera biblioteca">Tutta la biblioteca ✕</button>
                </div>
              )}
              {searchResults !== null && (
                <div className="mb-6 space-y-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-400">
                    <span>{searchResults.length} risultati</span>
                    {retrievalProfile && <span className={`rounded-full px-2 py-0.5 normal-case tracking-normal ${retrievalProfile.semantic_used ? 'bg-violet-500/10 text-violet-300' : 'bg-slate-500/10 text-slate-400'}`}>
                      {retrievalProfile.semantic_used ? `Ricerca ibrida locale · ${retrievalProfile.semantic_indexed_chunks} passaggi vettoriali` : 'Ricerca per parole locali'}
                    </span>}
                  </div>
                  {searchResults.length === 0 ? <p className="text-sm text-slate-500">Nessun passaggio trovato.</p> : searchResults.map(result => (
                    <article key={`${result.document_id}-${result.citation.locator}`} className={`rounded-xl border p-4 ${t.card}`}>
                      <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">{result.filename}</h3><span className="shrink-0 text-xs text-blue-400">v{result.citation.version} · {result.citation.locator}</span></div>
                      {result.excerpt && <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-400">{result.excerpt}</p>}
                    </article>
                  ))}
                </div>
              )}
              {loadingDocuments ? (
                <div className="space-y-3">{[1, 2, 3].map(item => <div key={item} className={`h-16 rounded-xl ${t.skeleton}`} />)}</div>
              ) : documents.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-slate-500">
                  <FileText className="h-12 w-12 opacity-20" />
                  <h2 className="text-lg font-semibold text-slate-300">Pronta per il primo documento</h2>
                  <p className="max-w-md text-sm leading-6">Carica un PDF, DOCX, TXT o Markdown. Ermes lo indicizza e manterrà il collegamento all'originale e alla sua versione.</p>
                  {canEditLibrary ? <label className="mt-2 cursor-pointer rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-500">
                    Carica il primo documento
                    <input type="file" className="hidden" accept=".pdf,.docx,.xlsx,.txt,.md" onChange={uploadDocument} />
                  </label> : <p className="text-xs text-slate-400">Chiedi a un editor di caricare un documento.</p>}
                  <p className="text-xs text-slate-500">Per impostazione predefinita, i documenti restano locali.</p>
                </div>
              ) : (
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {documents.map(document => (
                    <article key={document.id} className={`rounded-xl border p-4 ${t.card}`}>
                      <div className="flex items-start gap-3">
                        <FileText className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" />
                        <div className="min-w-0">
                          <h3 className="truncate text-sm font-semibold">{document.filename}</h3>
                          <p className="mt-1 text-xs text-slate-400">v{document.version} · {formatSize(document.size_bytes)}</p>
                          {(() => {
                            const status = documentStatus(document.status)
                            return <span className={`mt-3 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${status.className}`}><status.Icon className={`h-3 w-3 ${document.status === 'processing' ? 'animate-spin' : ''}`} />{status.label}</span>
                          })()}
                          <div className="mt-3 flex flex-wrap gap-3"><button onClick={() => { setSearchScopeDoc(current => current?.id === document.id ? null : document); setSearchQuery(''); setSearchResults(null); setRetrievalProfile(null) }} className={`flex items-center gap-1 text-xs transition hover:text-blue-400 ${searchScopeDoc?.id === document.id ? 'text-blue-300' : 'text-slate-400'}`}><Search className="h-3 w-3" />{searchScopeDoc?.id === document.id ? 'Scope attivo' : 'Cerca qui'}</button><button onClick={() => showSummary(document)} disabled={summarizing} className="flex items-center gap-1 text-xs text-slate-400 transition hover:text-blue-400 disabled:cursor-not-allowed disabled:opacity-40"><FileText className="h-3 w-3" />{summarizing ? 'Riassumo…' : 'Riassumi'}</button><button onClick={() => downloadDocument(document)} className="flex items-center gap-1 text-xs text-slate-400 transition hover:text-blue-400"><Download className="h-3 w-3" />Apri</button>{canManageMembers && <button onClick={() => openAclPanel(document)} className="flex items-center gap-1 text-xs text-slate-400 transition hover:text-blue-400"><ShieldCheck className="h-3 w-3" />Accessi</button>}{canEditLibrary && <button disabled={document.status === 'queued' || document.status === 'processing'} onClick={() => reindexDocument(document)} className="flex items-center gap-1 text-xs text-slate-400 transition hover:text-blue-400 disabled:cursor-not-allowed disabled:opacity-40"><RefreshCw className="h-3 w-3" />Reindicizza</button>}<button onClick={() => showVersions(document)} className="text-xs text-slate-400 transition hover:text-blue-400">Versioni</button>{canEditLibrary && <button onClick={() => deleteDocument(document)} disabled={deletingDocumentId === document.id} aria-label={`Elimina ${document.filename}`} className="flex items-center gap-1 text-xs text-rose-400/80 transition hover:text-rose-300 disabled:cursor-not-allowed disabled:opacity-40"><Trash2 className="h-3 w-3" />{deletingDocumentId === document.id ? 'Elimino…' : 'Elimina'}</button>}</div>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-slate-500">
            <Library className="h-16 w-16 opacity-20" />
            <div className="max-w-md text-center">
              <p className="text-lg font-semibold text-slate-300">Inizia con una biblioteca</p>
              <p className="mt-2 text-sm leading-6">Crea uno spazio separato per procedure, manuali e documenti del team. Potrai scegliere in seguito se tenerlo privato o condividerlo.</p>
              <ol className="mt-5 space-y-2 text-left text-sm text-slate-400">
                <li><strong className="text-blue-300">1.</strong> Dai un nome alla biblioteca.</li>
                <li><strong className="text-blue-300">2.</strong> Carica il primo documento.</li>
                <li><strong className="text-blue-300">3.</strong> Consulta le risposte con le relative fonti.</li>
              </ol>
              <button onClick={() => document.getElementById('new-library-name')?.focus()} className="mt-6 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500">Crea la prima biblioteca</button>
            </div>
          </div>
        )}
      </section>
      {aclPanel && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/70 p-6">
          <section className={`w-full max-w-lg rounded-2xl border p-6 shadow-2xl ${t.card}`} aria-label="Accessi documento">
            <div className="flex items-start justify-between gap-4"><div><h2 className="font-semibold">Chi può vedere questo documento</h2><p className="mt-1 text-sm text-slate-400">{aclPanel.document.filename}</p></div><button onClick={() => setAclPanel(null)} className="text-slate-400 hover:text-white">Chiudi</button></div>
            <p className="mt-4 rounded-lg border border-white/10 bg-white/[0.02] p-3 text-xs leading-5 text-slate-400">Senza restrizioni il documento è visibile a chi accede alla biblioteca. Con una lista, solo l'amministratore, il proprietario e gli utenti elencati possono vederlo — anche nelle risposte dell'assistente.</p>
            {aclPanel.usernames.length > 0 ? (
              <ul className="mt-4 space-y-2">
                {aclPanel.usernames.map(username => (
                  <li key={username} className="flex items-center justify-between rounded-lg border border-white/10 px-3 py-2">
                    <span className="flex items-center gap-2 text-sm"><ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />{username}</span>
                    <button disabled={savingAcl} onClick={() => removeAclUser(username)} className="text-xs text-rose-400 transition hover:text-rose-300 disabled:opacity-40">Rimuovi</button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 text-sm text-slate-500">Nessuna restrizione: visibile a tutta la biblioteca.</p>
            )}
            <form onSubmit={addAclUser} className="mt-5 flex flex-wrap items-center gap-2">
              <input value={aclUsername} onChange={event => setAclUsername(event.target.value)} placeholder="nome utente da autorizzare" className={`min-w-0 flex-1 rounded-xl border px-3 py-2 text-sm outline-none ${t.sidebarInput}`} aria-label="Utente da autorizzare" />
              <button type="submit" disabled={savingAcl || !aclUsername.trim()} className="flex items-center gap-1.5 rounded-xl bg-blue-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40">
                <UserPlus className="h-3.5 w-3.5" />{savingAcl ? 'Salvo…' : 'Autorizza'}
              </button>
            </form>
          </section>
        </div>
      )}
      {summaryPanel && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/70 p-6">
          <section className={`w-full max-w-lg rounded-2xl border p-6 shadow-2xl ${t.card}`} aria-label="Riassunto documento">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="font-semibold">Riassunto</h2>
                <p className="mt-1 text-sm text-slate-400">{summaryPanel.document.filename}</p>
              </div>
              <button onClick={() => setSummaryPanel(null)} className="text-slate-400 hover:text-white">Chiudi</button>
            </div>
            {summaryPanel.status === 'answered' ? (
              <>
                <div className="mt-4 space-y-2 rounded-lg border border-white/10 bg-white/[0.02] p-4 text-sm leading-6 whitespace-pre-wrap">{summaryPanel.summary}</div>
                <p className="mt-3 text-xs text-slate-500">
                  Generato {summaryPanel.mode === 'local_llm' ? 'con il modello locale' : 'in modo estrattivo'} solo dai passaggi indicizzati del documento.
                  {summaryPanel.reason ? ` ${summaryPanel.reason}` : ''}
                </p>
              </>
            ) : (
              <p className="mt-4 rounded-lg border border-white/10 bg-white/[0.02] p-4 text-sm text-slate-400">
                Nessun riassunto disponibile: {summaryPanel.reason || 'il documento non ha testo indicizzato utilizzabile.'}
              </p>
            )}
          </section>
        </div>
      )}
      {versionHistory && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/70 p-6">
          <section className={`w-full max-w-lg rounded-2xl border p-6 shadow-2xl ${t.card}`}>
            <div className="flex items-start justify-between gap-4"><div><h2 className="font-semibold">Storico versioni</h2><p className="mt-1 text-sm text-slate-400">{versionHistory.document.filename}</p></div><button onClick={() => setVersionHistory(null)} className="text-slate-400 hover:text-white">Chiudi</button></div>
            <div className="mt-5 space-y-2">{versionHistory.items.map(item => <article key={item.version} className="flex items-center justify-between rounded-lg border border-white/10 p-3"><div><p className="text-sm font-medium">Versione {item.version}{item.version === versionHistory.document.version ? ' · corrente' : ''}</p><p className="text-xs text-slate-400">{formatSize(item.size_bytes)} · {new Date(item.created_at).toLocaleString()}</p></div>{item.version !== versionHistory.document.version && <button onClick={() => restoreVersion(item.version)} className="rounded-md border border-blue-500/40 px-2 py-1 text-xs text-blue-300 hover:bg-blue-500/10">Ripristina</button>}</article>)}</div>
          </section>
        </div>
      )}
    </div>
  )
}
