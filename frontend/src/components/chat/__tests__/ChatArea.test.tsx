import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import ChatArea from '../ChatArea'

const defaultProps = {
  messages: [], inputMessage: '', onInputChange: vi.fn(), onSend: vi.fn(), onStop: vi.fn(), isGenerating: false,
  suggestions: [{ title: 'Trova una procedura', desc: 'Cerca una policy', prompt: 'Dove trovo la policy?' }],
  libraries: [{ id: 'hr', name: 'Procedure HR' }], selectedLibraryId: 'hr', selectedLibraryDocumentCount: 3,
  onLibraryChange: vi.fn(), onOpenLibraries: vi.fn(),
}

const renderChat = (props = {}) => render(<ThemeProvider><ChatArea {...defaultProps} {...props} /></ThemeProvider>)

describe('ChatArea', () => {
  it('shows the selected library and evidence-first welcome state', () => {
    renderChat()
    expect(screen.getAllByText('Procedure HR').length).toBeGreaterThan(0)
    expect(screen.getByText(/Ogni risposta indica il documento da cui arriva/)).toBeInTheDocument()
  })

  it('sends a suggested document question', () => {
    const onSend = vi.fn()
    renderChat({ onSend })
    fireEvent.click(screen.getByText('Trova una procedura'))
    expect(onSend).toHaveBeenCalledWith('Dove trovo la policy?')
  })

  it('renders citations for a supported answer', () => {
    renderChat({ messages: [
      { id: 'u', role: 'user' as const, content: 'Quando ferie?', timestamp: '10:00' },
      { id: 'a', role: 'assistant' as const, content: 'Cinque giorni prima.[1]', timestamp: '10:01', evidence: { coverage: 'supported' as const }, sources: [{ document_id: 'd1', filename: 'ferie.md', version: 2, locator: 'Sezione: Ferie', excerpt: 'Le ferie vanno richieste cinque giorni prima.' }] },
    ] })
    expect(screen.getByText('Basata su 1 fonte')).toBeInTheDocument()
    expect(screen.getByText('ferie.md')).toBeInTheDocument()
  })

  it('opens the original document from a citation, scoped to the selected library', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    renderChat({ selectedLibraryId: 'hr', messages: [
      { id: 'a', role: 'assistant' as const, content: 'Cinque giorni prima.[1]', timestamp: '10:01', evidence: { coverage: 'supported' as const }, sources: [{ document_id: 'd1', filename: 'ferie.md', version: 2, locator: 'Sezione: Ferie', excerpt: 'Le ferie vanno richieste cinque giorni prima.' }] },
    ] })
    fireEvent.click(screen.getByTitle('Apri il documento originale'))
    expect(openSpy).toHaveBeenCalledWith('/api/libraries/hr/documents/d1/download', '_blank', 'noopener,noreferrer')
    openSpy.mockRestore()
  })

  it('shows a stop action while a document answer is running', () => {
    const onStop = vi.fn()
    renderChat({ messages: [{ id: 'a', role: 'assistant' as const, content: '', timestamp: '10:00' }], isGenerating: true, onStop })
    fireEvent.click(screen.getByText('Stop'))
    expect(onStop).toHaveBeenCalledOnce()
  })

  it('guides a first-time user to create a library', () => {
    renderChat({ libraries: [], selectedLibraryId: '', selectedLibraryDocumentCount: 0 })
    expect(screen.getByText('Crea la prima biblioteca')).toBeInTheDocument()
  })

  it('opens citation detail modal on marker click and closes it with Escape key', () => {
    renderChat({
      selectedLibraryId: 'hr',
      messages: [
        {
          id: 'a',
          role: 'assistant' as const,
          content: 'Risposta documentata.[1]',
          timestamp: '10:01',
          evidence: { coverage: 'supported' as const },
          sources: [
            {
              document_id: 'd1',
              filename: 'manuale.pdf',
              version: 1,
              locator: 'Pagina 5',
              excerpt: 'Estratto di prova dal manuale.',
              marker: 1,
            },
          ],
        },
      ],
    })

    // Clicca sul marcatore citazione [1]
    fireEvent.click(screen.getByRole('button', { name: /^Fonte 1/ }))
    expect(screen.getByRole('dialog', { name: 'Dettaglio citazione' })).toBeInTheDocument()
    expect(screen.getByText('Citazione [1]')).toBeInTheDocument()
    expect(screen.getByText('Copia estratto')).toBeInTheDocument()

    // Premi Escape per chiudere il modal
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Dettaglio citazione' })).not.toBeInTheDocument()
  })

  it('a negative feedback asks for a reason and sends it as the comment', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    try {
      renderChat({ messages: [{ id: 'ev-1', role: 'assistant', content: 'Risposta.', timestamp: '10:00', sources: [] }] })

      fireEvent.click(screen.getByTitle(/non utile/i))
      expect(screen.getByText('Segnala motivo gap:')).toBeInTheDocument()
      fireEvent.click(screen.getByText(/Fonte non pertinente/))

      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
      const [url, init] = fetchMock.mock.calls[0]
      expect(url).toBe('/api/analytics/feedback')
      expect(JSON.parse(String(init.body))).toEqual({ event_id: 'ev-1', rating: -1, comment: 'Fonte non pertinente' })
      expect(screen.queryByText('Segnala motivo gap:')).not.toBeInTheDocument()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('rolls the optimistic feedback back when the server refuses it', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 500 }))
    vi.stubGlobal('fetch', fetchMock)
    try {
      renderChat({ messages: [{ id: 'ev-2', role: 'assistant', content: 'Risposta.', timestamp: '10:00', sources: [] }] })
      const utile = screen.getByTitle('Utile')
      fireEvent.click(utile)
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
      // Rolled back: the thumb is no longer rendered as selected.
      await waitFor(() => expect(utile.className).not.toMatch(/emerald-500\/20/))
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('provides visual PDF preview toggle and report export', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => ({
      document: { write: vi.fn(), close: vi.fn() },
      focus: vi.fn(),
      print: vi.fn(),
    } as any))

    renderChat({
      selectedLibraryId: 'hr',
      messages: [
        {
          id: 'a',
          role: 'assistant' as const,
          content: 'Consultare il manuale.[1]',
          timestamp: '10:01',
          evidence: { coverage: 'supported' as const },
          sources: [
            {
              document_id: 'd-manuale',
              filename: 'manuale.pdf',
              version: 1,
              locator: 'Pagina 14',
              excerpt: 'Procedura di sicurezza interna.',
              marker: 1,
            },
          ],
        },
      ],
    })

    // Verifica pulsante export report certificato
    expect(screen.getByText('Report PDF')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Report PDF'))
    expect(openSpy).toHaveBeenCalledWith('', '_blank')

    // Apertura citazione
    fireEvent.click(screen.getByRole('button', { name: /^Fonte 1/ }))
    expect(screen.getByText('Citazione [1]')).toBeInTheDocument()

    // Toggle PDF Pag. 14
    const pdfToggle = screen.getByText('Visualizza PDF (Pag. 14)')
    expect(pdfToggle).toBeInTheDocument()
    fireEvent.click(pdfToggle)
    expect(screen.getByTitle('Anteprima PDF manuale.pdf a pagina 14')).toBeInTheDocument()

    openSpy.mockRestore()
  })

  it('prints the report from the opener, with no inline script (the CSP blocks those)', () => {
    vi.useFakeTimers()
    const write = vi.fn()
    const print = vi.fn()
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => ({
      document: { write, close: vi.fn() },
      focus: vi.fn(),
      print,
    } as any))

    renderChat({
      selectedLibraryId: 'hr',
      messages: [
        { id: 'a', role: 'assistant' as const, content: 'Risposta.[1]', timestamp: '10:01',
          evidence: { coverage: 'supported' as const },
          sources: [{ document_id: 'd', filename: '<img src=x onerror=alert(1)>.pdf', version: 1, locator: 'Pagina 1', excerpt: 'x', marker: 1 }] },
      ],
    })
    fireEvent.click(screen.getByText('Report PDF'))

    const html = String(write.mock.calls[0][0])
    expect(html).not.toMatch(/<script/i)
    expect(html).not.toContain('<img src=x') // il nome del file e' escapato
    expect(html).not.toMatch(/certificat|zero allucinazioni/i) // nessuna promessa che il prodotto non puo' mantenere
    expect(print).not.toHaveBeenCalled()
    vi.advanceTimersByTime(500)
    expect(print).toHaveBeenCalledTimes(1)

    openSpy.mockRestore()
    vi.useRealTimers()
  })
})

