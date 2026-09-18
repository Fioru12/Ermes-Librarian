import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../../hooks/useTheme'
import { ConfirmProvider, useConfirm } from '../ConfirmDialog'

function Deleter({ onResult }: { onResult: (value: boolean) => void }) {
  const confirm = useConfirm()
  return (
    <button
      onClick={async () => onResult(await confirm({ title: 'Eliminare il documento?', message: 'Non è reversibile.', confirmLabel: 'Elimina', danger: true }))}
    >
      Elimina documento
    </button>
  )
}

function renderWithProvider(onResult: (value: boolean) => void) {
  return render(
    <ThemeProvider>
      <ConfirmProvider>
        <Deleter onResult={onResult} />
      </ConfirmProvider>
    </ThemeProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('ConfirmDialog', () => {
  it('resolves true on confirm and closes', async () => {
    const onResult = vi.fn()
    renderWithProvider(onResult)
    fireEvent.click(screen.getByText('Elimina documento'))

    const dialog = await screen.findByRole('dialog', { name: 'Eliminare il documento?' })
    expect(dialog).toHaveTextContent('Non è reversibile.')
    fireEvent.click(screen.getByRole('button', { name: 'Elimina' }))

    await waitFor(() => expect(onResult).toHaveBeenCalledWith(true))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('resolves false on Annulla, on Escape, and on a click outside', async () => {
    const onResult = vi.fn()
    renderWithProvider(onResult)

    fireEvent.click(screen.getByText('Elimina documento'))
    fireEvent.click(await screen.findByRole('button', { name: 'Annulla' }))
    await waitFor(() => expect(onResult).toHaveBeenLastCalledWith(false))

    fireEvent.click(screen.getByText('Elimina documento'))
    await screen.findByRole('dialog')
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(onResult).toHaveBeenCalledTimes(2))
    expect(onResult).toHaveBeenLastCalledWith(false)

    fireEvent.click(screen.getByText('Elimina documento'))
    const overlay = await screen.findByRole('dialog')
    fireEvent.click(overlay)
    await waitFor(() => expect(onResult).toHaveBeenCalledTimes(3))
    expect(onResult).toHaveBeenLastCalledWith(false)
  })

  it('focuses the confirm button so Enter confirms', async () => {
    renderWithProvider(vi.fn())
    fireEvent.click(screen.getByText('Elimina documento'))
    const confirmButton = await screen.findByRole('button', { name: 'Elimina' })
    expect(document.activeElement).toBe(confirmButton)
  })

  it('falls back to window.confirm when no provider is mounted', async () => {
    const native = vi.fn(() => true)
    vi.stubGlobal('confirm', native)
    const onResult = vi.fn()
    render(<Deleter onResult={onResult} />)
    fireEvent.click(screen.getByText('Elimina documento'))
    await waitFor(() => expect(onResult).toHaveBeenCalledWith(true))
    expect(native).toHaveBeenCalledWith('Eliminare il documento?\n\nNon è reversibile.')
  })
})
