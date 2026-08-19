import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import Sidebar from '../Sidebar'

const defaultProps = {
  activeTab: 'chat' as const, onTabChange: vi.fn(), healthStatus: { status: 'healthy' }, onRefresh: vi.fn(),
}

const renderSidebar = (props = {}) => render(<ThemeProvider><Sidebar {...defaultProps} {...props} /></ThemeProvider>)

describe('Sidebar', () => {
  it('explains the library-level AI policy instead of a global model selector', () => {
    renderSidebar()
    expect(screen.getByText('Assistente IA')).toBeInTheDocument()
    expect(screen.getByText(/La biblioteca scelta decide/)).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('navigates to document libraries', () => {
    const onTabChange = vi.fn()
    renderSidebar({ onTabChange })
    fireEvent.click(screen.getByText('Biblioteche e documenti'))
    expect(onTabChange).toHaveBeenCalledWith('docs')
  })

  it('shows administration only for administrators', () => {
    renderSidebar()
    expect(screen.queryByText('Audit Log')).not.toBeInTheDocument()
    renderSidebar({ isAdmin: true })
    expect(screen.getAllByText('Audit Log').length).toBeGreaterThan(0)
  })
})
