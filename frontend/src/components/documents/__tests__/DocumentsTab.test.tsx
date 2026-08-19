import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import DocumentsTab from '../DocumentsTab'

function renderWithTheme(ui: React.ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>)
}

describe('DocumentsTab', () => {
  const showNotif = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    showNotif.mockReset()
  })

  it('shows an empty-library state', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => ({ items: [] }) } as Response)

    renderWithTheme(<DocumentsTab showNotif={showNotif} />)

    await waitFor(() => expect(screen.getByText('Crea la prima biblioteca per iniziare.')).toBeInTheDocument())
    expect(screen.getByText('Inizia con una biblioteca')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Crea la prima biblioteca' })).toBeInTheDocument()
  })

  it('shows documents for the selected library', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ id: 'library-1', name: 'Procedure HR', description: '', visibility: 'private', document_count: 1 }] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ id: 'document-1', filename: 'ferie.md', size_bytes: 1200, version: 1, status: 'queued' }] }) } as Response)

    renderWithTheme(<DocumentsTab showNotif={showNotif} />)

    await waitFor(() => expect(screen.getByText('ferie.md')).toBeInTheDocument())
    expect(screen.getAllByText('Procedure HR')).toHaveLength(2)
  })

  it('lets the owner manage collaborators without exposing controls to readers', async () => {
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input)
      if (init?.method === 'PUT' && url.endsWith('/members')) return { ok: true, json: async () => ({ username: 'maria', role: 'editor' }) } as Response
      if (url === '/api/libraries') return { ok: true, json: async () => ({ items: [{ id: 'library-1', name: 'Procedure HR', description: '', visibility: 'private', document_count: 1 }] }) } as Response
      if (url.endsWith('/documents')) return { ok: true, json: async () => ({ items: [{ id: 'document-1', filename: 'ferie.md', size_bytes: 1200, version: 1, status: 'ready' }] }) } as Response
      if (url.endsWith('/members')) return { ok: true, json: async () => ({ items: [{ username: 'owner', role: 'owner' }, { username: 'maria', role: 'viewer' }] }) } as Response
      return { ok: false, json: async () => ({}) } as Response
    })

    renderWithTheme(<DocumentsTab showNotif={showNotif} />)

    const collaborators = await screen.findByRole('button', { name: /Collaboratori/ })
    fireEvent.click(collaborators)
    expect(screen.getByText('Accesso alla biblioteca')).toBeInTheDocument()
    expect(screen.getByText('owner')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Nome utente collaboratore'), { target: { value: 'maria' } })
    fireEvent.change(screen.getByLabelText('Ruolo collaboratore'), { target: { value: 'editor' } })
    fireEvent.click(screen.getByRole('button', { name: 'Aggiungi' }))

    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/libraries/library-1/members', expect.objectContaining({ method: 'PUT' })))
  })

  it('shows whether a document search used local hybrid retrieval', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ id: 'library-1', name: 'Procedure HR', description: '', visibility: 'private', document_count: 1 }] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ id: 'document-1', filename: 'ferie.md', size_bytes: 1200, version: 1, status: 'ready' }] }) } as Response)
      .mockResolvedValueOnce({ ok: false, json: async () => ({}) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ document_id: 'document-1', filename: 'ferie.md', excerpt: 'Cinque giorni.', citation: { version: 1, locator: 'Sezione: Ferie' } }], retrieval_profile: { mode: 'hybrid_local', semantic_used: true, semantic_indexed_chunks: 4 } }) } as Response)

    renderWithTheme(<DocumentsTab showNotif={showNotif} />)

    const input = await screen.findByPlaceholderText('Cerca nei documenti della biblioteca')
    fireEvent.change(input, { target: { value: 'ferie' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cerca' }))

    expect(await screen.findByText('Ricerca ibrida locale · 4 passaggi vettoriali')).toBeInTheDocument()
  })

  it('keeps write controls hidden for a viewer library role', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ id: 'library-1', name: 'Procedure HR', description: '', visibility: 'private', document_count: 1, access_role: 'viewer' }] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ id: 'document-1', filename: 'ferie.md', size_bytes: 1200, version: 1, status: 'ready' }] }) } as Response)
      .mockResolvedValueOnce({ ok: false, json: async () => ({}) } as Response)

    renderWithTheme(<DocumentsTab showNotif={showNotif} />)

    await screen.findByText('Sola lettura')
    expect(screen.queryByText('Carica documento')).not.toBeInTheDocument()
    expect(screen.queryByText('Reindicizza')).not.toBeInTheDocument()
  })
})
