import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import ProvidersTab from '../ProvidersTab'

function renderWithTheme(ui: React.ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>)
}

describe('ProvidersTab', () => {
  const showNotif = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('renders provider list', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => ({ providers: [{ name: 'Test', type: 'openai', enabled: true }] })
    } as any)
    
    renderWithTheme(<ProvidersTab showNotif={showNotif} />)
    
    await waitFor(() => {
        expect(screen.getByText('Test', { selector: 'span.font-bold' })).toBeInTheDocument()
    })
  })
})
