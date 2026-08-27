import { useState, useEffect } from 'react'
import { Settings, Cpu, Zap, RefreshCw } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { Card, CardTitle, Input, Select, Button } from '../ui'
import type { ProviderConfig } from '../../types'

interface ProvidersTabProps {
  showNotif: (msg: string, type?: 'success' | 'error') => void
}

const typeDefaults: Record<string, string> = {
  openai: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  google: 'https://generativelanguage.googleapis.com',
  ollama: 'http://127.0.0.1:11434',
}

export default function ProvidersTab({ showNotif }: ProvidersTabProps) {
  const { t } = useTheme()
  const [providers, setProviders] = useState<ProviderConfig[]>([])
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState<ProviderConfig>({
    name: '', type: 'openai', api_key: '', base_url: 'https://api.openai.com/v1',
    default_model: '', models: [], enabled: true,
  })
  const [modelsInput, setModelsInput] = useState('')
  const [detecting, setDetecting] = useState(false)
  const [fetchingModels, setFetchingModels] = useState(false)

  const fetchProviders = async () => {
    try {
      const res = await fetch('/api/providers', { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        setProviders(data.providers || [])
      }
    } catch { /* ignore */ }
  }

  useEffect(() => { fetchProviders() }, [])

  const resetForm = () => {
    setForm({ name: '', type: 'openai', api_key: '', base_url: 'https://api.openai.com/v1', default_model: '', models: [], enabled: true })
    setModelsInput('')
    setEditing(null)
  }

  const detectProvider = async () => {
    if (!form.api_key && form.type !== 'ollama') { showNotif('Inserisci una API key', 'error'); return }
    setDetecting(true)
    try {
      const key = form.type === 'ollama' ? 'ollama_local' : form.api_key
      const res = await fetch('/api/providers/detect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ api_key: key }),
      })
      if (!res.ok) { showNotif(await res.text(), 'error'); return }
      const data = await res.json()
      setForm(prev => ({
        ...prev,
        type: data.type || prev.type,
        base_url: data.base_url || prev.base_url,
        default_model: data.default_model || prev.default_model,
        models: data.models || [],
      }))
      if (data.models) setModelsInput(data.models.join('\n'))
      showNotif(`Riconosciuto: ${data.type}${data.match !== 'unknown' ? ` (${data.match}...)` : ''}`, 'success')
    } catch (e: any) { showNotif(e.message, 'error') }
    finally { setDetecting(false) }
  }

  const fetchModels = async () => {
    if (!form.base_url) { showNotif('Inserisci Base URL', 'error'); return }
    setFetchingModels(true)
    try {
      const res = await fetch('/api/providers/fetch-models', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: form.type, base_url: form.base_url, api_key: form.api_key }),
      })
      if (!res.ok) { showNotif(await res.text(), 'error'); return }
      const data = await res.json()
      if (data.models?.length) {
        setForm(prev => ({ ...prev, models: data.models }))
        setModelsInput(data.models.join('\n'))
        showNotif(`${data.count} modelli trovati`, 'success')
      } else {
        showNotif('Nessun modello trovato', 'error')
      }
    } catch (e: any) { showNotif(e.message, 'error') }
    finally { setFetchingModels(false) }
  }

  const saveProvider = async () => {
    if (!form.name) { showNotif('Inserisci un nome per il provider', 'error'); return }
    try {
      const res = await fetch('/api/providers', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form),
      })
      if (res.ok) {
        showNotif(`Provider "${form.name}" aggiunto`)
        resetForm()
        fetchProviders()
      } else {
        showNotif(await res.text(), 'error')
      }
    } catch (e: any) { showNotif(e.message, 'error') }
  }

  const testProvider = async (p: ProviderConfig) => {
    const res = await fetch('/api/providers/test', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(p),
    })
    if (res.ok) {
      const data = await res.json()
      showNotif(data.ok ? `${p.name}: Connessione OK ✓` : `${p.name}: ${data.message}`, data.ok ? 'success' : 'error')
    }
  }

  const setActive = async (name: string) => {
    await fetch('/api/providers/active', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
    })
    showNotif(`Provider attivo: ${name}`)
    fetchProviders()
  }

  const removeProvider = async (name: string) => {
    if (!confirm(`Rimuovere provider "${name}"?`)) return
    const res = await fetch(`/api/providers/${name}`, {  method: 'DELETE', credentials: 'include' })
    if (res.ok) {
      showNotif(`Provider "${name}" rimosso`)
      fetchProviders()
    }
  }

  const editProvider = (p: ProviderConfig) => {
    setEditing(p.name)
    setForm({ ...p, api_key: '' })
    setModelsInput((p.models || []).join('\n'))
  }

  const handleTypeChange = (type: string) => {
    setForm({ ...form, type, base_url: typeDefaults[type] || '' })
  }

  return (
    <div className="p-8 h-full overflow-y-auto space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Add/Edit Form */}
        <Card>
          <CardTitle><Settings className="w-4 h-4 text-purple-400" />{editing ? 'Modifica Provider' : 'Aggiungi Provider'}</CardTitle>
          <div className="space-y-3 mt-4">
            <Select label="Tipo" value={form.type} onChange={e => handleTypeChange(e.target.value)}>
              <option value="openai">OpenAI / OpenRouter / Groq</option>
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="google">Google (Gemini)</option>
              <option value="ollama">Ollama (Locale)</option>
            </Select>
            <Input label="Nome" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="es. openai-gpt4" />
            {form.type !== 'ollama' && (
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <Input label="API Key" type="password" value={form.api_key} onChange={e => setForm({ ...form, api_key: e.target.value })} placeholder="sk-..." />
                </div>
                <button onClick={detectProvider} disabled={detecting || (!form.api_key && form.type !== 'ollama')}
                  className="h-10 px-3 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer shrink-0">
                  {detecting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                  Riconosci
                </button>
              </div>
            )}
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <Input label="Base URL" value={form.base_url} onChange={e => setForm({ ...form, base_url: e.target.value })} />
              </div>
              {form.type !== 'ollama' && (
                <button onClick={fetchModels} disabled={fetchingModels || !form.base_url}
                  className="h-10 px-3 rounded-lg border border-white/10 hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed text-slate-300 text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer shrink-0">
                  {fetchingModels ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                  Modelli
                </button>
              )}
            </div>
            <Input label="Modello predefinito" value={form.default_model} onChange={e => setForm({ ...form, default_model: e.target.value })} placeholder="es. gpt-4o" />
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-400 block">Modelli (uno per riga)</label>
              <textarea value={modelsInput} onChange={e => {
                setModelsInput(e.target.value)
                setForm({ ...form, models: e.target.value.split('\n').filter(s => s.trim()) })
              }} rows={3} placeholder="gpt-4o&#10;gpt-4.1" className={`w-full border rounded-lg px-3 py-2 text-sm outline-none transition ${t.sidebarInput}`} />
            </div>
            <div className="flex gap-2 pt-2">
              <Button onClick={saveProvider}>{editing ? 'Aggiorna' : 'Aggiungi'}</Button>
              <Button variant="secondary" onClick={() => testProvider(form)}>Test Connessione</Button>
              {editing && <Button variant="danger" onClick={resetForm}>Annulla</Button>}
            </div>
          </div>
        </Card>

        {/* Provider List */}
        <Card>
          <CardTitle><Cpu className="w-4 h-4 text-emerald-400" />Provider Configurati</CardTitle>
          {providers.length === 0 ? (
            <div className="text-sm text-slate-500 text-center py-8">Nessun provider configurato.</div>
          ) : (
            <div className="space-y-3 mt-4">
              {providers.map(p => (
                <div key={p.name} className={`border rounded-xl p-4 transition ${t.card}`}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${p.enabled ? 'bg-emerald-500' : 'bg-gray-500'}`} />
                      <span className="font-bold text-sm">{p.name}</span>
                      {p.is_active && <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">ATTIVO</span>}
                    </div>
                    <span className="text-[10px] uppercase tracking-wider text-slate-500 bg-white/5 px-2 py-0.5 rounded-full">{p.type}</span>
                  </div>
                  <div className="text-xs text-slate-400 space-y-1">
                    {p.base_url && <div>URL: <span className="text-slate-300">{p.base_url}</span></div>}
                    {p.default_model && <div>Modello: <span className="text-slate-300">{p.default_model}</span></div>}
                    {p.models && p.models.length > 0 && <div>Modelli: <span className="text-slate-300">{p.models.slice(0, 3).join(', ')}{p.models.length > 3 ? ` +${p.models.length - 3}` : ''}</span></div>}
                  </div>
                  <div className="flex items-center gap-2 mt-3 pt-3 border-t border-white/5">
                    {!p.is_active && <button onClick={() => setActive(p.name)} className="text-xs text-blue-400 hover:text-blue-300 font-semibold transition cursor-pointer">Imposta Attivo</button>}
                    <button onClick={() => testProvider(p)} className="text-xs text-slate-400 hover:text-slate-300 font-semibold transition cursor-pointer">Test</button>
                    <button onClick={() => editProvider(p)} className="text-xs text-slate-400 hover:text-slate-300 font-semibold transition cursor-pointer">Modifica</button>
                    <button onClick={() => removeProvider(p.name)} className="text-xs text-rose-400 hover:text-rose-300 font-semibold transition cursor-pointer">Rimuovi</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
