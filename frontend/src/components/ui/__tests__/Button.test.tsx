import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Button } from '../Button'

describe('Button', () => {
  it('renders children text', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByRole('button')).toHaveTextContent('Click me')
  })

  it('applies primary variant classes by default', () => {
    render(<Button>Primary</Button>)
    const btn = screen.getByRole('button')
    expect(btn.className).toContain('bg-blue-600')
  })

  it('applies secondary variant classes', () => {
    render(<Button variant="secondary">Secondary</Button>)
    const btn = screen.getByRole('button')
    expect(btn.className).toContain('border')
  })

  it('applies danger variant classes', () => {
    render(<Button variant="danger">Danger</Button>)
    const btn = screen.getByRole('button')
    expect(btn.className).toContain('text-rose-400')
  })

  it('applies ghost variant classes', () => {
    render(<Button variant="ghost">Ghost</Button>)
    const btn = screen.getByRole('button')
    expect(btn.className).toContain('text-slate-400')
  })

  it('applies success variant classes', () => {
    render(<Button variant="success">Success</Button>)
    const btn = screen.getByRole('button')
    expect(btn.className).toContain('bg-emerald-600')
  })

  it('is disabled when disabled prop is true', () => {
    render(<Button disabled>Disabled</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('calls onClick handler', () => {
    let clicked = false
    render(<Button onClick={() => { clicked = true }}>Click</Button>)
    screen.getByRole('button').click()
    expect(clicked).toBe(true)
  })

  it('passes additional className', () => {
    render(<Button className="extra-class">Test</Button>)
    expect(screen.getByRole('button').className).toContain('extra-class')
  })

  it('passes additional HTML attributes', () => {
    render(<Button data-testid="custom-btn" type="submit">Submit</Button>)
    const btn = screen.getByTestId('custom-btn')
    expect(btn).toHaveAttribute('type', 'submit')
  })
})
