import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import KnowledgeGraphTab from '../KnowledgeGraphTab'

function renderWithTheme(ui: React.ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>)
}

describe('KnowledgeGraphTab', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('shows loading state initially', () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}))
    const { container } = renderWithTheme(<KnowledgeGraphTab />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders graph when fetch succeeds', async () => {
    const mockGraph = {
      nodes: [{ id: 'N1', name: 'Node 1', tipo: 'base' }],
      links: []
    }
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => mockGraph
    } as any)

    renderWithTheme(<KnowledgeGraphTab />)

    await waitFor(() => {
      expect(screen.getByText('Knowledge Graph')).toBeInTheDocument()
      expect(screen.getByText('N1')).toBeInTheDocument()
    })
  })
})
