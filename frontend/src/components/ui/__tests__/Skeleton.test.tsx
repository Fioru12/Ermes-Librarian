import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '../../../hooks/useTheme'
import { PanelSkeleton } from '../Skeleton'

describe('PanelSkeleton', () => {
  it('annuncia il caricamento ai lettori di schermo e segna la zona come occupata', () => {
    render(<ThemeProvider><PanelSkeleton /></ThemeProvider>)
    const zona = screen.getByRole('status')
    expect(zona).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Caricamento…')).toBeInTheDocument()
  })
})
