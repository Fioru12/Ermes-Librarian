import { describe, it, expect, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { ThemeProvider, useTheme } from '../useTheme'

const wrapper = ({ children }: { children: ReactNode }) => <ThemeProvider>{children}</ThemeProvider>

describe('useTheme', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('parte dallo scuro quando non c\'è una scelta salvata', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    expect(result.current.isDark).toBe(true)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('cambia la classe sulla radice e salva la scelta', () => {
    const { result } = renderHook(() => useTheme(), { wrapper })
    act(() => result.current.toggle())
    expect(result.current.isDark).toBe(false)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(window.localStorage.getItem('ermes-theme')).toBe('light')
  })

  it('ricorda il tema chiaro dopo un ricaricamento', () => {
    window.localStorage.setItem('ermes-theme', 'light')
    const { result } = renderHook(() => useTheme(), { wrapper })
    expect(result.current.isDark).toBe(false)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})
