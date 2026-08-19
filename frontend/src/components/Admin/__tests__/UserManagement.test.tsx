import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import UserManagement from '../UserManagement'

describe('UserManagement', () => {
  const showNotif = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    showNotif.mockReset()
  })

  it('shows a newly generated API key in a one-time dialog instead of a notification', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ users: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ users: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ success: true, username: 'maria', role: 'viewer', api_key: 'ermes_demo_secret' }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ users: [{ username: 'maria', role: 'viewer' }] }) } as Response)

    render(<UserManagement showNotif={showNotif} />)
    await screen.findByText('Chiavi API (accesso programmatico)')
    fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'maria' } })
    fireEvent.click(screen.getByRole('button', { name: /^Crea$/ }))

    expect(await screen.findByRole('dialog', { name: 'Nuova chiave API' })).toHaveTextContent('ermes_demo_secret')
    expect(showNotif).toHaveBeenCalledWith(expect.not.stringContaining('ermes_demo_secret'), 'success')
  })

  it('creates a local web account without exposing its password again', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ users: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ users: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ success: true, username: 'maria', role: 'editor' }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ users: [{ username: 'maria', role: 'editor', active: true }] }) } as Response)

    render(<UserManagement showNotif={showNotif} />)
    fireEvent.change(screen.getByPlaceholderText('Username account'), { target: { value: 'maria' } })
    fireEvent.change(screen.getByLabelText('Password account locale'), { target: { value: 'StrongUser!123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Crea account' }))

    const createdRole = await screen.findByLabelText('Ruolo di maria') as HTMLSelectElement
    expect(createdRole.value).toBe('editor')
    expect(showNotif).toHaveBeenCalledWith(expect.not.stringContaining('StrongUser!123'), 'success')
  })

  it('updates a local account without exposing its new password in notifications', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ users: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ users: [{ username: 'maria', role: 'viewer', active: true }] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ success: true, username: 'maria', role: 'editor', active: false }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ users: [{ username: 'maria', role: 'editor', active: false }] }) } as Response)

    render(<UserManagement showNotif={showNotif} />)
    await screen.findByText('maria')
    fireEvent.change(screen.getByLabelText('Ruolo di maria'), { target: { value: 'editor' } })
    fireEvent.click(screen.getByLabelText('Accesso attivo per maria'))
    fireEvent.change(screen.getByLabelText('Nuova password per maria'), { target: { value: 'ChangedUser!456' } })
    fireEvent.click(screen.getByLabelText('Salva account maria'))

    await screen.findByText('disattivato')
    expect(showNotif).toHaveBeenCalledWith(expect.not.stringContaining('ChangedUser!456'), 'success')
  })
})
