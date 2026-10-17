import { describe, it, expect, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useInstallPrompt } from '../useInstallPrompt'

function offerta() {
  const evento = new Event('beforeinstallprompt', { cancelable: true }) as Event & { prompt: () => Promise<void> }
  evento.prompt = vi.fn().mockResolvedValue(undefined)
  return evento
}

describe('useInstallPrompt', () => {
  it('non propone nulla finché il browser non offre l\'installazione', () => {
    const { result } = renderHook(() => useInstallPrompt())
    expect(result.current.canInstall).toBe(false)
  })

  it('propone l\'installazione quando il browser la offre e blocca il banner predefinito', () => {
    const { result } = renderHook(() => useInstallPrompt())
    const evento = offerta()
    act(() => { window.dispatchEvent(evento) })
    expect(result.current.canInstall).toBe(true)
    expect(evento.defaultPrevented).toBe(true)
  })

  it('install() mostra la finestra di installazione una volta sola', async () => {
    const { result } = renderHook(() => useInstallPrompt())
    const evento = offerta()
    act(() => { window.dispatchEvent(evento) })
    await act(async () => { await result.current.install() })
    expect(evento.prompt).toHaveBeenCalledTimes(1)
    expect(result.current.canInstall).toBe(false)
  })

  it('dopo l\'installazione il pulsante sparisce', () => {
    const { result } = renderHook(() => useInstallPrompt())
    act(() => { window.dispatchEvent(offerta()) })
    act(() => { window.dispatchEvent(new Event('appinstalled')) })
    expect(result.current.canInstall).toBe(false)
  })
})
