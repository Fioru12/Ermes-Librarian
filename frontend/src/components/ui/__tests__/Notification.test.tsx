import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { Notification, Badge } from '../Notification'

describe('Notification', () => {
  it('renders success message', () => {
    render(<Notification message="Operazione completata" type="success" />)
    expect(screen.getByText('Operazione completata')).toBeInTheDocument()
  })

  it('renders error message', () => {
    render(<Notification message="Errore critico" type="error" />)
    expect(screen.getByText('Errore critico')).toBeInTheDocument()
  })

  it('renders with success type by default', () => {
    render(<Notification message="Test" />)
    expect(screen.getByText('Test')).toBeInTheDocument()
  })

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn()
    render(<Notification message="Dismissable" onClose={onClose} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does not render close button when onClose not provided', () => {
    render(<Notification message="No close" />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})

describe('Badge', () => {
  it('renders children text', () => {
    render(<Badge>PDF</Badge>)
    expect(screen.getByText('PDF')).toBeInTheDocument()
  })

  it('applies default blue color', () => {
    render(<Badge>Blue</Badge>)
    expect(screen.getByText('Blue').className).toContain('bg-blue-500/10')
  })

  it('applies emerald color', () => {
    render(<Badge color="emerald">Green</Badge>)
    expect(screen.getByText('Green').className).toContain('bg-emerald-500/10')
  })

  it('applies rose color', () => {
    render(<Badge color="rose">Red</Badge>)
    expect(screen.getByText('Red').className).toContain('bg-rose-500/10')
  })

  it('applies purple color', () => {
    render(<Badge color="purple">Purple</Badge>)
    expect(screen.getByText('Purple').className).toContain('bg-purple-500/10')
  })

  it('applies amber color', () => {
    render(<Badge color="amber">Amber</Badge>)
    expect(screen.getByText('Amber').className).toContain('bg-amber-500/10')
  })
})
