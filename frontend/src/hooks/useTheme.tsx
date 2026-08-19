import { createContext, useContext, useState, useCallback, useMemo, useEffect, ReactNode } from 'react'
import type { ThemeClasses } from '../types'

interface ThemeContextValue {
  isDark: boolean
  toggle: () => void
  t: ThemeClasses
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

function buildTheme(dark: boolean): ThemeClasses {
  return {
    bg: dark ? 'bg-[#0f1115] text-slate-100' : 'bg-[#f8fafc] text-slate-900',
    sidebar: dark ? 'bg-slate-950/72 border-r border-white/[0.08] ermes-glass' : 'bg-white/78 border-r border-slate-200 ermes-glass',
    sidebarTitle: dark ? 'text-slate-300' : 'text-slate-700',
    sidebarLabel: dark ? 'text-slate-500' : 'text-slate-400',
    sidebarInput: dark ? 'bg-slate-800/50 border-slate-700 text-slate-200 focus:border-blue-500 focus:bg-slate-800 transition-colors' : 'bg-slate-50 border-slate-200 text-slate-900 focus:border-blue-500 focus:bg-white placeholder-slate-400 transition-colors',
    navButtonActive: dark ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20 shadow-sm' : 'bg-blue-50 text-blue-700 border border-blue-200 shadow-sm',
    navButtonInactive: dark ? 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 transition-colors' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors',
    header: dark ? 'border-b border-white/[0.08] bg-slate-950/48 ermes-glass' : 'border-b border-slate-200 bg-white/78 ermes-glass',
    chatBg: dark ? 'bg-transparent' : 'bg-transparent',
    welcomeTitle: dark ? 'text-slate-100' : 'text-slate-800',
    card: dark ? 'bg-slate-800/30 border border-slate-700/50 hover:border-blue-500/40 hover:bg-slate-800/50 transition-all duration-200' : 'bg-white border border-slate-200 hover:border-blue-400/50 hover:shadow-md transition-all duration-200',
    cardTitle: dark ? 'text-slate-200' : 'text-slate-800',
    cardDesc: dark ? 'text-slate-400' : 'text-slate-500',
    chatBubbleUser: 'bg-blue-600 text-white rounded-tr-sm shadow-sm',
    chatBubbleAssistant: dark ? 'bg-[#1c1e26] text-slate-200 border border-slate-700 rounded-tl-sm shadow-sm' : 'bg-white text-slate-800 border border-slate-200 rounded-tl-sm shadow-sm',
    chatFormBg: dark ? 'border-t border-white/[0.08] bg-slate-950/60 ermes-glass' : 'border-t border-slate-200 bg-white/78 ermes-glass',
    chatInput: dark ? 'bg-slate-800/50 border border-slate-700 text-slate-200 focus:border-blue-500 focus:bg-slate-800 placeholder-slate-500 rounded-xl transition-colors' : 'bg-slate-50 border border-slate-200 text-slate-800 focus:border-blue-500 focus:bg-white placeholder-slate-400 rounded-xl transition-colors',
    statusFooter: dark ? 'bg-slate-950/55 border-t border-white/[0.08] ermes-glass' : 'bg-slate-50/80 border-t border-slate-200 ermes-glass',
    tableHeader: dark ? 'bg-slate-800/50 text-slate-400 border-b border-slate-700' : 'bg-slate-50 text-slate-600 border-b border-slate-200',
    tableRow: dark ? 'hover:bg-slate-800/30 border-slate-800/50 transition-colors' : 'hover:bg-slate-50 border-slate-100 transition-colors',
    documentsBg: dark ? 'bg-transparent' : 'bg-transparent',
    docSelected: dark ? 'bg-blue-500/10 border-blue-500/30' : 'bg-blue-50 border-blue-300',
    skeleton: dark ? 'bg-slate-800 animate-pulse' : 'bg-slate-200 animate-pulse',
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [isDark, setIsDark] = useState(true)
  const toggle = useCallback(() => setIsDark(d => !d), [])
  const t = useMemo(() => buildTheme(isDark), [isDark])
  
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [isDark])

  return <ThemeContext.Provider value={{ isDark, toggle, t }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
