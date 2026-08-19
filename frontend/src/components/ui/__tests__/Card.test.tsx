import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import { Card, CardTitle } from '../Card'

function renderWithTheme(ui: React.ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>)
}

describe('Card', () => {
  it('renders children', () => {
    renderWithTheme(<Card>Content</Card>)
    expect(screen.getByText('Content')).toBeInTheDocument()
  })

  it('applies card classes', () => {
    renderWithTheme(<Card data-testid="card">Test</Card>)
    expect(screen.getByTestId('card').className).toContain('rounded-2xl')
  })

  it('applies custom className', () => {
    renderWithTheme(<Card className="my-class" data-testid="card">X</Card>)
    expect(screen.getByTestId('card').className).toContain('my-class')
  })

  it('calls onClick when provided', () => {
    let clicked = false
    renderWithTheme(<Card onClick={() => { clicked = true }} data-testid="card">Click</Card>)
    screen.getByTestId('card').click()
    expect(clicked).toBe(true)
  })
})

describe('CardTitle', () => {
  it('renders children text', () => {
    renderWithTheme(<CardTitle>Titolo</CardTitle>)
    expect(screen.getByText('Titolo')).toBeInTheDocument()
  })

  it('applies heading classes', () => {
    renderWithTheme(<CardTitle>Title</CardTitle>)
    expect(screen.getByText('Title').className).toContain('font-bold')
  })
})
