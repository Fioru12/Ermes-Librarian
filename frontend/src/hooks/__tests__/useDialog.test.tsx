import { describe, it, expect, vi } from 'vitest'
import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useDialog } from '../useDialog'

function Harness({ onClose = () => {} }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false)
  const close = () => { setOpen(false); onClose() }
  const ref = useDialog<HTMLDivElement>(open, close)
  return (
    <div>
      <button onClick={() => setOpen(true)}>Apri</button>
      {open && (
        <div ref={ref} role="dialog" aria-modal="true" aria-label="Prova" tabIndex={-1}>
          <button>Primo</button>
          <button>Ultimo</button>
        </div>
      )}
    </div>
  )
}

describe('useDialog', () => {
  it('porta il focus dentro la finestra quando si apre', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByText('Apri'))
    expect(screen.getByRole('dialog')).toHaveFocus()
  })

  it('tiene Tab e Maiusc+Tab dentro la finestra', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByText('Apri'))
    await user.tab()
    expect(screen.getByText('Primo')).toHaveFocus()
    await user.tab()
    expect(screen.getByText('Ultimo')).toHaveFocus()
    await user.tab()
    expect(screen.getByText('Primo')).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByText('Ultimo')).toHaveFocus()
  })

  it('Esc chiude e il focus torna al pulsante che l\'aveva aperta', async () => {
    const user = userEvent.setup()
    const chiuso = vi.fn()
    render(<Harness onClose={chiuso} />)
    const apri = screen.getByText('Apri')
    await user.click(apri)
    await user.keyboard('{Escape}')
    expect(chiuso).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(apri).toHaveFocus()
  })
})
