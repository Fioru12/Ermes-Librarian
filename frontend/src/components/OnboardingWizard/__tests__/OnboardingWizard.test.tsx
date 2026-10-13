import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import OnboardingWizard from '../OnboardingWizard'

describe('OnboardingWizard', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ id: 'lib-9', name: 'Ufficio acquisti' }) }) as Response))
  })

  it('opens straight on creating the first library, with labelled fields', async () => {
    const onLibraryCreated = vi.fn()
    render(<ThemeProvider><OnboardingWizard onLibraryCreated={onLibraryCreated} showNotif={vi.fn()} /></ThemeProvider>)

    // Nessun passaggio "Benvenuto → Inizia ora" prima dei campi.
    expect(screen.queryByRole('button', { name: /inizia ora/i })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Nome'), { target: { value: 'Ufficio acquisti' } })
    fireEvent.click(screen.getByRole('button', { name: 'Crea' }))

    await waitFor(() => expect(onLibraryCreated).toHaveBeenCalledWith('lib-9'))
  })
})
