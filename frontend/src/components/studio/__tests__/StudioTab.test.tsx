import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import StudioTab, { type StudioResult } from '../StudioTab'

const libraries = [{ id: 'lib-1', name: 'Amministrazione' }]

function respond(body: StudioResult) {
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => body } as Response)
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
})
