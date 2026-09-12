import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import SynonymsSettingsPanel from '../SynonymsSettingsPanel'

function renderWithTheme(ui: React.ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>)
}

describe('SynonymsSettingsPanel', () => {
  const showNotif = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    vi.stubGlobal('confirm', vi.fn(() => true))
    showNotif.mockReset()
  })

  it('renders custom and active synonyms stats correctly', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        custom: { ddt: ['documento di trasporto', 'bolla'] },
        all: { ddt: ['documento di trasporto', 'bolla'], tfr: ['trattamento fine rapporto'] },
        count_custom: 1,
        count_total: 2,
      }),
    } as Response)

    renderWithTheme(<SynonymsSettingsPanel showNotif={showNotif} isAdmin={true} />)

    expect(await screen.findByText('1 Termini Personalizzati')).toBeInTheDocument()
    expect(screen.getByText('2 Totale Termini Attivi')).toBeInTheDocument()
    expect(screen.getByText('ddt')).toBeInTheDocument()
    expect(screen.getByText('documento di trasporto')).toBeInTheDocument()
  })

  it('allows an admin to add a new custom synonym', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          custom: {},
          all: { tfr: ['trattamento fine rapporto'] },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          term: 'cig',
          synonyms: ['codice appalto'],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          custom: { cig: ['codice appalto'] },
          all: { cig: ['codice appalto'], tfr: ['trattamento fine rapporto'] },
        }),
      } as Response)

    renderWithTheme(<SynonymsSettingsPanel showNotif={showNotif} isAdmin={true} />)

    await screen.findByText('Nessun termine personalizzato configurato. Aggiungine uno sopra!')

    fireEvent.change(screen.getByPlaceholderText('es. DDT, WFH, CIG...'), { target: { value: 'cig' } })
    fireEvent.change(screen.getByPlaceholderText('es. documento di trasporto, bolla di consegna'), { target: { value: 'codice appalto' } })
    fireEvent.click(screen.getByRole('button', { name: /Aggiungi al Glossario/i }))

    await waitFor(() => {
      expect(showNotif).toHaveBeenCalledWith(expect.stringContaining('cig'), 'success')
    })
  })

  it('allows an admin to delete a custom synonym', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          custom: { ddt: ['documento di trasporto'] },
          all: { ddt: ['documento di trasporto'] },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, term: 'ddt' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          custom: {},
          all: {},
        }),
      } as Response)

    renderWithTheme(<SynonymsSettingsPanel showNotif={showNotif} isAdmin={true} />)

    await screen.findByText('ddt')
    const deleteBtn = screen.getByTitle('Elimina ddt')
    fireEvent.click(deleteBtn)

    await waitFor(() => {
      expect(showNotif).toHaveBeenCalledWith(expect.stringContaining('ddt'), 'success')
    })
  })
})
