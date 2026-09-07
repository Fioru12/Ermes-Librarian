import { useState } from 'react'
import { Sparkles, Check, X, Folder } from 'lucide-react'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Card, CardTitle } from '../ui/Card'

interface OnboardingWizardProps {
  onLibraryCreated: (libraryId: string) => void
  showNotif: (msg: string, type?: 'success' | 'error') => void
}

export default function OnboardingWizard({ onLibraryCreated, showNotif }: OnboardingWizardProps) {
  const [step, setStep] = useState<'welcome' | 'library' | 'connector' | 'complete'>('welcome')
  const [libraryName, setLibraryName] = useState('')
  const [libraryDescription, setLibraryDescription] = useState('')
  const [isCreating, setIsCreating] = useState(false)

  const handleCreateLibrary = async () => {
    if (!libraryName.trim()) { showNotif('Inserisci un nome', 'error'); return }
    setIsCreating(true)
    try {
      const res = await fetch('/api/libraries', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ name: libraryName, description: libraryDescription }) })
      if (res.ok) {
        const data = await res.json()
        onLibraryCreated(data.id)
        showNotif(`Biblioteca "${libraryName}" creata!`, 'success')
        setStep('connector')
      } else { showNotif('Errore creazione biblioteca', 'error') }
    } catch { showNotif('Errore di rete', 'error') }
    finally { setIsCreating(false) }
  }

  const handleSkip = () => setStep('complete')
  const renderStep = () => {
    switch (step) {
      case 'welcome': return (<div className='text-center space-y-6'><div className='w-20 h-20 mx-auto bg-blue-600 rounded-2xl flex items-center'><Sparkles className='w-10 h-10 text-white' /></div><h2 className='text-2xl font-bold'>Benvenuto in Ermes Knowledge</h2><Button onClick={() => setStep('library')}>Inizia ora</Button></div>)
      case 'library': return (<div className='space-y-4'><h2>Crea biblioteca</h2><Input label='Nome' value={libraryName} onChange={e => setLibraryName(e.target.value)} /><Input label='Descrizione' value={libraryDescription} onChange={e => setLibraryDescription(e.target.value)} /><Button onClick={handleCreateLibrary} disabled={isCreating}>{isCreating ? 'Creazione...' : 'Crea'}</Button></div>)
      case 'connector': return (<div><h2>Aggiungi un connettore</h2><Card><CardTitle><Folder /> Cartella Locale</CardTitle></Card><div className='flex gap-3'><Button onClick={() => setStep('complete')}>Continua</Button><Button variant='ghost' onClick={handleSkip}>Salta</Button></div></div>)
      case 'complete': return (<div className='text-center'><Check className='w-10 h-10 mx-auto text-emerald-500' /><h2>Tutto pronto!</h2><Button onClick={() => window.dispatchEvent(new CustomEvent('openChat'))}>Vai alla chat</Button></div>)
      default: return null
    }
  }

  return (
    <div className='fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4'>
      <div className='bg-slate-950 border border-white/10 rounded-2xl w-full max-w-lg max-h-[90vh] flex flex-col'>
        <div className='p-4 border-b'>
          <div className='flex justify-between'><h3>Configurazione iniziale</h3><button onClick={() => window.dispatchEvent(new CustomEvent('closeOnboarding'))} className='text-slate-500 hover:text-slate-300'><X className='w-4 h-4' /></button></div>
        </div>
        <div className='p-4 overflow-y-auto flex-1'>{renderStep()}</div>
      </div>
    </div>
  )
}
