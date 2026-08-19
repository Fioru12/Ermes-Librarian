import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import { Input, Select } from '../Input'

function renderWithTheme(ui: React.ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>)
}

describe('Input', () => {
  it('renders input element', () => {
    renderWithTheme(<Input placeholder="Type here" />)
    expect(screen.getByPlaceholderText('Type here')).toBeInTheDocument()
  })

  it('renders label when provided', () => {
    renderWithTheme(<Input label="Username" />)
    expect(screen.getByText('Username')).toBeInTheDocument()
  })

  it('does not render label when not provided', () => {
    const { container } = renderWithTheme(<Input />)
    expect(container.querySelector('label')).toBeNull()
  })

  it('passes value and onChange', () => {
    const handleChange = () => {}
    renderWithTheme(<Input value="hello" onChange={handleChange} />)
    expect(screen.getByDisplayValue('hello')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    renderWithTheme(<Input className="custom" data-testid="inp" />)
    expect(screen.getByTestId('inp').className).toContain('custom')
  })

  it('passes input type', () => {
    renderWithTheme(<Input type="password" data-testid="pwd" />)
    expect(screen.getByTestId('pwd')).toHaveAttribute('type', 'password')
  })
})

describe('Select', () => {
  it('renders select element', () => {
    renderWithTheme(
      <Select>
        <option value="a">A</option>
        <option value="b">B</option>
      </Select>
    )
    expect(screen.getByRole('combobox')).toBeInTheDocument()
  })

  it('renders options', () => {
    renderWithTheme(
      <Select>
        <option value="a">Option A</option>
        <option value="b">Option B</option>
      </Select>
    )
    expect(screen.getByText('Option A')).toBeInTheDocument()
    expect(screen.getByText('Option B')).toBeInTheDocument()
  })

  it('renders label when provided', () => {
    renderWithTheme(<Select label="Modulo"><option>x</option></Select>)
    expect(screen.getByText('Modulo')).toBeInTheDocument()
  })

  it('applies value', () => {
    renderWithTheme(
      <Select value="b">
        <option value="a">A</option>
        <option value="b">B</option>
      </Select>
    )
    expect(screen.getByRole('combobox')).toHaveValue('b')
  })
})
