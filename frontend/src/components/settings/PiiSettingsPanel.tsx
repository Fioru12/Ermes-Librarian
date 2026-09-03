import { useState, useEffect } from 'react'
import { ShieldAlert, Plus, Trash2, TestTube, CheckCircle, RefreshCw, Lock } from 'lucide-react'
import { Card, CardTitle, Button, Input } from '../ui'

interface PiiSettingsPanelProps {
  showNotif: (msg: string, type?: 'success' | 'error') => void
  isAdmin?: boolean
}

interface StandardPatternMeta {
  id: string
  label: string
  replacement: string
  enabled: boolean
}

interface CustomRule {
  id: string
  name: string
  pattern: string
  replacement: string
  enabled: boolean
}

export default function PiiSettingsPanel({ showNotif, isAdmin = false }: PiiSettingsPanelProps) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [standardMeta, setStandardMeta] = useState<StandardPatternMeta[]>([])
  const [enabledPatterns, setEnabledPatterns] = useState<Record<string, boolean>>({})
  const [customRules, setCustomRules] = useState<CustomRule[]>([])

  // State per aggiunta nuova regola custom
  const [newRuleName, setNewRuleName] = useState('')
  const [newRulePattern, setNewRulePattern] = useState('')
  const [newRuleReplacement, setNewRuleReplacement] = useState('[DATO_RISERVATO]')

  // State per tester in tempo reale
  const [testText, setTestText] = useState('Gentile cliente, il mio codice fiscale è RSSMRA80A01H501U e l\'IBAN è IT60X0542811101000000123456. Contattatemi a mario.rossi@email.it o al 3391234567.')
  const [testResult, setTestResult] = useState<{ masked: string; detected: Array<{ type: string; label: string; value: string }> } | null>(null)
  const [testing, setTesting] = useState(false)

  const fetchConfig = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/pii/config')
      if (!res.ok) throw new Error('Errore nel caricamento delle regole PII')
      const data = await res.json()
      setStandardMeta(data.standard_patterns_meta || [])
      setEnabledPatterns(data.enabled_patterns || {})
      setCustomRules(data.custom_rules || [])
    } catch (err: any) {
      showNotif(err.message || 'Impossibile caricare configurazione DLP', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchConfig()
  }, [])

  const handleTogglePattern = (id: string) => {
    if (!isAdmin) return
    setEnabledPatterns(prev => ({
      ...prev,
      [id]: !prev[id],
    }))
  }

  const handleAddCustomRule = () => {
    if (!newRuleName.trim() || !newRulePattern.trim() || !newRuleReplacement.trim()) {
      showNotif('Compila tutti i campi della regola personalizzata', 'error')
      return
    }

    // Valida sintassi regex client-side
    try {
      new RegExp(newRulePattern)
    } catch (e) {
      showNotif('Sintassi Regex non valida', 'error')
      return
    }

    const newRule: CustomRule = {
      id: `custom_${Date.now()}`,
      name: newRuleName.trim(),
      pattern: newRulePattern.trim(),
      replacement: newRuleReplacement.trim(),
      enabled: true,
    }

    setCustomRules(prev => [...prev, newRule])
    setNewRuleName('')
    setNewRulePattern('')
    setNewRuleReplacement('[DATO_RISERVATO]')
    showNotif('Regola personalizzata aggiunta alla bozza', 'success')
  }

  const handleDeleteCustomRule = (id: string) => {
    setCustomRules(prev => prev.filter(r => r.id !== id))
  }

  const handleSaveConfig = async () => {
    if (!isAdmin) return
    setSaving(true)
    try {
      const res = await fetch('/api/pii/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled_patterns: enabledPatterns,
          custom_rules: customRules,
        }),
      })

      if (!res.ok) throw new Error('Errore durante il salvataggio della configurazione PII')
      showNotif('Regole PII / DLP salvate con successo!', 'success')
    } catch (err: any) {
      showNotif(err.message || 'Errore salvataggio PII', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleRunTest = async () => {
    if (!testText.trim()) return
    setTesting(true)
    try {
      const res = await fetch('/api/pii/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: testText }),
      })
      if (!res.ok) throw new Error('Errore durante il test PII')
      const data = await res.json()
      setTestResult({
        masked: data.masked,
        detected: data.detected || [],
      })
    } catch (err: any) {
      showNotif(err.message || 'Test fallito', 'error')
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return (
      <Card>
        <div className="flex items-center justify-center p-8 text-slate-400 gap-2">
          <RefreshCw className="w-5 h-5 animate-spin" /> Caricamento regole PII/DLP...
        </div>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {/* 1. Pattern PII Standard */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <CardTitle>
            <ShieldAlert className="w-5 h-5 text-amber-400" /> Protezione Dati Sensibili PII & DLP
          </CardTitle>
          {isAdmin && (
            <Button variant="primary" onClick={handleSaveConfig} disabled={saving}>
              {saving ? 'Salvataggio...' : 'Salva Regole PII'}
            </Button>
          )}
        </div>
        <p className="text-sm text-slate-400 mb-6">
          Seleziona i tipi di dati riservati che il sistema deve oscurare automaticamente prima dell'invio ai modelli AI e nelle risposte finali.
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          {standardMeta.map(item => (
            <div
              key={item.id}
              onClick={() => handleTogglePattern(item.id)}
              className={`flex items-center justify-between p-4 rounded-xl border transition-all cursor-pointer ${
                enabledPatterns[item.id] !== false
                  ? 'bg-amber-500/10 border-amber-500/30 text-amber-200'
                  : 'bg-white/[0.02] border-white/10 text-slate-400 hover:border-slate-600'
              }`}
            >
              <div>
                <span className="font-semibold text-sm block">{item.label}</span>
                <span className="text-xs opacity-75 font-mono">Maschera: {item.replacement}</span>
              </div>
              <input
                type="checkbox"
                checked={enabledPatterns[item.id] !== false}
                onChange={() => {}}
                disabled={!isAdmin}
                className="w-4 h-4 accent-amber-500 rounded cursor-pointer"
              />
            </div>
          ))}
        </div>
      </Card>

      {/* 2. Regole Custom Regex */}
      <Card>
        <CardTitle>
          <Lock className="w-4 h-4 text-blue-400" /> Regole Regex Personalizzate
        </CardTitle>
        <p className="text-sm text-slate-400 mt-1 mb-4">
          Definisci espressioni regolari aziendali su misura per mascherare codici interni, matricole dipendenti o numeri d'ordine.
        </p>

        {isAdmin && (
          <div className="grid gap-3 sm:grid-cols-3 mb-6 p-4 rounded-xl border border-white/10 bg-white/[0.02]">
            <Input
              placeholder="Nome Regola (es. Badge Dipendente)"
              value={newRuleName}
              onChange={e => setNewRuleName(e.target.value)}
            />
            <Input
              placeholder="Regex (es. \bEMP-\d{6}\b)"
              value={newRulePattern}
              onChange={e => setNewRulePattern(e.target.value)}
            />
            <div className="flex gap-2">
              <Input
                placeholder="Segnaposto (es. [BADGE])"
                value={newRuleReplacement}
                onChange={e => setNewRuleReplacement(e.target.value)}
              />
              <Button variant="secondary" onClick={handleAddCustomRule} className="shrink-0">
                <Plus className="w-4 h-4" /> Aggiungi
              </Button>
            </div>
          </div>
        )}

        {customRules.length === 0 ? (
          <div className="text-center py-6 border border-dashed border-white/10 rounded-xl text-slate-500 text-sm">
            Nessuna regola Regex personalizzata definita.
          </div>
        ) : (
          <div className="space-y-2">
            {customRules.map(rule => (
              <div
                key={rule.id}
                className="flex items-center justify-between p-3 rounded-lg border border-white/10 bg-white/[0.02] text-sm"
              >
                <div>
                  <span className="font-semibold text-slate-200">{rule.name}</span>
                  <span className="ml-3 font-mono text-xs text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded">
                    {rule.pattern}
                  </span>
                  <span className="ml-2 font-mono text-xs text-amber-400">→ {rule.replacement}</span>
                </div>
                {isAdmin && (
                  <Button variant="danger" className="px-2 py-1 text-xs" onClick={() => handleDeleteCustomRule(rule.id)}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* 3. Real-Time Tester Panel */}
      <Card>
        <CardTitle>
          <TestTube className="w-4 h-4 text-emerald-400" /> Tester Mascheramento PII in Tempo Reale
        </CardTitle>
        <p className="text-sm text-slate-400 mt-1 mb-4">
          Incolla un testo di prova per verificare istantaneamente come le regole attive oscurano i dati riservati.
        </p>

        <div className="space-y-4">
          <textarea
            className="w-full h-24 p-3 text-sm bg-slate-900/60 border border-white/10 rounded-xl focus:border-emerald-500 focus:outline-none text-slate-200 placeholder-slate-500 font-mono"
            value={testText}
            onChange={e => setTestText(e.target.value)}
            placeholder="Inserisci qui il testo da collaudare..."
          />

          <Button variant="secondary" onClick={handleRunTest} disabled={testing}>
            {testing ? 'Verifica in corso...' : 'Esegui Collaudo Live'}
          </Button>

          {testResult && (
            <div className="mt-4 p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 space-y-3">
              <div className="flex items-center gap-2 text-emerald-300 font-semibold text-sm">
                <CheckCircle className="w-4 h-4" /> Risultato Mascheramento ({testResult.detected.length} dati rilevati)
              </div>
              <div className="p-3 bg-slate-950/80 border border-white/10 rounded-lg text-xs font-mono text-slate-200 whitespace-pre-wrap leading-relaxed">
                {testResult.masked}
              </div>
              {testResult.detected.length > 0 && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {testResult.detected.map((d, idx) => (
                    <span key={idx} className="text-xs bg-amber-500/20 text-amber-300 border border-amber-500/40 px-2 py-1 rounded-md font-mono">
                      {d.label}: <strong className="text-white">{d.value}</strong>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
