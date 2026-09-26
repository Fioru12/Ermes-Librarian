import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import StudioTab, { type StudioResult } from '../StudioTab'

const libraries = [{ id: 'lib-1', name: 'Amministrazione' }]

const saved: unknown[] = []

function respond(body: StudioResult) {
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const target = String(url)
    if (target.endsWith('/notes') && init?.method === 'POST') {
      const note = JSON.parse(String(init.body))
      saved.push(note)
      return { ok: true, json: async () => ({ id: `n${saved.length}`, updated_at: '', ...note }) } as Response
    }
    if (target.endsWith('/notes')) return { ok: true, json: async () => ({ items: [] }) } as Response
    return { ok: true, json: async () => body } as Response
  })
}

function renderStudio(onAsk = vi.fn()) {
  render(
    <ThemeProvider>
      <StudioTab libraries={libraries} selectedLibraryId="lib-1" onSelectLibrary={vi.fn()} onAsk={onAsk} />
    </ThemeProvider>,
  )
  return onAsk
}

const source = { marker: 1, filename: 'nota-spese.md', version: 2, locator: 'Sezione: Scadenze', excerpt: 'Entro il quinto giorno lavorativo.' }

describe('StudioTab', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('generates a briefing and shows the cited passage on demand', async () => {
    respond({ kind: 'briefing', status: 'answered', reason: '', discarded: 1, sources: [source], items: [{ text: 'La nota spese ha una scadenza mensile.', citations: [1] }] })
    renderStudio()

    fireEvent.click(screen.getByRole('button', { name: /genera/i }))

    await waitFor(() => expect(screen.getByText('La nota spese ha una scadenza mensile.')).toBeInTheDocument())
    expect(fetch).toHaveBeenCalledWith('/api/libraries/lib-1/studio/briefing', expect.objectContaining({ method: 'POST' }))
    expect(screen.getByText(/1 punti scartati/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '1' }))
    expect(screen.getByText('Entro il quinto giorno lavorativo.')).toBeInTheDocument()
    expect(screen.getByText('Sezione: Scadenze')).toBeInTheDocument()
  })

  it('says why nothing was generated instead of showing an empty page', async () => {
    respond({ kind: 'briefing', status: 'unavailable', reason: 'Il modello scelto per la biblioteca non ha risposto.', discarded: 0, sources: [], items: [] })
    renderStudio()

    fireEvent.click(screen.getByRole('button', { name: /genera/i }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('non ha risposto'))
  })

  it('sends a suggested question to the assistant', async () => {
    respond({ kind: 'questions', status: 'answered', reason: '', discarded: 0, sources: [], items: [{ text: 'Entro quando va consegnata la nota spese?', citations: [] }] })
    const onAsk = renderStudio()

    fireEvent.click(screen.getByRole('tab', { name: /domande suggerite/i }))
    fireEvent.click(screen.getByRole('button', { name: /genera/i }))
    const question = await screen.findByRole('button', { name: 'Entro quando va consegnata la nota spese?' })
    fireEvent.click(question)

    expect(onAsk).toHaveBeenCalledWith('Entro quando va consegnata la nota spese?')
  })

  it('saves a generated point as a private note together with its source', async () => {
    saved.length = 0
    respond({ kind: 'briefing', status: 'answered', reason: '', discarded: 0, sources: [source], items: [{ text: 'La nota spese ha una scadenza mensile.', citations: [1] }] })
    renderStudio()

    fireEvent.click(screen.getByRole('button', { name: /genera/i }))
    fireEvent.click(await screen.findByRole('button', { name: 'Salva nelle note' }))

    await waitFor(() => expect(saved).toHaveLength(1))
    expect(saved[0]).toMatchObject({ body: 'La nota spese ha una scadenza mensile.', sources: [{ filename: 'nota-spese.md', locator: 'Sezione: Scadenze' }] })
    expect(await within(screen.getByRole('region', { name: 'Le mie note' })).findByRole('button', { name: 'Briefing' })).toBeInTheDocument()
  })
})
