import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import ConnectorsTab from '../ConnectorsTab'

function renderWithTheme(ui: React.ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>)
}

describe('ConnectorsTab', () => {
  const showNotif = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  it('populates the target library selector from `items` (regressione: usava `libraries`)', async () => {
    const fetchMock = vi.mocked(fetch)
    // /api/libraries -> { items: [...] }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/libraries') {
        return { ok: true, json: async () => ({ items: [{ id: 'lib-1', name: 'HR Policy' }] }) } as any
      }
      if (url === '/api/connectors/watcher/status') {
        return { ok: true, json: async () => ({ active: true, monitored_sources_count: 2 }) } as any
      }
      return { ok: false, json: async () => ({}) } as any
    })

    renderWithTheme(<ConnectorsTab showNotif={showNotif} />)

    await waitFor(() => {
      expect(screen.getByText('HR Policy (lib-1)')).toBeInTheDocument()
    })
  })

  it('shows the Microsoft 365 connector card and the Folder Watcher status', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ active: true, monitored_sources_count: 3 }),
    } as any)

    renderWithTheme(<ConnectorsTab showNotif={showNotif} />)

    await waitFor(() => {
      expect(screen.getByText('Microsoft 365 (SharePoint / OneDrive)')).toBeInTheDocument()
      expect(screen.getByText(/Attivo — 3 sorgenti monitorate/)).toBeInTheDocument()
    })
  })
})