import { useCallback, useEffect, useState } from 'react'
import { NotebookPen, Trash2 } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { Button } from '../ui'

export interface NoteSource {
  document_id?: string
  filename?: string
  version?: number
  locator?: string
  excerpt?: string
}

export interface Note {
  id: string
  title: string
  body: string
  sources: NoteSource[]
  updated_at: string
}

export interface NoteDraft {
  title: string
  body: string
  sources: NoteSource[]
}

interface Props {
  libraryId: string
  /** Una nota da salvare arrivata da fuori (es. un punto dello Studio). */
  incoming: NoteDraft | null
  onIncomingHandled: () => void
}

export default function NotesPanel({ libraryId, incoming, onIncomingHandled }: Props) {
  const { t } = useTheme()
  const [notes, setNotes] = useState<Note[]>([])
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const [open, setOpen] = useState<string | null>(null)

  const base = `/api/libraries/${libraryId}/notes`

  const load = useCallback(async () => {
    if (!libraryId) return
    try {
      const response = await fetch(base, { credentials: 'include' })
      if (!response.ok) throw new Error()
      setNotes((await response.json()).items ?? [])
    } catch {
      setError('Note non disponibili.')
    }
  }, [base, libraryId])

  useEffect(() => { setNotes([]); setError(''); void load() }, [load])

  const save = useCallback(async (note: NoteDraft) => {
    setError('')
    const response = await fetch(base, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(note),
    })
    if (!response.ok) { setError('Nota non salvata.'); return }
    const created: Note = await response.json()
    setNotes(current => [created, ...current])
  }, [base])

  useEffect(() => {
    if (incoming) { void save(incoming); onIncomingHandled() }
  }, [incoming, onIncomingHandled, save])

  const remove = async (id: string) => {
    const response = await fetch(`${base}/${id}`, { method: 'DELETE', credentials: 'include' })
    if (response.ok) setNotes(current => current.filter(note => note.id !== id))
    else setError('Nota non eliminata.')
  }

  return (
    <section className={`rounded-2xl border p-4 ${t.card}`} aria-label="Le mie note">
      <p className="flex items-center gap-2 text-sm font-semibold"><NotebookPen className="h-4 w-4 text-blue-400" />Le mie note</p>
      <p className={`mt-1 text-[11px] leading-4 ${t.cardDesc}`}>Private: le vedi solo tu.</p>
      <form
        className="mt-3"
        onSubmit={event => {
          event.preventDefault()
          if (!draft.trim()) return
          void save({ title: '', body: draft, sources: [] })
          setDraft('')
        }}
      >
        <textarea
          aria-label="Nuova nota"
          value={draft}
          onChange={event => setDraft(event.target.value)}
          rows={3}
          placeholder="Scrivi una nota…"
          className={`w-full resize-y rounded-xl border px-3 py-2 text-sm ${t.sidebarInput}`}
        />
        <Button type="submit" variant="secondary" className="mt-2 w-full" disabled={!draft.trim()}>Aggiungi nota</Button>
      </form>
      {error && <p className="mt-2 text-xs text-rose-300" role="alert">{error}</p>}
      <ul className="mt-3 space-y-2">
        {notes.map(note => (
          <li key={note.id} className="rounded-xl border border-white/10 p-3">
            <div className="flex items-start justify-between gap-2">
              <button type="button" onClick={() => setOpen(open === note.id ? null : note.id)} className="text-left text-sm font-medium">
                {note.title}
              </button>
              <button type="button" aria-label={`Elimina nota ${note.title}`} onClick={() => void remove(note.id)} className="text-slate-500 hover:text-rose-400">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
            {open === note.id && (
              <div className={`mt-2 text-xs leading-5 ${t.cardDesc}`}>
                <p className="whitespace-pre-wrap">{note.body}</p>
                {note.sources.length > 0 && (
                  <ul className="mt-2 space-y-1 border-t border-white/10 pt-2">
                    {note.sources.map((source, index) => (
                      <li key={index}>{source.filename}{source.locator ? ` — ${source.locator}` : ''}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
