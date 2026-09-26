import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import Sidebar from '../Sidebar'

const defaultProps = {
  activeTab: 'chat' as const, onTabChange: vi.fn(), healthStatus: { status: 'healthy' }, onRefresh: vi.fn(),
}

const renderSidebar = (props = {}) => render(<ThemeProvider><Sidebar {...defaultProps} {...props} /></ThemeProvider>)

describe('Sidebar', () => {
  it('explains the library-level AI policy in plain words, without a global model selector', () => {
    renderSidebar()
    expect(screen.getByText('Assistente IA')).toBeInTheDocument()
    expect(screen.getByText(/Ogni biblioteca decide/)).toBeInTheDocument()
    expect(screen.queryByText(/Ollama|provider cloud/)).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('navigates to document libraries', () => {
    const onTabChange = vi.fn()
    renderSidebar({ onTabChange })
    fireEvent.click(screen.getByText('Biblioteche e documenti'))
    expect(onTabChange).toHaveBeenCalledWith('docs')
  })

  it('shows administration pages only to administrators', () => {
    renderSidebar()
    // Un utente semplice vede solo cio' che puo' usare.
    for (const adminOnly of ['Registro attività', 'Collegamenti esterni', 'Stato del sistema']) {
      expect(screen.queryByText(adminOnly)).not.toBeInTheDocument()
    }
    expect(screen.getByText('Studio')).toBeInTheDocument()
    renderSidebar({ isAdmin: true })
    expect(screen.getAllByText('Registro attività').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Collegamenti esterni').length).toBeGreaterThan(0)
  })
})
