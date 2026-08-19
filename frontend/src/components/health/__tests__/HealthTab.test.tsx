import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import HealthTab from '../HealthTab'

function renderWithTheme(ui: React.ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>)
}

describe('HealthTab', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('shows loading state initially', () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}))
    const { container } = renderWithTheme(<HealthTab />)
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders health status when fetch succeeds', async () => {
    const mockHealth = {
      status: 'healthy',
      api: 'healthy',
      documents: 'healthy',
      vector_store: 'healthy',
      providers: 'healthy',
      modules: { 'RAG': { status: 'healthy', documents: 10, models: 2 } }
    }
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => mockHealth
    } as any)

    renderWithTheme(<HealthTab />)

    await waitFor(() => {
      expect(screen.getByText('Stato Sistema')).toBeInTheDocument()
      expect(screen.getByText('API Server')).toBeInTheDocument()
    })
  })
})
