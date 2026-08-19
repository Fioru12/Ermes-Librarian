import { fireEvent, render, screen } from '@testing-library/react'
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
    expect(screen.getByText('Fonti verificate')).toBeInTheDocument()
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
    expect(screen.getByText('Basata su 1 fonti')).toBeInTheDocument()
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
})
